"""HTTPS: kendinden imzalı sertifika üretimi veya kurum sertifikası (data/tls/cert.pem + key.pem)."""
import datetime
import ipaddress
import socket

from .paths import DIRS


def paths():
    d = DIRS.data / "tls"
    d.mkdir(exist_ok=True)
    return d / "cert.pem", d / "key.pem"


def available() -> bool:
    c, k = paths()
    return c.exists() and k.exists()


def info() -> dict:
    c, _ = paths()
    if not c.exists():
        return {}
    try:
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(c.read_bytes())
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            names = [str(n.value) for n in san]
        except x509.ExtensionNotFound:
            names = []
        return {"subject": cert.subject.rfc4514_string(), "not_after": cert.not_valid_after_utc.isoformat()[:10],
                "names": names, "self_signed": cert.issuer == cert.subject}
    except Exception as e:
        return {"error": str(e)}


def make_selfsigned(hostnames: list[str]) -> dict:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from .api import lan_ip
    names = {socket.gethostname(), "localhost", lan_ip(), "127.0.0.1", *[h.strip() for h in hostnames if h.strip()]}
    alt = []
    for n in sorted(names):
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            alt.append(x509.DNSName(n))
    key = ec.generate_private_key(ec.SECP256R1())
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NexEnvanter"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NexEnvanter")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subj).issuer_name(subj).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    c, k = paths()
    k.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    c.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return info()
