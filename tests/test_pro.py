"""Pro modül testleri: python -m pytest -q"""
import io
import json
import socket
import threading
import zipfile

import pytest
from fastapi.testclient import TestClient

H = {"x-nx": "1"}


@pytest.fixture(scope="module")
def c(tmp_path_factory):
    from app.paths import DIRS
    DIRS.init(str(tmp_path_factory.mktemp("pro")))
    from app import api, db
    db._local.__dict__.clear()
    db.init()
    cl = TestClient(api.app)
    assert cl.post("/api/setup", json={"username": "admin", "password": "Parola123"}, headers=H).status_code == 200
    for code, loc, bm in [("A1", "Acil Servis", "HP LaserJet M428"), ("A2", "Acil Servis", "Fujitsu Esprimo D556"),
                          ("B1", "Poliklinik", "HP LaserJet M428"), ("B2", "Poliklinik", "Dell Optiplex 7090")]:
        r = cl.post("/api/assets", json={"asset_code": code, "location_name": loc, "brand_model": bm,
                                         "mac_address": f"00:11:22:33:44:{code[-1]}{code[0]}".replace("A", "A").upper()[:17]}, headers=H)
        assert r.status_code == 200, r.text
    return cl


def aid(c, code):
    return c.get(f"/api/assets/by-code/{code}").json()["id"]


def test_public_ticket_flow(c):
    a = c.get("/api/assets/by-code/A1").json()
    anon = TestClient(c.app)
    page = anon.get(f"/e/{a['public_id']}")
    assert "Arıza bildir" in page.text and "Sayıma ekle" not in page.text
    r = anon.post("/api/public/tickets", json={"public_id": a["public_id"], "description": "Kağıt sıkıştı", "reporter_name": "Ayşe",
                                                "category": "Yazdırma sorunu"}, headers=H)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert "Durum: yeni" in anon.get(f"/t/{code}").text
    t = c.get("/api/tickets").json()["items"][0]
    assert t["asset_code"] == "A1" and t["source"] == "qr"
    r = c.patch(f"/api/tickets/{t['id']}", json={"assigned_to": "admin"}, headers=H).json()
    assert r["status"] == "atandı"
    r = c.patch(f"/api/tickets/{t['id']}", json={"status": "çözüldü", "resolution": "Kağıt yolu temizlendi",
                                                 "save_kb": True}, headers=H).json()
    assert r["resolved_at"] and r["kb_id"]
    # bilgi bankası aynı modeldeki diğer cihazda da önerilir
    b1 = c.get(f"/api/assets/{aid(c, 'B1')}").json()
    assert any(k["id"] == r["kb_id"] for k in b1["kb"])
    assert "Durum: çözüldü" in anon.get(f"/t/{code}").text
    # hız sınırı
    for _ in range(6):
        last = anon.post("/api/public/tickets", json={"public_id": a["public_id"], "description": "deneme deneme",
                                                       "reporter_name": "X"}, headers=H)
    assert last.status_code == 429


def test_count(c):
    cnt = c.post("/api/counts", json={"name": "Acil sayımı", "location": "acil servis"}, headers=H).json()
    assert cnt["expected"] == 2
    a1 = c.get("/api/assets/by-code/A1").json()
    assert c.post(f"/api/counts/{cnt['id']}/scan", json={"code": f"http://x/e/{a1['public_id']}"}, headers=H).json()["result"] == "ok"
    assert c.post(f"/api/counts/{cnt['id']}/scan", json={"code": "A1"}, headers=H).json()["result"] == "already"
    assert c.post(f"/api/counts/{cnt['id']}/scan", json={"code": "B2"}, headers=H).json()["result"] == "other_location"
    r = c.post(f"/api/counts/{cnt['id']}/scan-batch", json={"items": [{"code": "YOK-1", "at": "2026-10-27T10:00:00"}]}, headers=H)
    assert r.json()["results"][0]["result"] == "unknown"
    d = c.get(f"/api/counts/{cnt['id']}").json()
    assert (d["seen"], d["missing"], d["foreign"], d["unknown"]) == (2, 1, 1, 1)
    assert d["missing_items"][0]["asset_code"] == "A2"
    # QR sayfasında giriş yapmış kullanıcıya sayım düğmesi
    assert "Sayıma ekle" in c.get(f"/e/{a1['public_id']}").text
    assert c.get(f"/api/counts/{cnt['id']}/report.xlsx").status_code == 200
    assert "SAYIM TUTANAĞI" in c.get(f"/print/sayim/{cnt['id']}").text
    r = c.post(f"/api/counts/{cnt['id']}/close", json={"move_foreign": True}, headers=H).json()
    assert r["moved"] == 1 and r["status"] == "kapalı"
    assert c.get("/api/assets/by-code/B2").json()["data"]["location_name"] == "acil servis"


