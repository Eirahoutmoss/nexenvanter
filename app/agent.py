"""PC donanım ajanı: Windows bilgisayarlar PowerShell betiğiyle donanım bilgisini gönderir;
seri no / MAC / bilgisayar adıyla envanter kaydına eşlenir."""
import hmac
import json

from . import assets as A, db
from .textnorm import fold

AGENT_FIELDS = ("hostname", "os", "cpu", "ram_gb", "disk", "last_user", "ip_address")

SCRIPT = r"""# NexEnvanter donanim ajani - Windows PowerShell 5.1+
$ErrorActionPreference = 'SilentlyContinue'
$Server = '__SERVER__'
$Token = '__TOKEN__'
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
$os = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$disks = @(Get-CimInstance Win32_DiskDrive | ForEach-Object { '{0} {1:N0}GB' -f $_.Model.Trim(), ($_.Size / 1GB) })
$nics = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True')
$body = @{
  hostname     = $env:COMPUTERNAME
  serial       = "$($bios.SerialNumber)".Trim()
  manufacturer = "$($cs.Manufacturer)".Trim()
  model        = "$($cs.Model)".Trim()
  cpu          = "$cpu".Trim()
  ram_gb       = [math]::Round($cs.TotalPhysicalMemory / 1GB)
  disk         = ($disks -join '; ')
  os           = "$($os.Caption) $($os.Version)".Trim()
  user         = "$($cs.UserName)"
  domain       = "$($cs.Domain)"
  macs         = @($nics | ForEach-Object { $_.MACAddress } | Where-Object { $_ })
  ips          = @($nics | ForEach-Object { $_.IPAddress } | Where-Object { $_ -and $_ -notmatch ':' })
} | ConvertTo-Json -Compress
try {
  Invoke-RestMethod -Uri "$Server/api/agent/report" -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($body)) `
    -ContentType 'application/json; charset=utf-8' -Headers @{ 'X-Agent-Token' = $Token } -TimeoutSec 30 | Out-Null
} catch { exit 1 }
"""

_BAD_SERIALS = {"", "to be filled by o.e.m.", "default string", "system serial number", "0", "none", "not specified", "123456789"}


def script(base_url: str) -> str:
    return SCRIPT.replace("__SERVER__", base_url).replace("__TOKEN__", db.get_setting("agent_token") or "")


def check_token(tok: str | None) -> bool:
    real = db.get_setting("agent_token") or ""
    return bool(tok) and bool(real) and hmac.compare_digest(tok, real)


def _norm(d: dict) -> dict:
    macs = []
    for m in d.get("macs") or []:
        h = "".join(ch for ch in str(m) if ch.isalnum()).upper()
        if len(h) == 12:
            macs.append(":".join(h[i:i + 2] for i in range(0, 12, 2)))
    serial = str(d.get("serial") or "").strip()
    if fold(serial) in _BAD_SERIALS:
        serial = ""
    return {"hostname": str(d.get("hostname") or "").strip()[:64], "serial": serial[:100], "macs": macs,
            "manufacturer": str(d.get("manufacturer") or "").strip()[:80], "model": str(d.get("model") or "").strip()[:120],
            "cpu": str(d.get("cpu") or "")[:200], "ram_gb": d.get("ram_gb"), "disk": str(d.get("disk") or "")[:300],
            "os": str(d.get("os") or "")[:200], "user": str(d.get("user") or "")[:120],
            "ips": [str(x) for x in (d.get("ips") or [])][:8]}


def match(d: dict) -> int | None:
    c = db.conn()
    if d["serial"]:
        r = c.execute("SELECT id FROM assets WHERE archived=0 AND fold(json_extract(data,'$.serial_number'))=?",
                      (fold(d["serial"]),)).fetchone()
        if r:
            return r[0]
    for m in d["macs"]:
        r = c.execute("SELECT id FROM assets WHERE archived=0 AND json_extract(data,'$.mac_address') LIKE ?", (f"%{m}%",)).fetchone()
        if r:
            return r[0]
    if d["hostname"]:
        r = c.execute("SELECT id FROM assets WHERE archived=0 AND fold(json_extract(data,'$.hostname'))=?",
                      (fold(d["hostname"]),)).fetchone()
        if r:
            return r[0]
    return None


