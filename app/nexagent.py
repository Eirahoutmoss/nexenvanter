"""NexAgent entegrasyonu: imzalı (ECDSA P-256) çağrılar, sabitlenmiş TLS parmak izi, çekme (pull) işleri,
ayar eşitleme, kurulum paketi üretimi. Ajan ikilisi: agent/ klasöründeki C# projesi."""
import base64
import hashlib
import http.client
import io
import json
import os
import secrets
import socket
import ssl
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import agent as AG, db
from .paths import DIRS

PROTO = "NEX1"
MODULES = [
    ("system", "Sistem, BIOS, seri no, işletim sistemi"), ("cpu", "İşlemci"), ("memory", "Bellek ve modüller"),
    ("storage", "Diskler ve bölümler"), ("gpu", "Ekran kartı"), ("display", "Monitörler (seri no dahil)"),
    ("network", "Ağ kartları, IP, MAC"), ("software", "Kurulu programlar"), ("printers", "Yazıcılar"),
    ("security", "Güvenlik (antivirüs, güvenlik duvarı, BitLocker, TPM)"), ("updates", "Windows güncellemeleri"),
    ("usb", "USB aygıtları"), ("admins", "Yerel yöneticiler"),
]
DEFAULT_MODULES = {k: k not in ("usb", "admins") for k, _ in MODULES}
DEFAULTS = {"port": 47820, "sources": [], "interval_minutes": 360, "software_max": 800, "modules": DEFAULT_MODULES,
            "uninstall_hash": None, "server_name": "", "pull_on_start": True, "pull_hours": 6, "workers": 16}

STATE = {"running": False, "kind": "", "progress": "", "done": 0, "total": 0, "last_run": None, "last_result": None}
_lock = threading.Lock()


class AgentError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


class FingerprintMismatch(AgentError):
    def __init__(self, fp):
        super().__init__("Sertifika parmak izi değişti", 0)
        self.fp = fp


# ------------------------------------------------------------------ ayarlar
def local_ips() -> list[str]:
    """Bu sunucunun yerel IPv4 adresleri (ajanın izinli kaynak listesi için otomatik öneri)."""
    import socket
    found: list[str] = []
    try:  # varsayılan rotanın çıkış adresi
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 9))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(ai[4][0])
    except OSError:
        pass
    out = []
    for ip in found:
        if ip.startswith(("127.", "169.254.", "0.")) or ip in out:
            continue
        out.append(ip)
    return out


def cfg() -> dict:
    out = json.loads(json.dumps(DEFAULTS))
    r = db.conn().execute("SELECT value FROM nexagent_cfg WHERE key='cfg'").fetchone()
    if r:
        saved = json.loads(r[0])
        out.update({k: v for k, v in saved.items() if k != "modules"})
        out["modules"].update(saved.get("modules") or {})
    if not out["sources"]:  # elle girilmediyse sunucunun kendi adreslerini kullan (kaydedilmez)
        out["sources"] = [f"{ip}/32" for ip in local_ips()]
    return out


def cfg_save(c: dict):
    db.conn().execute("INSERT INTO nexagent_cfg VALUES('cfg',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (json.dumps(c, ensure_ascii=False),))


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000, 32)
    return f"pbkdf2-sha256$200000${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def update_cfg(user: str, d: dict) -> dict:
    c = cfg()
    if "port" in d:
        p = int(d["port"])
        if not 1024 <= p <= 65535:
            raise ValueError("Port 1024–65535 arasında olmalı")
        c["port"] = p
    if "sources" in d:
        import ipaddress
        src = [str(s).strip() for s in d["sources"] if str(s).strip()]
        for s in src:
            try:
                ipaddress.ip_network(s, strict=False)
            except ValueError:
                raise ValueError(f"Geçersiz kaynak adres: {s}")
        c["sources"] = src
    for k, lo, hi in (("interval_minutes", 15, 10080), ("software_max", 0, 5000), ("pull_hours", 0, 168), ("workers", 1, 64)):
        if k in d:
            v = int(float(d[k]))
            if not lo <= v <= hi:
                raise ValueError(f"{k}: {lo}–{hi} arasında olmalı")
            c[k] = v
    if "modules" in d:
        c["modules"].update({k: bool(v) for k, v in d["modules"].items() if k in DEFAULT_MODULES})
    if "pull_on_start" in d:
        c["pull_on_start"] = bool(d["pull_on_start"])
    if "server_name" in d:
        c["server_name"] = str(d["server_name"])[:80]
    if d.get("uninstall_password"):
        if len(d["uninstall_password"]) < 6:
            raise ValueError("Kaldırma parolası en az 6 karakter olmalı")
        c["uninstall_hash"] = hash_password(d["uninstall_password"])
    if d.get("clear_uninstall_password"):
        c["uninstall_hash"] = None
    cfg_save(c)
    db.audit(user, "nexagent_settings", None, {k: v for k, v in d.items() if "password" not in k})
    return c


