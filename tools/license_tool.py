"""NexEnvanter lisans aracı (yalnızca geliştirici bilgisayarında; depoya özel anahtar koymayın).

  python tools/license_tool.py keygen  C:\\guvenli\\nexenvanter_private.key
      → özel anahtarı yazar, genel anahtarı ekrana basar (app/license.py PUBLIC_KEY'e yapıştırın)

  python tools/license_tool.py issue C:\\guvenli\\nexenvanter_private.key --licensee "Adıyaman EAH" \\
      --edition pro --machine 2F7AF6AF67B302B53E53 [--expires 2027-12-31] [--max-assets 20000] -o license.nxl
"""
import argparse
import base64
import json
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def keygen(path):
    p = Path(path)
    if p.exists():
        sys.exit(f"{p} zaten var; üzerine yazılmadı.")
    k = Ed25519PrivateKey.generate()
    p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("Özel anahtar:", p.resolve())
    print('PUBLIC_KEY = "%s"' % b64(pub))


def issue(a):
    k = serialization.load_pem_private_key(Path(a.key).read_bytes(), None)
    payload = {"licensee": a.licensee, "edition": a.edition, "machine_id": a.machine or "*",
               "issued": date.today().isoformat(), "expires": a.expires}
    if a.max_assets:
        payload["max_assets"] = a.max_assets
    if a.max_users:
        payload["max_users"] = a.max_users
    body = b64(json.dumps(payload, ensure_ascii=False).encode())
    text = body + "." + b64(k.sign(body.encode()))
    Path(a.output).write_text(text, encoding="utf-8")
    print("Lisans yazıldı:", a.output, payload)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("keygen")
    g.add_argument("path")
    i = sub.add_parser("issue")
    i.add_argument("key")
    i.add_argument("--licensee", required=True)
    i.add_argument("--edition", choices=["free", "standard", "pro"], default="pro")
    i.add_argument("--machine")
    i.add_argument("--expires")
    i.add_argument("--max-assets", type=int)
    i.add_argument("--max-users", type=int)
    i.add_argument("-o", "--output", default="license.nxl")
    a = ap.parse_args()
    keygen(a.path) if a.cmd == "keygen" else issue(a)