SIG = "data:image/png;base64,iVBORw0KGgo="


def test_assignment(c):
    ids = [aid(c, "A1"), aid(c, "A2")]
    r = c.post("/api/assignments", json={"asset_ids": ids, "kind": "kişi", "holder_name": "Dr. Ali Veli", "holder_unit": "Acil Servis",
                                         "signature": SIG}, headers=H).json()
    doc = r["doc_no"]
    assert doc.startswith("Z-")
    html = c.get(f"/print/zimmet/{doc}").text
    assert "ZİMMET TUTANAĞI" in html and "Dr. Ali Veli" in html and "A2" in html
    r2 = c.post("/api/assignments", json={"asset_ids": [ids[0]], "holder_name": "Hemşire Ayşe"}, headers=H).json()
    assert "DEVİR" in c.get(f"/print/zimmet/{r2['doc_no']}").text
    a = c.get(f"/api/assets/{ids[0]}").json()
    assert a["assignment"]["holder_name"] == "Hemşire Ayşe" and len(a["assignments"]) == 2
    r3 = c.post("/api/assignments/return", json={"asset_ids": ids}, headers=H).json()
    assert r3["count"] == 2 and "İADE" in c.get(f"/print/zimmet/{r3['doc_no']}").text
    assert c.get("/api/assignments").json()["total"] == 0


def test_maintenance_and_warranty(c):
    a = aid(c, "B1")
    c.patch(f"/api/assets/{a}", json={"warranty_end": "2026-11-15"}, headers=H)
    assert c.post("/api/maintenance", json={"asset_ids": [a], "title": "Yazıcı bakımı", "interval_days": 90,
                                            "first_due": "2026-01-01"}, headers=H).json()["created"] == 1
    ag = c.get("/api/maintenance").json()
    assert ag["overdue"] == 1 and ag["due"][0]["asset_code"] == "B1"
    pid = ag["due"][0]["id"]
    r = c.post(f"/api/maintenance/{pid}/done", json={"note": "Toner değişti"}, headers=H).json()
    assert r["next_due"] > "2026-10-01"
    assert c.get("/api/maintenance").json()["overdue"] == 0


def test_stock(c):
    s = c.post("/api/stock", json={"name": "HP 59A Toner", "min_stock": 2, "stock": 3, "compatible": "M428"}, headers=H).json()
    assert s["stock"] == 3 and not s["low"]
    s = c.post(f"/api/stock/{s['id']}/move", json={"qty": -2, "asset_code": "B1", "note": "Değişim"}, headers=H).json()
    assert s["stock"] == 1 and s["low"]
    assert c.post(f"/api/stock/{s['id']}/move", json={"qty": -5}, headers=H).status_code == 400
    b1 = c.get(f"/api/assets/{aid(c, 'B1')}").json()
    assert b1["consumables"][0]["name"] == "HP 59A Toner" and any(e["action"] == "sarf" for e in b1["events"])
    assert c.get("/api/badges").json()["low_stock"] == 1


def test_unit_rep_scope(c):
    c.post("/api/users", json={"username": "poli", "password": "Parola123", "role": "unit_rep", "units": ["Poliklinik"]}, headers=H)
    p = TestClient(c.app)
    p.post("/api/login", json={"username": "poli", "password": "Parola123"}, headers=H)
    lst = p.get("/api/assets").json()
    assert [x["asset_code"] for x in lst["items"]] == ["B1"]
    assert p.get(f"/api/assets/{aid(c, 'A1')}").status_code == 404
    assert p.post("/api/counts", json={"name": "x", "location": "Acil Servis"}, headers=H).status_code == 403
    assert p.post("/api/counts", json={"name": "Poli", "location": "poliklinik"}, headers=H).status_code == 200
    assert [x["name"] for x in p.get("/api/counts").json()] == ["Poli"]
    assert p.post("/api/assets", json={"asset_code": "Z9"}, headers=H).status_code == 403


