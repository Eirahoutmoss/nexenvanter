"""Lisans: Ed25519 imzalı lisans dosyası + makine kimliği.

Şu an ENFORCE=False: lisans olmadan tüm özellikler açık (geliştirme/ücretsiz kullanım).
Lisanslı derlemeye geçiş: tools/license_tool.py keygen → çıkan genel anahtarı PUBLIC_KEY'e yaz → ENFORCE=True.
Lisans dosyası: <veri klasörü>/license.nxl  (biçim: base64(json) "." base64(imza))
"""
import base64
import hashlib
import json
import platform
import sys
import uuid
from datetime import date

ENFORCE = False
PUBLIC_KEY = ""  # base64 Ed25519 genel anahtar (32 bayt). Özel anahtar ASLA depoya konmaz.

EDITIONS = {
    "free": {"name": "Ücretsiz", "max_assets": 500, "max_users": 3},
    "standard": {"name": "Standart", "max_assets": 5000, "max_users": 20},
    "pro": {"name": "Pro", "max_assets": None, "max_users": None},
}

_cache = {"mtime": None, "lic": None, "error": None}


def machine_id() -> str:
    raw = None
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        except OSError:
            pass
    if not raw:
        try:
            raw = open("/etc/machine-id").read().strip()
        except OSError:
            raw = f"{platform.node()}|{uuid.getnode()}"
    return hashlib.sha256(f"nexenvanter|{raw}".encode()).hexdigest()[:20].upper()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify(text: str) -> dict:
    """Lisans metnini doğrula; geçerliyse yük sözlüğünü döndür, değilse ValueError."""
    if not PUBLIC_KEY:
        raise ValueError("Bu derlemede lisans doğrulama anahtarı yok")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        body, sig = text.strip().split(".")
        Ed25519PublicKey.from_public_bytes(_b64d(PUBLIC_KEY)).verify(_b64d(sig), body.encode())
        lic = json.loads(_b64d(body))
    except (ValueError, InvalidSignature):
        raise ValueError("Lisans imzası geçersiz")
    if lic.get("machine_id") not in (None, "*", machine_id()):
        raise ValueError("Lisans bu bilgisayara ait değil")
    if lic.get("expires") and date.fromisoformat(lic["expires"]) < date.today():
        raise ValueError(f"Lisans süresi doldu ({lic['expires']})")
    if lic.get("edition") not in EDITIONS:
        raise ValueError("Bilinmeyen lisans türü")
    return lic


def _path():
    from .paths import DIRS
    return DIRS.data / "license.nxl"


def current() -> tuple[dict | None, str | None]:
    p = _path()
    if not p.exists():
        return None, None
    m = p.stat().st_mtime
    if _cache["mtime"] != m:
        try:
            _cache.update(mtime=m, lic=verify(p.read_text(encoding="utf-8")), error=None)
        except ValueError as e:
            _cache.update(mtime=m, lic=None, error=str(e))
    return _cache["lic"], _cache["error"]


def install(text: str) -> dict:
    lic = verify(text)
    _path().write_text(text.strip(), encoding="utf-8")
    _cache["mtime"] = None
    return lic


def edition() -> dict:
    lic, _ = current()
    if lic:
        e = dict(EDITIONS[lic["edition"]])
        for k in ("max_assets", "max_users"):
            if k in lic:
                e[k] = lic[k]
        return {"id": lic["edition"], **e}
    if not ENFORCE:
        return {"id": "dev", "name": "Geliştirme (lisanssız, sınırsız)", "max_assets": None, "max_users": None}
    return {"id": "free", **EDITIONS["free"]}


def is_valid() -> bool:
    return True  # lisanssız da çalışır; sınırlar edition() ile uygulanır


def check_limit(kind: str, current_count: int):
    lim = edition().get(f"max_{kind}")
    if lim is not None and current_count >= lim:
        what = "cihaz" if kind == "assets" else "kullanıcı"
        raise PermissionError(f"Lisans sınırı: en fazla {lim} {what}. Lisansınızı yükseltin.")


def status() -> dict:
    lic, err = current()
    e = edition()
    return {"enforced": ENFORCE, "valid": True, "edition": e["name"], "edition_id": e["id"],
            "limits": {"assets": e["max_assets"], "users": e["max_users"]}, "machine_id": machine_id(),
            "licensee": (lic or {}).get("licensee"), "expires": (lic or {}).get("expires"), "error": err,
            "can_install": bool(PUBLIC_KEY), "required": ENFORCE}