def apply(asset_id: int, d: dict, user="ajan"):
    a = A.get(asset_id)
    cur = a["data"]
    payload = {"hostname": d["hostname"], "os": d["os"], "cpu": d["cpu"], "ram_gb": d["ram_gb"], "disk": d["disk"],
               "last_user": d["user"] or cur.get("last_user"), "ip_address": ", ".join(d["ips"]) or cur.get("ip_address")}
    # Elle girilmiş temel alanlar korunur; yalnızca boşsa doldurulur
    if not cur.get("serial_number") and d["serial"]:
        payload["serial_number"] = d["serial"]
    if not cur.get("brand_model") and (d["manufacturer"] or d["model"]):
        payload["brand_model"] = f"{d['manufacturer']} {d['model']}".strip()
    if not cur.get("mac_address") and d["macs"]:
        payload["mac_address"] = ", ".join(d["macs"])
    if not cur.get("hardware_info"):
        payload["hardware_info"] = "Bilgisayar"
    payload = {k: v for k, v in payload.items() if v not in (None, "")}
    try:
        A.update(asset_id, payload, user, blank_overwrites=False, action="agent")
    except A.AssetError:
        # tip uyumsuzluğu vb. durumda ajanın değeri yazılmaz, kayıt bozulmaz
        pass
    db.conn().execute("UPDATE assets SET data=json_set(data,'$.agent_seen_at',?) WHERE id=?", (db.now(), asset_id))


def report(raw: dict, ip: str) -> dict:
    d = _norm(raw)
    if not d["hostname"]:
        raise ValueError("hostname gerekli")
    aid = match(d)
    db.conn().execute("""INSERT INTO agent_reports(hostname,serial,macs,data,ip,at,asset_id) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(hostname) DO UPDATE SET serial=excluded.serial, macs=excluded.macs, data=excluded.data, ip=excluded.ip,
        at=excluded.at, asset_id=coalesce(excluded.asset_id, agent_reports.asset_id)""",
                      (d["hostname"], d["serial"], json.dumps(d["macs"]), json.dumps(d, ensure_ascii=False), ip, db.now(), aid))
    if aid is None:  # daha önce elle eşlenmiş olabilir
        r = db.conn().execute("SELECT asset_id FROM agent_reports WHERE hostname=?", (d["hostname"],)).fetchone()
        aid = r[0] if r else None
    if aid:
        apply(aid, d)
    return {"matched": bool(aid), "asset_id": aid}


def reports(unmatched_only=False):
    q = "SELECT r.*, a.asset_code FROM agent_reports r LEFT JOIN assets a ON a.id=r.asset_id"
    if unmatched_only:
        q += " WHERE r.asset_id IS NULL"
    out = []
    for r in db.conn().execute(q + " ORDER BY r.at DESC LIMIT 2000"):
        x = dict(r)
        x["data"] = json.loads(x["data"])
        out.append(x)
    return out


def link(hostname: str, asset_id: int | None, new_code: str | None, user: str) -> dict:
    r = db.conn().execute("SELECT data FROM agent_reports WHERE hostname=?", (hostname,)).fetchone()
    if not r:
        raise KeyError(hostname)
    d = json.loads(r[0])
    if not asset_id:
        if not (new_code or "").strip():
            raise ValueError("Bağlanacak kayıt veya yeni barkod gerekli")
        asset_id = A.create({"asset_code": new_code, "hardware_info": "Bilgisayar"}, user)["id"]
    db.conn().execute("UPDATE agent_reports SET asset_id=? WHERE hostname=?", (asset_id, hostname))
    apply(asset_id, d, user)
    return A.get(asset_id)
