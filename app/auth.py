"""Kullanıcılar, oturumlar ve rol tabanlı yetki (RBAC)."""
import hashlib
import hmac
import secrets
import time

from . import db

ROLES = {
    "admin": "Sistem Yöneticisi",
    "manager": "BİM Yöneticisi",
    "operator": "Envanter Operatörü",
    "auditor": "Denetçi",
    "viewer": "Görüntüleyici",
}

PERMS = {
    "asset.read": {"admin", "manager", "operator", "auditor", "viewer"},
    "asset.write": {"admin", "manager", "operator"},
    "asset.archive": {"admin", "manager"},
    "import": {"admin", "manager"},
    "export": {"admin", "manager", "operator", "auditor"},
    "print": {"admin", "manager", "operator"},
    "fields": {"admin", "manager"},
    "labels": {"admin", "manager"},
    "audit": {"admin", "manager", "auditor"},
    "users": {"admin"},
    "settings": {"admin"},
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


def has_users() -> bool:
    return db.conn().execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def create_user(username, password, role="viewer", full_name=None) -> dict:
    if role not in ROLES:
        raise ValueError("Geçersiz rol")
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("Kullanıcı adı en az 3 karakter olmalı")
    validate_pw(password)
    if db.conn().execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise ValueError("Bu kullanıcı adı zaten var")
    cur = db.conn().execute("INSERT INTO users(username,full_name,role,pw_hash,created_at) VALUES(?,?,?,?,?)",
                            (username, full_name, role, hash_pw(password), db.now()))
    return get_user(cur.lastrowid)


def _pub(r) -> dict:
    d = dict(r)
    d.pop("pw_hash", None)
    d["active"] = bool(d["active"])
    d["role_name"] = ROLES.get(d["role"], d["role"])
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
    if "full_name" in patch:
        c.execute("UPDATE users SET full_name=? WHERE id=?", (patch["full_name"], uid))
    if patch.get("password"):
        validate_pw(patch["password"])
        c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(patch["password"]), uid))
        c.execute("DELETE FROM sessions WHERE user_id=? AND user_id<>?", (uid, actor_id or -1))
    return get_user(uid)


def _admin_count():
    return db.conn().execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]


_fails: dict[str, list[float]] = {}


def login(username, password, ip="?") -> tuple[str, dict]:
    key = f"{ip}|{(username or '').lower()}"
    recent = [t for t in _fails.get(key, []) if t > time.time() - 300]
    if len(recent) >= 8:
        raise PermissionError("Çok fazla hatalı deneme. 5 dakika sonra tekrar deneyin.")
    r = db.conn().execute("SELECT * FROM users WHERE username=? AND active=1", (username or "",)).fetchone()
    if not r or not check_pw(password or "", r["pw_hash"]):
        _fails[key] = recent + [time.time()]
        raise PermissionError("Kullanıcı adı veya parola hatalı")
    _fails.pop(key, None)
    token = secrets.token_urlsafe(32)
    c = db.conn()
    c.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
    c.execute("INSERT INTO sessions VALUES(?,?,?)", (token, r["id"], time.time() + SESSION_TTL))
    c.execute("UPDATE users SET last_login=? WHERE id=?", (db.now(), r["id"]))
    return token, _pub(r)


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
