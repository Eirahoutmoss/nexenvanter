"""Lisans kancası. Şu an lisans GEREKMEZ (LICENSE_REQUIRED=False).
İleride: imzalı lisans dosyası (Ed25519) + makine kimliği doğrulaması bu modüle eklenecek;
api.py yalnızca status() ve is_valid() çağırdığı için uygulamanın geri kalanı değişmez."""
import hashlib
import platform
import uuid

LICENSE_REQUIRED = False
EDITION = "Geliştirme (lisanssız)"


def machine_id() -> str:
    raw = f"{platform.node()}|{uuid.getnode()}|{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20].upper()


def is_valid() -> bool:
    return not LICENSE_REQUIRED


def status() -> dict:
    return {"required": LICENSE_REQUIRED, "valid": is_valid(), "edition": EDITION, "machine_id": machine_id(),
            "limits": None}