def test_agent(c):
    st = c.get("/api/settings").json()
    tok = st["agent_token"]
    anon = TestClient(c.app)
    assert anon.get("/agent.ps1?t=yanlis").status_code == 403
    assert "X-Agent-Token" in anon.get(f"/agent.ps1?t={tok}").text
    rep = {"hostname": "ACIL-PC01", "serial": "123", "macs": ["00-11-22-33-44-2A"], "cpu": "Intel i5", "ram_gb": 16,
           "os": "Windows 11 Pro", "manufacturer": "FUJITSU", "model": "D556", "ips": ["10.1.1.5"], "user": "HASTANE\\ayse"}
    r = anon.post("/api/agent/report", json=rep, headers={"X-Agent-Token": tok}).json()
    assert r["matched"]  # MAC ile eşleşti (A2)
    a = c.get(f"/api/assets/{r['asset_id']}").json()
    assert a["asset_code"] == "A2" and a["data"]["ram_gb"] == "16" and a["data"]["hostname"] == "ACIL-PC01"
    assert a["data"]["brand_model"] == "Fujitsu Esprimo D556"  # elle girilen korunur
    r = anon.post("/api/agent/report", json={**rep, "hostname": "YENI-PC", "serial": "S-NEW", "macs": []},
                  headers={"X-Agent-Token": tok}).json()
    assert not r["matched"]
    un = c.get("/api/agent/reports?unmatched=1").json()
    assert un[0]["hostname"] == "YENI-PC"
    a = c.post("/api/agent/link", json={"hostname": "YENI-PC", "new_code": "PC-500"}, headers=H).json()
    assert a["data"]["serial_number"] == "S-NEW"


def test_reports_and_disposal(c):
    c.patch(f"/api/assets/{aid(c, 'B2')}", json={"purchase_date": "2015-01-01"}, headers=H)
    r = c.get("/api/reports/renewal").json()
    assert any(x["asset_code"] == "B2" for x in r["candidates"])
    assert c.get("/api/reports/renewal.xlsx").status_code == 200
    assert c.get("/api/reports/tasinir.xlsx").status_code == 200
    z = zipfile.ZipFile(io.BytesIO(c.get("/api/reports/audit-pack.zip").content))
    assert "03_zimmetler.xlsx" in z.namelist() and "BENIOKU.txt" in z.namelist()
    d = c.post("/api/disposals", json={"asset_ids": [aid(c, "B2")], "reason": "Anakart arızası, onarımı ekonomik değil",
                                       "commission": [{"name": "Ahmet", "title": "Başkan"}]}, headers=H).json()
    b2 = c.get("/api/assets/by-code/B2").json()
    assert b2["status"] == "hurda" and b2["archived"]
    assert "TERKİN" in c.get(f"/print/hurda/{d['doc_no']}").text


def test_tokens_and_summary(c):
    t = c.post("/api/tokens", json={"name": "il-saglik", "role": "auditor"}, headers=H).json()
    anon = TestClient(c.app)
    s = anon.get("/api/summary", headers={"Authorization": f"Bearer {t['token']}"})
    assert s.status_code == 200 and s.json()["assets"] >= 4
    # denetçi anahtarı yazamaz
    assert anon.post("/api/assets", json={"asset_code": "Q"}, headers={"Authorization": f"Bearer {t['token']}"}).status_code == 403
    c.delete(f"/api/tokens/{t['id']}", headers=H)
    assert anon.get("/api/summary", headers={"Authorization": f"Bearer {t['token']}"}).status_code == 401


def test_federation_poll(c):
    import uvicorn
    from app import api
    t = c.post("/api/tokens", json={"name": "fed", "role": "auditor"}, headers=H).json()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    import time
    for _ in range(50):
        if srv.started:
            break
        time.sleep(0.1)
    c.post("/api/federation", json={"name": "Kahta DH", "url": f"http://127.0.0.1:{port}", "token": t["token"]}, headers=H)
    c.post("/api/federation", json={"name": "Kapalı", "url": "http://127.0.0.1:1", "token": "x"}, headers=H)
    res = c.get("/api/federation/poll").json()
    srv.should_exit = True
    by = {x["name"]: x for x in res}
    assert by["Kahta DH"]["ok"] and by["Kahta DH"]["summary"]["assets"] >= 4
    assert not by["Kapalı"]["ok"]


