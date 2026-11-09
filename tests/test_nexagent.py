"""NexAgent protokolü: sahte (Python) ajanla uçtan uca — imza, TLS parmak izi, keşif, çekme, ayar, kaldırma, paket."""
import base64
import datetime
import hashlib
import json
import ssl
import threading
import time
import zipfile
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

H = {"x-nx": "1"}
AGENT_ID = "11111111-2222-3333-4444-555555555555"
LOG = []


def make_cert(tmp):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NexAgent-TEST")])
    c = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(k.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
         .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)).sign(k, hashes.SHA256()))
    cf, kf = tmp / "c.pem", tmp / "k.pem"
    cf.write_bytes(c.public_bytes(serialization.Encoding.PEM))
    kf.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cf, kf, hashlib.sha256(c.public_bytes(serialization.Encoding.DER)).hexdigest()


class FakeAgent:
    """C# ajanın protokolünü aynen uygular (NEX1 imza metni, DER ECDSA, nonce, ±300 sn)."""

    def __init__(self, pubkey_b64, cert, key, port):
        from cryptography.hazmat.primitives import serialization
        self.pub = serialization.load_der_public_key(base64.b64decode(pubkey_b64))
        self.nonces, self.cfg_version, self.collected = set(), 1, "2026-11-09T10:00:00Z"
        outer = self

        class Hd(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, obj=None, etag=None):
                b = json.dumps(obj).encode() if obj is not None and code != 304 else b""
                self.send_response(code)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Connection", "close")
                if etag:
                    self.send_header("ETag", etag)
                self.end_headers()
                self.wfile.write(b)

            def _auth(self, body):
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import ec
                h = self.headers
                try:
                    ts, nonce, ag, sig = int(h["X-Nex-Ts"]), h["X-Nex-Nonce"], h["X-Nex-Agent"], h["X-Nex-Sig"]
                    assert abs(time.time() - ts) < 300 and ag == AGENT_ID and nonce not in outer.nonces and len(nonce) >= 12
                    msg = f"NEX1\n{self.command}\n{self.path}\n{AGENT_ID}\n{ts}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
                    outer.pub.verify(base64.b64decode(sig), msg.encode(), ec.ECDSA(hashes.SHA256()))
                    outer.nonces.add(nonce)
                    return True
                except Exception:
                    return False

            def handle_any(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                p = self.path.split("?")[0]
                if self.command == "GET" and p == "/v1/hello":
                    return self._send(200, {"proto": 1, "agentId": AGENT_ID, "version": "1.0.0", "os": "windows"})
                if not self._auth(body):
                    return self._send(401, {"error": "imza geçersiz"})
                LOG.append((self.command, self.path))
                if p == "/v1/status":
                    return self._send(200, {"agentId": AGENT_ID, "version": "1.0.0", "os": "windows", "hostname": "TEST-PC"})
                if p == "/v1/inventory":
                    etag = f'"{outer.collected}-{outer.cfg_version}"'
                    if self.headers.get("If-None-Match") == etag:
                        return self._send(304, etag=etag)
                    return self._send(200, outer.inventory(), etag)
                if p == "/v1/config" and self.command == "PUT":
                    outer.cfg_version += 1
                    outer.last_cfg = json.loads(body)
                    return self._send(200, {"ok": True, "version": outer.cfg_version})
                if p == "/v1/uninstall":
                    outer.uninstalled = json.loads(body)["confirm"] == AGENT_ID
                    return self._send(202, {"ok": True})
                self._send(404, {"error": "yok"})

            do_GET = do_PUT = do_POST = handle_any

        self.srv = ThreadingHTTPServer(("127.0.0.1", port), Hd)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        self.srv.socket = ctx.wrap_socket(self.srv.socket, server_side=True)
        self.uninstalled = False
        self.last_cfg = None
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def inventory(self):
        return {"agentId": AGENT_ID, "agentVersion": "1.0.0", "hostname": "TEST-PC", "collectedAt": self.collected, "durationMs": 900,
                "configVersion": self.cfg_version, "errors": {}, "missing": [], "modules": {
                    "system": {"hostname": "TEST-PC", "manufacturer": "FUJITSU", "model": "D556", "serial": "SN-TEST-1", "lastUser": "HASTANE\\ayse",
                               "os": {"caption": "Microsoft Windows 11 Pro", "version": "10.0.22631"}},
                    "cpu": {"name": "Intel i5-6500", "cores": 4, "threads": 4},
                    "memory": {"totalBytes": 17101897728, "modules": []},
                    "storage": {"disks": [{"model": "Samsung SSD 860", "sizeBytes": 256060514304, "mediaType": "SSD"}], "volumes": []},
                    "network": [{"name": "Ethernet", "mac": "00:11:22:33:44:AA", "ips": ["127.0.0.1"], "virtual": False}],
                    "software": {"count": 1, "truncated": False, "items": [{"name": "7-Zip", "version": "23.01"}]}}}

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    from app.paths import DIRS
    DIRS.init(str(tmp_path_factory.mktemp("nexagent")))
    from app import api, db
    db._local.__dict__.clear()
    db.init()
    cl = TestClient(api.app)
    assert cl.post("/api/setup", json={"username": "admin", "password": "Parola123"}, headers=H).status_code == 200
    cl.post("/api/assets", json={"asset_code": "PC-T1", "location_name": "Acil", "brand_model": "Fujitsu D556", "hardware_info": "Masaüstü Bilgisayar",
                                 "mac_address": "00:11:22:33:44:AA"}, headers=H)
    return cl, tmp_path_factory.mktemp("certs")


def wait_job(NA):
    for _ in range(200):
        if not NA.STATE["running"]:
            return NA.STATE["last_result"]
        time.sleep(0.05)
    raise AssertionError("iş bitmedi")


def test_end_to_end(env):
    c, tmp = env
    from app import nexagent as NA, db
    cf, kf, fp = make_cert(tmp)
    ag = FakeAgent(NA.public_b64(), cf, kf, 47899)
    try:
        r = c.put("/api/nexagent/settings", json={"port": 47899, "sources": ["127.0.0.1"], "uninstall_password": "Gizli123", "interval_minutes": 120,
                                                 "modules": {"usb": True}}, headers=H)
        assert r.status_code == 200
        assert NA.cfg()["uninstall_hash"].startswith("pbkdf2-sha256$")
        # keşif: ajanı bul, imzalı doğrulama + ilk veri
        assert NA.discover(["127.0.0.1"], "admin")
        res = wait_job(NA)
        assert res["found"] == 1 and res["new"] == 1, res
        n = NA.node(AGENT_ID)
        assert n["fingerprint"] == fp and n["state"] == "çevrimiçi" and n["hostname"] == "TEST-PC"
        assert n["asset_id"], "MAC ile envanter kaydına eşlenmeli"
        a = c.get(f"/api/assets/{n['asset_id']}").json()
        assert a["asset_code"] == "PC-T1" and a["data"]["hostname"] == "TEST-PC" and a["data"]["ram_gb"] == "16"
        assert a["data"]["brand_model"] == "Fujitsu D556"  # elle girilen korunur
        sn = c.get(f"/api/nexagent/asset/{n['asset_id']}").json()
        assert sn["snapshot"]["modules"]["software"]["count"] == 1
        # ayar eşitleme: ilk çekmede PUT /v1/config gitmeli, istenen modüller/parola özeti ile
        assert ag.last_cfg["modules"]["usb"] is True and ag.last_cfg["uninstallHash"].startswith("pbkdf2-sha256$")
        assert ag.last_cfg["allowedSources"] == ["127.0.0.1"] and ag.last_cfg["intervalMinutes"] == 120
        # değişmeyen veri: 304
        LOG.clear()
        out = NA.pull_node(AGENT_ID)
        assert out.get("unchanged"), out
        # cihaz özel ayarı → bir sonraki çekmede iletilir
        NA.set_override(AGENT_ID, {"modules": {"software": False}}, "admin")
        NA.pull_node(AGENT_ID)
        assert ag.last_cfg["modules"]["software"] is False and ag.last_cfg["modules"]["system"] is True
        # imza olmadan / bozuk imzayla erişilemez
        import http.client
        conn = NA._Conn("127.0.0.1", 47899, timeout=5)
        conn.request("GET", "/v1/inventory")
        assert conn.getresponse().status == 401
        # sertifika değişti (taklit/yeniden kurulum) → parmak izi uyarısı, veri alınmaz
        ag.stop()
        cf2, kf2, fp2 = make_cert(tmp)
        ag = FakeAgent(NA.public_b64(), cf2, kf2, 47899)
        with pytest.raises(NA.FingerprintMismatch):
            NA.pull_node(AGENT_ID, True)
        n = NA.node(AGENT_ID)
        assert n["state"] == "parmak izi" and n["pending_fp"] == fp2
        r = c.post(f"/api/nexagent/nodes/{AGENT_ID}/accept-fingerprint", headers=H)
        assert r.status_code == 200
        NA.pull_node(AGENT_ID, True)
        assert NA.node(AGENT_ID)["state"] == "çevrimiçi"
        # uzaktan kaldırma: yanlış onay reddedilir, doğrusu ajana iletilir
        assert c.post(f"/api/nexagent/nodes/{AGENT_ID}/uninstall", json={"confirm": "yanlis"}, headers=H).status_code == 400
        assert c.post(f"/api/nexagent/nodes/{AGENT_ID}/uninstall", json={"confirm": "test-pc"}, headers=H).status_code == 200
        assert ag.uninstalled and NA.node(AGENT_ID)["state"] == "kaldırıldı"
        assert c.delete(f"/api/nexagent/nodes/{AGENT_ID}", headers=H).status_code == 200
    finally:
        ag.stop()


def test_foreign_agent_not_enrolled(env):
    """Başka bir sunucunun anahtarını bilen ajan: imza doğrulanamaz → kayıt oluşmaz."""
    c, tmp = env
    from app import nexagent as NA
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    other = base64.b64encode(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    cf, kf, _ = make_cert(tmp)
    ag = FakeAgent(other, cf, kf, 47898)
    try:
        c.put("/api/nexagent/settings", json={"port": 47898}, headers=H)
        NA.discover(["127.0.0.1"], "admin")
        res = wait_job(NA)
        assert res["found"] == 1 and res["foreign"] == 1 and res["new"] == 0
        assert NA.node(AGENT_ID) is None
    finally:
        ag.stop()


def test_package_and_validation(env):
    c, _ = env
    from app import nexagent as NA
    assert c.put("/api/nexagent/settings", json={"port": 80}, headers=H).status_code == 400
    assert c.put("/api/nexagent/settings", json={"sources": ["gecersiz"]}, headers=H).status_code == 400
    c.put("/api/nexagent/settings", json={"port": 47820, "sources": ["10.0.0.5"]}, headers=H)
    assert c.get("/api/nexagent/package?os=win&arch=x64").status_code == 400  # ikili yok
    (NA.bins_dir() / "NexAgent-1.0.0-win-x64.exe").write_bytes(b"MZ-test")
    r = c.get("/api/nexagent/package?os=win&arch=x64")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert set(z.namelist()) == {"NexAgent.exe", "enroll.json", "KURULUM.txt"}
    en = json.loads(z.read("enroll.json"))
    assert en["publicKey"] == NA.public_b64() and en["allowedSources"] == ["10.0.0.5"] and en["port"] == 47820
    assert "privateKey" not in json.dumps(en) and en["uninstallHash"].startswith("pbkdf2-sha256$")
