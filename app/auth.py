"""Kullanıcılar, oturumlar, API anahtarları, Active Directory (LDAP) girişi ve rol tabanlı yetki (RBAC)."""
import hashlib
import hmac
import json
import secrets
import time

from . import db
from .textnorm import fold

ROLES = {
    "admin": "Sistem Yöneticisi",
    "manager": "BİM Yöneticisi",
    "operator": "Envanter Operatörü",
    "auditor": "Denetçi",
    "unit_rep": "Birim Envanter Temsilcisi",
    "viewer": "Görüntüleyici",
}

_ALL = set(ROLES)
_STAFF = {"admin", "manager", "operator"}
PERMS = {
    "asset.read": _ALL,
    "asset.write": _STAFF,
    "asset.archive": {"admin", "manager"},
    "import": {"admin", "manager"},
    "export": _STAFF | {"auditor"},
    "print": _STAFF,
    "fields": {"admin", "manager"},
    "labels": {"admin", "manager"},
    "audit": {"admin", "manager", "auditor"},
    "users": {"admin"},
    "settings": {"admin"},
    "tokens": {"admin"},
    "federation": {"admin", "manager"},
    "ticket.create": _ALL,
    "ticket.read": _ALL,
    "ticket.manage": _STAFF,
    "count": _STAFF | {"unit_rep"},
    "count.manage": {"admin", "manager"},
    "assign": _STAFF,
    "maint": _STAFF,
    "stock.read": _ALL - {"unit_rep"},
    "stock": _STAFF,
    "kb.read": _ALL,
    "kb.write": _STAFF,
    "network": {"admin", "manager"},
    "reports": {"admin", "manager", "auditor"},
}

SESSION_TTL = 12 * 3600
_ITER = 240_000


def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${h.hex()}"


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


def validate_pw(pw: str):
    if not pw or len(pw) < 8:
        raise ValueError("Parola en az 8 karakter olmalı")


def can(user: dict | None, perm: str) -> bool:
    return bool(user) and user["role"] in PERMS.get(perm, set())


def perms_of(role: str) -> list[str]:
    return sorted(p for p, roles in PERMS.items() if role in roles)


def scope(user: dict | None) -> list[str] | None:
    """Birim temsilcisi yalnızca kendi birim(ler)ini görür. None = kısıtsız."""
    if user and user["role"] == "unit_rep":
        return user.get("units") or ["\x00"]  # birimi atanmamış temsilci hiçbir şey görmez
    return None


def in_scope(user, location) -> bool:
    sc = scope(user)
    return sc is None or fold(location or "") in {fold(u) for u in sc}


def has_users() -> bool:
    return db.conn().execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def create_user(username, password, role="viewer", full_name=None, units=None, email=None, source="local") -> dict:
    if role not in ROLES:
        raise ValueError("Geçersiz rol")
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("Kullanıcı adı en az 3 karakter olmalı")
    if source == "local":
        validate_pw(password)
    if db.conn().execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise ValueError("Bu kullanıcı adı zaten var")
    cur = db.conn().execute(
        "INSERT INTO users(username,full_name,role,pw_hash,created_at,units,email,source) VALUES(?,?,?,?,?,?,?,?)",
        (username, full_name, role, hash_pw(password) if source == "local" else "!", db.now(),
         json.dumps(units or [], ensure_ascii=False), email, source))
    return get_user(cur.lastrowid)


def _pub(r) -> dict:
    d = dict(r)
    d.pop("pw_hash", None)
    d["active"] = bool(d["active"])
    d["role_name"] = ROLES.get(d["role"], d["role"])
    d["units"] = json.loads(d.get("units") or "[]")
    return d


def get_user(uid) -> dict | None:
    r = db.conn().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return _pub(r) if r else None


def list_users() -> list[dict]:
    return [_pub(r) for r in db.conn().execute("SELECT * FROM users ORDER BY username")]