# ------------------------------------------------------------------ anahtarlar
_key = None


def _priv():
    global _key
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    with _lock:
        if _key is None:
            f = DIRS.data / "nexagent" / "signing.pem"
            if f.exists():
                _key = serialization.load_pem_private_key(f.read_bytes(), None)
            else:
                f.parent.mkdir(parents=True, exist_ok=True)
                _key = ec.generate_private_key(ec.SECP256R1())
                f.write_bytes(_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()))
                try:
                    os.chmod(f, 0o600)
                except OSError:
                    pass
        return _key


def public_b64() -> str:
    from cryptography.hazmat.primitives import serialization
    return base64.b64encode(_priv().public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()


def sign_headers(method: str, target: str, agent_id: str, body: bytes) -> dict:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    msg = f"{PROTO}\n{method}\n{target}\n{agent_id}\n{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
    sig = _priv().sign(msg.encode(), ec.ECDSA(hashes.SHA256()))  # DER
    return {"X-Nex-Ts": ts, "X-Nex-Nonce": nonce, "X-Nex-Agent": agent_id, "X-Nex-Sig": base64.b64encode(sig).decode()}


# ------------------------------------------------------------------ ağ
class _Conn(http.client.HTTPSConnection):
    expected: str | None = None
    peer_fp: str | None = None

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self.sock = ctx.wrap_socket(sock, server_hostname=self.host)
        self.peer_fp = hashlib.sha256(self.sock.getpeercert(True)).hexdigest()
        if self.expected and self.peer_fp != self.expected:
            self.sock.close()
            raise FingerprintMismatch(self.peer_fp)


def _request(addr, port, method, target, headers, body, timeout, expected_fp):
    c = _Conn(addr, int(port), timeout=timeout)
    c.expected = expected_fp
    try:
        c.request(method, target, body=body or None, headers=headers)
        r = c.getresponse()
        data = r.read(8 * 1024 * 1024)
        return r.status, {k.lower(): v for k, v in r.getheaders()}, data, c.peer_fp
    except FingerprintMismatch:
        raise
    except (OSError, http.client.HTTPException, ssl.SSLError) as e:
        raise AgentError(f"bağlanılamadı: {e}") from e
    finally:
        c.close()


def hello(addr, port, timeout=3.0):
    st, _, data, fp = _request(addr, port, "GET", "/v1/hello", {}, b"", timeout, None)
    if st != 200:
        raise AgentError(f"hello {st}", st)
    j = json.loads(data)
    if j.get("proto") != 1 or not j.get("agentId"):
        raise AgentError("NexAgent değil")
    return j, fp


def call(node: dict, method: str, target: str, payload=None, timeout=15.0, trust=False, etag=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    h = sign_headers(method, target, node["agent_id"], body)
    if body:
        h["Content-Type"] = "application/json"
    if etag:
        h["If-None-Match"] = etag
    st, rh, data, fp = _request(node["address"], node["port"], method, target, h, body, timeout,
                                None if trust or not node.get("fingerprint") else node["fingerprint"])
    j = None
    if data:
        try:
            j = json.loads(data)
        except ValueError:
            j = None
    if st >= 400:
        raise AgentError((j or {}).get("error") or f"HTTP {st}", st)
    return {"status": st, "json": j, "etag": rh.get("etag"), "fp": fp}


# ------------------------------------------------------------------ düğümler
def nodes(include_removed=True) -> list[dict]:
    q = ("SELECT n.*, a.asset_code FROM nexagent_nodes n LEFT JOIN assets a ON a.id=n.asset_id"
         + ("" if include_removed else " WHERE n.state!='kaldırıldı'") + " ORDER BY lower(coalesce(n.hostname,n.address))")
    out = []
    for r in db.conn().execute(q):
        d = dict(r)
        d["override"] = json.loads(d.pop("override") or "null")
        d["config"] = json.loads(d["config"] or "null")
        out.append(d)
    return out


def node(agent_id: str) -> dict | None:
    r = db.conn().execute("SELECT n.*, a.asset_code FROM nexagent_nodes n LEFT JOIN assets a ON a.id=n.asset_id "
                          "WHERE n.agent_id=?", (agent_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["override"] = json.loads(d.pop("override") or "null")
    d["config"] = json.loads(d["config"] or "null")
    return d


def _set(agent_id: str, **kw):
    cols = ", ".join(f"{k}=?" for k in kw)
    db.conn().execute(f"UPDATE nexagent_nodes SET {cols} WHERE agent_id=?", (*kw.values(), agent_id))


def snapshot(agent_id: str) -> dict | None:
    r = db.conn().execute("SELECT at, data FROM nexagent_snapshots WHERE agent_id=?", (agent_id,)).fetchone()
    return {"at": r[0], **json.loads(r[1])} if r else None


def for_asset(asset_id: int) -> dict | None:
    r = db.conn().execute("SELECT agent_id FROM nexagent_nodes WHERE asset_id=? AND state!='kaldırıldı' "
                          "ORDER BY last_seen DESC LIMIT 1", (asset_id,)).fetchone()
    if not r:
        return None
    n = node(r[0])
    return {"node": n, "snapshot": snapshot(r[0])}


def desired(n: dict) -> dict:
    """Ajana gönderilecek istenen yapılandırma (genel ayar + cihaz özel ayarı)."""
    c = cfg()
    d = {"modules": dict(c["modules"]), "intervalMinutes": c["interval_minutes"], "softwareMax": c["software_max"],
         "serverName": c["server_name"]}
    ov = n.get("override") or {}
    d["modules"].update({k: bool(v) for k, v in (ov.get("modules") or {}).items() if k in DEFAULT_MODULES})
    if ov.get("interval_minutes"):
        d["intervalMinutes"] = int(ov["interval_minutes"])
    if c["sources"]:
        d["allowedSources"] = c["sources"]
    if c["uninstall_hash"]:
        d["uninstallHash"] = c["uninstall_hash"]
    else:
        d["clearUninstallHash"] = True
    return d


def _hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def alt_addresses(n: dict) -> list[str]:
    """IP değişmiş olabilir (DHCP): envanter kaydındaki IP ve ağ taramasındaki aynı MAC/ad."""
    out = []
    macs = []
    snap = snapshot(n["agent_id"])
    if snap:
        macs = [x.get("mac") for x in (snap.get("modules", {}).get("network") or []) if x.get("mac")]
    for m in macs:
        for r in db.conn().execute("SELECT ip FROM net_hosts WHERE mac=? ORDER BY last_seen DESC LIMIT 2", (m,)):
            out.append(r[0])
    if n.get("asset_id"):
        r = db.conn().execute("SELECT json_extract(data,'$.ip_address') FROM assets WHERE id=?", (n["asset_id"],)).fetchone()
        for x in str(r[0] or "").replace(";", ",").split(","):
            out.append(x.strip())
    seen = []
    for a in out:
        if a and a != n["address"] and a not in seen:
            seen.append(a)
    return seen[:4]


def _call_resolving(n: dict, method, target, payload=None, timeout=15.0, etag=None):
    try:
        return call(n, method, target, payload, timeout, etag=etag)
    except FingerprintMismatch:
        raise
    except AgentError as e:
        if e.status:
            raise
        for a in alt_addresses(n):  # bağlantı kurulamadı → olası yeni IP'leri dene
            try:
                j, _ = hello(a, n["port"], 2.0)
                if j["agentId"].lower() == n["agent_id"].lower():
                    n = {**n, "address": a}
                    r = call(n, method, target, payload, timeout, etag=etag)
                    _set(n["agent_id"], address=a)
                    return r
            except AgentError:
                continue
        raise


# ------------------------------------------------------------------ rapora dönüştürme
def to_report(inv: dict) -> dict:
    m = inv.get("modules") or {}
    s, cpu, mem, st = (m.get(k) or {} for k in ("system", "cpu", "memory", "storage"))
    os_ = s.get("os") or {}
    net = [x for x in (m.get("network") or []) if not x.get("virtual")]
    ram = round((mem.get("totalBytes") or 0) / 1024 ** 3) or None
    disks = "; ".join(f"{(d.get('model') or '').strip()} {round((d.get('sizeBytes') or 0) / 1e9)}GB"
                      for d in st.get("disks", []) if d.get("model"))
    return {"hostname": s.get("hostname") or inv.get("hostname"), "serial": s.get("serial"),
            "manufacturer": s.get("manufacturer"), "model": s.get("model"), "cpu": cpu.get("name"), "ram_gb": ram,
            "disk": disks, "os": f"{os_.get('caption') or ''} {os_.get('version') or ''}".strip(),
            "user": s.get("lastUser") or "", "macs": [x["mac"] for x in net if x.get("mac")],
            "ips": [i for x in net for i in x.get("ips", [])]}


# ------------------------------------------------------------------ çekme
def pull_node(agent_id: str, fresh=False, user="sistem") -> dict:
    n = node(agent_id)
    if not n:
        raise KeyError(agent_id)
    now = db.now()
    try:
        want = desired(n)
        h = _hash(want)
        applied = (n["config"] or {}).get("applied")
        if applied != h:
            _call_resolving(n, "PUT", "/v1/config", want)
            n["config"] = {**(n["config"] or {}), "applied": h}
            _set(agent_id, config=json.dumps(n["config"]))
            fresh = True
            n = node(agent_id)
        target = "/v1/inventory" + ("?fresh=1" if fresh else "")
        r = _call_resolving(n, "GET", target, timeout=60.0 if fresh else 20.0, etag=None if fresh else n.get("etag"))
        n = node(agent_id)
        if r["status"] == 304:
            _set(agent_id, last_seen=now, last_try=now, state="çevrimiçi", fail_count=0, last_error=None)
            return {"agent_id": agent_id, "unchanged": True}
        inv = r["json"] or {}
        asset_id = None
        rep = to_report(inv)
        if rep.get("hostname"):
            res = AG.report(rep, n["address"])
            asset_id = res.get("asset_id")
        db.conn().execute("INSERT INTO nexagent_snapshots VALUES(?,?,?) ON CONFLICT(agent_id) DO UPDATE SET at=excluded.at, data=excluded.data",
                          (agent_id, now, json.dumps({k: inv.get(k) for k in ("modules", "errors", "collectedAt", "durationMs", "agentVersion", "configVersion")},
                                                     ensure_ascii=False)))
        _set(agent_id, last_seen=now, last_try=now, state="çevrimiçi", fail_count=0, last_error=None,
             hostname=rep.get("hostname") or n.get("hostname"), version=inv.get("agentVersion"), etag=r.get("etag"),
             collected_at=inv.get("collectedAt"), asset_id=n["asset_id"] or asset_id)
        return {"agent_id": agent_id, "ok": True, "asset_id": asset_id}
    except FingerprintMismatch as e:
        _set(agent_id, last_try=now, state="parmak izi", pending_fp=e.fp,
             last_error="Ajanın sertifikası değişti (yeniden kurulum olabilir). Doğruysa onaylayın.")
        raise
    except AgentError as e:
        f = (n.get("fail_count") or 0) + 1
        _set(agent_id, last_try=now, fail_count=f, last_error=str(e)[:300], state="çevrimdışı" if f >= 2 else n["state"])
        raise


def pull_one(agent_id, fresh=False, user="sistem"):
    try:
        return pull_node(agent_id, fresh, user)
    except Exception as e:  # noqa: BLE001
        return {"agent_id": agent_id, "error": str(e)}


def _job(kind, fn):
    with _lock:
        if STATE["running"]:
            return False
        STATE.update(running=True, kind=kind, progress="başlıyor", done=0, total=0)

    def run():
        t0 = time.time()
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            res = {"errors": [str(e)]}
        res["seconds"] = round(time.time() - t0, 1)
        res["at"] = db.now()
        STATE.update(running=False, progress="", last_run=db.now(), last_result=res)
    threading.Thread(target=run, daemon=True, name="nexagent-" + kind).start()
    return True


def pull_all(ids=None, fresh=False, user="sistem") -> bool:
    def fn():
        ns = [n for n in nodes(False) if not ids or n["agent_id"] in ids]
        STATE["total"] = len(ns)
        ok = err = same = 0
        errors = []
        with ThreadPoolExecutor(cfg()["workers"]) as ex:
            for r in ex.map(lambda n: pull_one(n["agent_id"], fresh, user), ns):
                STATE["done"] += 1
                STATE["progress"] = f"{STATE['done']}/{STATE['total']}"
                if r.get("error"):
                    err += 1
                    errors.append(f"{r['agent_id'][:8]}: {r['error']}")
                elif r.get("unchanged"):
                    same += 1
                else:
                    ok += 1
        db.audit(user, "nexagent_pull", None, {"ok": ok, "unchanged": same, "error": err})
        return {"ok": ok, "unchanged": same, "failed": err, "errors": errors[:20]}
    return _job("pull", fn)


# ------------------------------------------------------------------ keşif
def _candidates(targets: list[str]) -> list[str]:
    from . import network
    ips = []
    if targets:
        for t in network.parse_targets(targets):
            ips += t["hosts"]
    else:
        since = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
        ips += [r[0] for r in db.conn().execute("SELECT ip FROM net_hosts WHERE last_seen>=?", (since,))]
        for r in db.conn().execute("SELECT json_extract(data,'$.ip_address') FROM assets WHERE archived=0"):
            for x in str(r[0] or "").replace(";", ",").split(","):
                ips.append(x.strip())
    out, seen = [], set()
    for i in ips:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _probe(ip: str, port: int):
    try:
        socket.create_connection((ip, port), 1.0).close()
    except OSError:
        return None
    try:
        j, fp = hello(ip, port, 3.0)
        return ip, j, fp
    except AgentError:
        return None


def discover(targets=None, user="sistem") -> bool:
    def fn():
        port = cfg()["port"]
        ips = _candidates(targets or [])
        STATE["total"] = len(ips)
        found = new = foreign = changed = 0
        added = []
        with ThreadPoolExecutor(96) as ex:
            for r in ex.map(lambda i: _probe(i, port), ips):
                STATE["done"] += 1
                STATE["progress"] = f"{STATE['done']}/{STATE['total']}"
                if not r:
                    continue
                ip, j, fp = r
                found += 1
                aid = j["agentId"]
                cur = node(aid)
                probe = {"agent_id": aid, "address": ip, "port": port, "fingerprint": cur["fingerprint"] if cur else None}
                try:
                    st = call(probe, "GET", "/v1/status", timeout=8.0, trust=not probe["fingerprint"])
                except FingerprintMismatch as e:
                    if cur:
                        _set(aid, address=ip, state="parmak izi", pending_fp=e.fp)
                    changed += 1
                    continue
                except AgentError:
                    foreign += 1   # başka bir sunucuya ait ya da yanıt vermiyor
                    continue
                s = st["json"] or {}
                if cur:
                    _set(aid, address=ip, port=port, fingerprint=cur["fingerprint"] or st["fp"], hostname=s.get("hostname"),
                         version=s.get("version"), os=s.get("os"), last_seen=db.now(), state="çevrimiçi", fail_count=0, last_error=None)
                else:
                    db.conn().execute("INSERT INTO nexagent_nodes(agent_id,address,port,fingerprint,hostname,version,os,state,first_seen,last_seen) "
                                      "VALUES(?,?,?,?,?,?,?,'çevrimiçi',?,?)",
                                      (aid, ip, port, st["fp"], s.get("hostname"), s.get("version"), s.get("os"), db.now(), db.now()))
                    new += 1
                    added.append(aid)
        for aid in added:   # yeni ajanların ilk verisini hemen al
            pull_one(aid, True, user)
        db.audit(user, "nexagent_discover", None, {"found": found, "new": new})
        return {"scanned": len(ips), "found": found, "new": new, "foreign": foreign, "fingerprint_changed": changed}
    return _job("discover", fn)


# ------------------------------------------------------------------ yönetim
def accept_fingerprint(agent_id: str, user: str):
    n = node(agent_id)
    if not n or not n.get("pending_fp"):
        raise ValueError("Onaylanacak yeni parmak izi yok")
    _set(agent_id, fingerprint=n["pending_fp"], pending_fp=None, state="yeni", last_error=None)
    db.audit(user, "nexagent_fingerprint", agent_id)


def forget(agent_id: str, user: str):
    db.conn().execute("DELETE FROM nexagent_nodes WHERE agent_id=?", (agent_id,))
    db.conn().execute("DELETE FROM nexagent_snapshots WHERE agent_id=?", (agent_id,))
    db.audit(user, "nexagent_forget", agent_id)


def set_override(agent_id: str, ov: dict | None, user: str):
    clean = None
    if ov:
        clean = {}
        if ov.get("modules"):
            clean["modules"] = {k: bool(v) for k, v in ov["modules"].items() if k in DEFAULT_MODULES}
        if ov.get("interval_minutes"):
            clean["interval_minutes"] = max(15, min(10080, int(ov["interval_minutes"])))
    _set(agent_id, override=json.dumps(clean) if clean else None)
    db.audit(user, "nexagent_override", agent_id, clean)


def remote_uninstall(agent_id: str, user: str, ip=None):
    n = node(agent_id)
    if not n:
        raise KeyError(agent_id)
    _call_resolving(n, "POST", "/v1/uninstall", {"confirm": agent_id}, 10.0)
    _set(agent_id, state="kaldırıldı", last_error=None)
    db.audit(user, "nexagent_uninstall", agent_id, {"host": n.get("hostname")}, ip=ip)


def link(agent_id: str, asset_id: int, user: str):
    n = node(agent_id)
    if not n:
        raise KeyError(agent_id)
    _set(agent_id, asset_id=asset_id)
    if n.get("hostname"):
        try:
            AG.link(n["hostname"], asset_id, None, user)
        except KeyError:
            pass
    db.audit(user, "nexagent_link", agent_id, {"asset_id": asset_id})


# ------------------------------------------------------------------ paket
def bins_dir():
    d = DIRS.data / "agent_bins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def available_bins() -> list[dict]:
    out = []
    for f in sorted(bins_dir().iterdir()):
        if f.is_file():
            out.append({"name": f.name, "size": f.stat().st_size})
    return out


def find_bin(os_: str, arch: str):
    key = f"{os_}-{arch}".lower()
    for f in sorted(bins_dir().iterdir(), reverse=True):
        if f.is_file() and key in f.name.lower():
            return f
    return None


def fetch_bins_from_github() -> list[str]:
    """Son GitHub sürümündeki NexAgent-*-{win|linux}-* dosyalarını indirir."""
    from . import updater
    with updater._get(updater.API) as r:
        rel = json.load(r)
    got = []
    for a in rel.get("assets", []):
        nm = a["name"].lower()
        if nm.startswith("nexagent-") and ("win" in nm or "linux" in nm):
            dest = bins_dir() / a["name"]
            with updater._get(a["browser_download_url"], timeout=180) as r, open(dest, "wb") as f:
                while chunk := r.read(1 << 16):
                    f.write(chunk)
            got.append(a["name"])
    return got


def enroll_json() -> dict:
    c = cfg()
    if not c["sources"]:
        raise ValueError("İzinli kaynak adres (bu Envanter sunucusunun IP'si) tanımlı değil — Ayarlar bölümünden ekleyin")
    return {"serverName": c["server_name"], "publicKey": public_b64(), "port": c["port"], "allowedSources": c["sources"],
            "uninstallHash": c["uninstall_hash"], "intervalMinutes": c["interval_minutes"], "modules": c["modules"]}


GUIDE_WIN = """NexAgent kurulumu (Windows)
1) Bu klasörü bilgisayara kopyalayın (NexAgent.exe ve enroll.json aynı klasörde olmalı).
2) Yönetici olarak çalıştırın:   NexAgent.exe install
   Sessiz kurulum:                NexAgent.exe install --password KALDIRMA_PAROLASI
   (Parola verilmezse Envanter'deki ortak kaldırma parolası kullanılır.)
3) Doğrulama:                     NexAgent.exe status
Kaldırma: Ayarlar > Uygulamalar > NexAgent (parola sorar) ya da Envanter > Ağ & Ajan > Kaldır.
"""
GUIDE_LINUX = """NexAgent kurulumu (Linux)
1) nexagent ve enroll.json dosyalarını aynı klasöre koyun.   chmod +x nexagent
2) sudo ./nexagent install        (sessiz: sudo ./nexagent install --password KALDIRMA_PAROLASI)
3) Doğrulama: sudo ./nexagent status
Kaldırma: sudo /opt/nexagent/nexagent uninstall   ya da Envanter > Ağ & Ajan > Kaldır.
"""


def build_package(os_: str, arch: str) -> tuple[bytes, str]:
    b = find_bin(os_, arch)
    if not b:
        raise ValueError(f"{os_}-{arch} için ajan dosyası yok. “GitHub'dan indir” ile alın ya da {bins_dir()} klasörüne koyun.")
    en = enroll_json()
    buf = io.BytesIO()
    exe = "NexAgent.exe" if os_ == "win" else "nexagent"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        zi = zipfile.ZipInfo(exe)
        zi.external_attr = 0o755 << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, b.read_bytes())
        z.writestr("enroll.json", json.dumps(en, indent=2, ensure_ascii=False))
        z.writestr("KURULUM.txt", GUIDE_WIN if os_ == "win" else GUIDE_LINUX)
    return buf.getvalue(), f"NexAgent-kurulum-{os_}-{arch}.zip"


# ------------------------------------------------------------------ zamanlayıcı
def scheduler():
    def loop():
        time.sleep(45)
        try:
            if cfg()["pull_on_start"] and nodes(False):
                pull_all(user="başlangıç")
        except Exception:
            pass
        while True:
            time.sleep(300)
            try:
                h = cfg()["pull_hours"]
                last = STATE["last_run"]
                if h > 0 and not STATE["running"] and (not last or datetime.fromisoformat(last) < datetime.now() - timedelta(hours=h)):
                    pull_all(user="zamanlayıcı")
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="nexagent-sched").start()


def overview() -> dict:
    c = cfg()
    ns = nodes()
    by = {}
    for n in ns:
        by[n["state"]] = by.get(n["state"], 0) + 1
    return {"cfg": {**c, "uninstall_protected": bool(c["uninstall_hash"]), "uninstall_hash": None},
            "modules": [{"key": k, "label": l} for k, l in MODULES], "nodes": ns, "counts": by, "state": STATE,
            "public_key_fp": hashlib.sha256(base64.b64decode(public_b64())).hexdigest()[:16],
            "bins": available_bins(), "bins_dir": str(bins_dir())}
