"""Keşif → onay kuyruğu. Tarama ve ajan yeni (envanterde olmayan) cihaz bulunca doğrudan envantere değil
'onay bekleyen' listesine düşürür. Yetkili onaylayıp envantere ekler ya da (misafir/sahte cihaz) yok sayar."""
import json

from . import assets as A, catalog, db
from .textnorm import fold


def enabled() -> bool:
    return bool(db.get_setting("discovery_approval", True))


def _dedup(ip=None, mac=None, hostname=None) -> str:
    return "mac:" + mac.upper() if mac else ("host:" + fold(hostname) if hostname else "ip:" + (ip or ""))


def offer(ip=None, mac=None, hostname=None, kind=None, source="tarama", data=None) -> int | None:
    """Envanterde yoksa ve bekleyen kuyruğunda yoksa ekle. Döner: pending id veya None (zaten var)."""
    c = db.conn()
    # Zaten envanterde mi? (MAC / IP / ad)
    if mac and c.execute("SELECT 1 FROM assets WHERE archived=0 AND json_extract(data,'$.mac_address') LIKE ?",
                         (f"%{mac.upper()}%",)).fetchone():
        return None
    if ip and c.execute("SELECT 1 FROM assets WHERE archived=0 AND json_extract(data,'$.ip_address') LIKE ?",
                        (f"%{ip}%",)).fetchone():
        return None
    if hostname and c.execute("SELECT 1 FROM assets WHERE archived=0 AND fold(json_extract(data,'$.hostname'))=?",
                             (fold(hostname),)).fetchone():
        return None
    dd = _dedup(ip, mac, hostname)
    ex = c.execute("SELECT id, status FROM pending_devices WHERE dedup=?", (dd,)).fetchone()
    if ex:
        if ex["status"] == "bekliyor":  # bilgileri tazele
            c.execute("UPDATE pending_devices SET ip=COALESCE(?,ip), hostname=COALESCE(?,hostname), kind=COALESCE(?,kind),"
                      " seen_at=?, data=? WHERE id=?", (ip, hostname, kind, db.now(), json.dumps(data or {}, ensure_ascii=False), ex["id"]))
        return None  # yok sayılmış ya da onaylanmışsa tekrar düşürme
    return c.execute("INSERT INTO pending_devices(ip,mac,hostname,kind,source,data,seen_at,dedup) VALUES(?,?,?,?,?,?,?,?)",
                     (ip, mac, hostname, kind, source, json.dumps(data or {}, ensure_ascii=False), db.now(), dd)).lastrowid


def pending(locations=None):
    rows = db.conn().execute("SELECT * FROM pending_devices WHERE status='bekliyor' ORDER BY seen_at DESC LIMIT 2000")
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"] or "{}")
        out.append(d)
    return out


def count_pending() -> int:
    return db.conn().execute("SELECT COUNT(*) FROM pending_devices WHERE status='bekliyor'").fetchone()[0]


def ignore(pid, user):
    db.conn().execute("UPDATE pending_devices SET status='yok sayıldı', decided_at=?, decided_by=? WHERE id=?",
                      (db.now(), user, pid))


def approve(pid, user, extra: dict | None = None, type_name=None) -> dict:
    c = db.conn()
    p = c.execute("SELECT * FROM pending_devices WHERE id=?", (pid,)).fetchone()
    if not p:
        raise KeyError(pid)
    if p["status"] != "bekliyor":
        raise ValueError("Bu kayıt zaten işlenmiş")
    d = json.loads(p["data"] or "{}")
    payload = {"mac_address": p["mac"] or "", "ip_address": p["ip"] or "",
               "hostname": (p["hostname"] or (d.get("netbios") or "")).split(".")[0]}
    if type_name:
        payload["hardware_info"] = type_name
    elif p["kind"] == "Yazıcı":
        payload["hardware_info"] = "Yazıcı"
    # ajan verisi varsa taşı
    for k in ("serial", "manufacturer", "model", "cpu", "ram_gb", "disk", "os"):
        if d.get(k):
            payload.setdefault({"serial": "serial_number", "model": "brand_model"}.get(k, k), d[k])
    if d.get("manufacturer") and d.get("model"):
        payload["brand_model"] = f"{d['manufacturer']} {d['model']}".strip()
    payload.update(extra or {})
    payload = {k: v for k, v in payload.items() if v not in (None, "")}
    a = A.create(payload, user)
    c.execute("UPDATE pending_devices SET status='onaylandı', decided_at=?, decided_by=?, asset_id=? WHERE id=?",
              (db.now(), user, a["id"], pid))
    db.audit(user, "discovery_approve", a["id"], {"ip": p["ip"], "mac": p["mac"]})
    return a