def update_user(uid, patch: dict, actor_id=None) -> dict:
    u = get_user(uid)
    if not u:
        raise ValueError("Kullanıcı bulunamadı")
    c = db.conn()
    if "role" in patch:
        if patch["role"] not in ROLES:
            raise ValueError("Geçersiz rol")
        if u["role"] == "admin" and patch["role"] != "admin" and _admin_count() <= 1:
            raise ValueError("Son yönetici hesabının rolü değiştirilemez")
        c.execute("UPDATE users SET role=? WHERE id=?", (patch["role"], uid))
    if "active" in patch:
        if not patch["active"] and (uid == actor_id or (u["role"] == "admin" and _admin_count() <= 1)):
            raise ValueError("Bu hesap pasifleştirilemez")
        c.execute("UPDATE users SET active=? WHERE id=?", (int(bool(patch["active"])), uid))
        if not patch["active"]:
            c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    for k in ("full_name", "email"):
        if k in patch:
            c.execute(f"UPDATE users SET {k}=? WHERE id=?", (patch[k], uid))
    if "units" in patch:
        units = [s.strip() for s in patch["units"] if s and s.strip()] if isinstance(patch["units"], list) else []
        c.execute("UPDATE users SET units=? WHERE id=?", (json.dumps(units, ensure_ascii=False), uid))
    if patch.get("password"):
        if u["source"] != "local":
            raise ValueError("Active Directory kullanıcısının parolası buradan değiştirilemez")
        validate_pw(patch["password"])
        c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(patch["password"]), uid))
        c.execute("DELETE FROM sessions WHERE user_id=? AND user_id<>?", (uid, actor_id or -1))
    return get_user(uid)


def _admin_count():
    return db.conn().execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]


# ---------------- Active Directory / LDAP ----------------
def _ldap_connection(cfg, user, password):
    """Testlerde değiştirilebilir bağlantı üreticisi."""
    from ldap3 import Connection, Server
    srv = Server(cfg["server"], use_ssl=bool(cfg.get("use_ssl")), connect_timeout=5)
    return Connection(srv, user=user, password=password, auto_bind=True, receive_timeout=10, raise_exceptions=False)


def ldap_authenticate(username: str, password: str) -> dict | None:
    """Başarılıysa {'full_name','email','groups'} döner; değilse None."""
    cfg = db.get_setting("ldap") or {}
    if not cfg.get("enabled") or not cfg.get("server") or not password:  # boş parola = anonim bind, reddet
        return None
    from ldap3.utils.conv import escape_filter_chars
    sam = username.split("@")[0].split("\\")[-1]
    upn = username if "@" in username else f"{sam}@{cfg.get('domain', '')}"
    try:
        c = _ldap_connection(cfg, upn, password)
    except Exception:
        return None
    if not c.bound:
        return None
    try:
        info = {"full_name": sam, "email": None, "groups": []}
        if cfg.get("base_dn"):
            flt = f"(|(userPrincipalName={escape_filter_chars(upn)})(sAMAccountName={escape_filter_chars(sam)}))"
            c.search(cfg["base_dn"], flt, attributes=["displayName", "mail", "memberOf"])
            if c.entries:
                e = c.entries[0]
                info["full_name"] = str(e.displayName) if "displayName" in e and e.displayName.value else sam
                info["email"] = str(e.mail) if "mail" in e and e.mail.value else None
                info["groups"] = [str(g) for g in (e.memberOf.values if "memberOf" in e else [])]
        return info
    finally:
        try:
            c.unbind()
        except Exception:
            pass


def ldap_role(groups: list[str]) -> tuple[str | None, list[str]]:
    """Grup → rol eşlemesi: ayarlardaki sıraya göre ilk eşleşen kazanır."""
    cfg = db.get_setting("ldap") or {}
    gf = [fold(g) for g in groups]
    for m in cfg.get("role_map") or []:
        key = fold(m.get("group", ""))
        if key and any(key in g for g in gf) and m.get("role") in ROLES:
            return m["role"], m.get("units") or []
    return (cfg.get("default_role", "viewer"), []) if cfg.get("allow_unmapped") else (None, [])