def test_ldap_mock(c, monkeypatch):
    from ldap3 import MOCK_SYNC, Connection, Server
    from app import auth, db
    db.set_setting("ldap", {"enabled": True, "server": "mock", "domain": "hastane.local", "base_dn": "DC=hastane,DC=local",
                            "role_map": [{"group": "CN=NexEnvanter-BIM", "role": "operator"}], "default_role": "viewer",
                            "allow_unmapped": False})
    srv = Server("mock")
    root = Connection(srv, user="cn=root", password="x", client_strategy=MOCK_SYNC)
    root.strategy.add_entry("CN=Mehmet,DC=hastane,DC=local", {
        "userPrincipalName": "mehmet@hastane.local", "sAMAccountName": "mehmet", "displayName": "Mehmet Yılmaz",
        "userPassword": "AdParola1", "memberOf": ["CN=NexEnvanter-BIM,OU=Gruplar,DC=hastane,DC=local"], "objectClass": "person"})
    root.strategy.add_entry("CN=Zeynep,DC=hastane,DC=local", {
        "userPrincipalName": "zeynep@hastane.local", "sAMAccountName": "zeynep", "displayName": "Zeynep",
        "userPassword": "AdParola1", "memberOf": ["CN=Muhasebe,DC=hastane,DC=local"], "objectClass": "person"})
    dns = {"mehmet@hastane.local": "CN=Mehmet,DC=hastane,DC=local", "zeynep@hastane.local": "CN=Zeynep,DC=hastane,DC=local"}

    def fake(cfg, user, password):  # AD, UPN ile bind kabul eder; sahte dizin DN ister
        conn = Connection(srv, user=dns.get(user, "x"), password=password, client_strategy=MOCK_SYNC)
        conn.bind()
        return conn
    monkeypatch.setattr(auth, "_ldap_connection", fake)
    m = TestClient(c.app)
    assert m.post("/api/login", json={"username": "mehmet", "password": "yanlis"}, headers=H).status_code == 401
    assert m.post("/api/login", json={"username": "mehmet", "password": ""}, headers=H).status_code == 401
    r = m.post("/api/login", json={"username": "mehmet", "password": "AdParola1"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "operator" and r.json()["user"]["source"] == "ldap"
    z = TestClient(c.app).post("/api/login", json={"username": "zeynep", "password": "AdParola1"}, headers=H)
    assert z.status_code == 401  # eşlenmemiş grup
    db.set_setting("ldap", {"enabled": False})


def test_license_roundtrip(tmp_path, monkeypatch):
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app import license
    k = Ed25519PrivateKey.generate()
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    monkeypatch.setattr(license, "PUBLIC_KEY", b64(pub))
    body = b64(json.dumps({"licensee": "Test", "edition": "standard", "machine_id": license.machine_id(), "expires": None}).encode())
    good = body + "." + b64(k.sign(body.encode()))
    assert license.verify(good)["licensee"] == "Test"
    with pytest.raises(ValueError):
        license.verify(body + "." + b64(b"x" * 64))
    other = b64(json.dumps({"licensee": "T", "edition": "pro", "machine_id": "BASKA"}).encode())
    with pytest.raises(ValueError, match="bilgisayara"):
        license.verify(other + "." + b64(k.sign(other.encode())))


def test_snmp_codec_against_fake_agent():
    """Sahte SNMP ajanı: istek paketini çözer, GETBULK yanıtı üretir; istemci tabloyu doğru yürümeli."""
    from app import snmp
    table = {(1, 3, 6, 1, 2, 1, 17, 4, 3, 1, 2, 0, 17, 34, 51, 68, 85): 3,
             (1, 3, 6, 1, 2, 1, 17, 4, 3, 1, 2, 170, 187, 204, 221, 238, 255): 7}
    keys = sorted(table)

    def resp(rid, vbs):
        vb = b"".join(snmp._tlv(0x30, snmp._oid(o) + (snmp._int(v) if v is not None else b"\x82\x00")) for o, v in vbs)
        pdu = snmp._tlv(0xA2, snmp._int(rid) + snmp._int(0) + snmp._int(0) + snmp._tlv(0x30, vb))
        return snmp._tlv(0x30, snmp._int(1) + snmp._tlv(0x04, b"public") + pdu)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]

    def serve():
        for _ in range(3):
            data, addr = s.recvfrom(4096)
            _, msg, _ = snmp._read(data, 0)
            _, _, i = snmp._read(msg, 0)
            _, comm, i = snmp._read(msg, i)
            _, pdu, _ = snmp._read(msg, i)
            _, rid, j = snmp._read(pdu, 0)
            _, _, j = snmp._read(pdu, j)
            _, _, j = snmp._read(pdu, j)
            _, vbl, _ = snmp._read(pdu, j)
            _, vb, _ = snmp._read(vbl, 0)
            _, ob, _ = snmp._read(vb, 0)
            start = snmp._dec_oid(ob)
            nxt = [k for k in keys if k > start][:25]
            vbs = [(k, table[k]) for k in nxt] or [(start, None)]
            if len(nxt) < 25:
                vbs.append(((1, 3, 6, 1, 2, 1, 17, 4, 3, 1, 3, 0), 1))  # tablo dışı → yürüyüş biter
            s.sendto(resp(int.from_bytes(rid, "big", signed=True), vbs), addr)
    threading.Thread(target=serve, daemon=True).start()
    out = snmp.walk("127.0.0.1", "public", "1.3.6.1.2.1.17.4.3.1.2", port=port)
    s.close()
    from app.network import mac_str
    assert [(mac_str(i), v) for i, v in out] == [("00:11:22:33:44:55", 3), ("AA:BB:CC:DD:EE:FF", 7)]
    assert snmp._oid((1, 3, 6, 1, 2, 1, 1, 1, 0)) == bytes.fromhex("06082b06010201010100")