def _ldap_login(username, password):
    info = ldap_authenticate(username, password)
    if not info:
        return None
    role, units = ldap_role(info["groups"])
    if not role:
        raise PermissionError("Active Directory hesabınız NexEnvanter grubunda değil")
    sam = username.split("@")[0].split("\\")[-1]
    c = db.conn()
    r = c.execute("SELECT * FROM users WHERE username=?", (sam,)).fetchone()
    if r is None:
        create_user(sam, None, role, info["full_name"], units, info["email"], source="ldap")
    elif r["source"] == "ldap":
        c.execute("UPDATE users SET role=?, full_name=?, email=?, units=CASE WHEN ?='[]' THEN units ELSE ? END WHERE id=?",
                  (role, info["full_name"], info["email"], json.dumps(units), json.dumps(units, ensure_ascii=False), r["id"]))
    return c.execute("SELECT * FROM users WHERE username=? AND active=1", (sam,)).fetchone()


# ---------------- oturum ----------------
_fails: dict[str, list[float]] = {}


def login(username, password, ip="?") -> tuple[str, dict]:
    key = f"{ip}|{(username or '').lower()}"
    recent = [t for t in _fails.get(key, []) if t > time.time() - 300]
    if len(recent) >= 8:
        raise PermissionError("Çok fazla hatalı deneme. 5 dakika sonra tekrar deneyin.")
    c = db.conn()
    r = c.execute("SELECT * FROM users WHERE username=?", (username or "",)).fetchone()
    ok = None
    if r is not None and r["source"] == "local":
        ok = r if r["active"] and check_pw(password or "", r["pw_hash"]) else None
    elif r is None or r["source"] == "ldap":
        ok = _ldap_login(username or "", password or "")
    if not ok:
        _fails[key] = recent + [time.time()]
        raise PermissionError("Kullanıcı adı veya parola hatalı")
    _fails.pop(key, None)
    token = secrets.token_urlsafe(32)
    c.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
    c.execute("INSERT INTO sessions VALUES(?,?,?)", (token, ok["id"], time.time() + SESSION_TTL))
    c.execute("UPDATE users SET last_login=? WHERE id=?", (db.now(), ok["id"]))
    return token, _pub(ok)


def session_user(token: str | None) -> dict | None:
    if not token:
        return None
    c = db.conn()
    r = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1",
                  (token, time.time())).fetchone()
    if not r:
        return None
    c.execute("UPDATE sessions SET expires=? WHERE token=?", (time.time() + SESSION_TTL, token))  # kayan süre
    return _pub(r)


def logout(token):
    db.conn().execute("DELETE FROM sessions WHERE token=?", (token,))


# ---------------- API anahtarları (entegrasyon, kurumlar paneli) ----------------
def _th(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def create_token(name: str, role: str, by: str) -> dict:
    if role not in ROLES:
        raise ValueError("Geçersiz rol")
    if not (name or "").strip():
        raise ValueError("Anahtar adı gerekli")
    tok = "nxt_" + secrets.token_urlsafe(30)
    cur = db.conn().execute("INSERT INTO api_tokens(name,token_hash,role,created_at,created_by) VALUES(?,?,?,?,?)",
                            (name.strip(), _th(tok), role, db.now(), by))
    return {"id": cur.lastrowid, "name": name.strip(), "role": role, "token": tok}


def list_tokens():
    return [dict(r) for r in db.conn().execute(
        "SELECT id,name,role,created_at,created_by,last_used,active FROM api_tokens ORDER BY id DESC")]


def revoke_token(tid: int):
    db.conn().execute("UPDATE api_tokens SET active=0 WHERE id=?", (tid,))


def token_user(tok: str | None) -> dict | None:
    if not tok or not tok.startswith("nxt_"):
        return None
    c = db.conn()
    r = c.execute("SELECT * FROM api_tokens WHERE token_hash=? AND active=1", (_th(tok),)).fetchone()
    if not r:
        return None
    c.execute("UPDATE api_tokens SET last_used=? WHERE id=?", (db.now(), r["id"]))
    return {"id": None, "username": f"anahtar:{r['name']}", "full_name": r["name"], "role": r["role"],
            "role_name": ROLES.get(r["role"]), "units": [], "token": True, "source": "token", "active": True}
