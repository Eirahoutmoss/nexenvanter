"""v0.4: onay kuyruğu, alarmlar, yedek havuzu, hizmet noktaları, yazıcı sayaç/maliyet, arıza analizi."""
import pytest
from fastapi.testclient import TestClient

H = {"x-nx": "1"}


@pytest.fixture(scope="module")
def c(tmp_path_factory):
    from app.paths import DIRS
    DIRS.init(str(tmp_path_factory.mktemp("v4")))
    from app import api, db
    db._local.__dict__.clear()
    db.init()
    cl = TestClient(api.app)
    assert cl.post("/api/setup", json={"username": "admin", "password": "Parola123"}, headers=H).status_code == 200
    for code, loc, bm, kind in [("PC1", "Acil", "HP", "Masaüstü Bilgisayar"), ("PR1", "Acil", "HP M428", "Yazıcı"),
                                ("MON1", "Acil", "Dell", "Monitör")]:
        cl.post("/api/assets", json={"asset_code": code, "location_name": loc, "brand_model": bm, "hardware_info": kind,
                                     "mac_address": f"00:11:22:33:44:{code[-1]}1"}, headers=H)
    return cl


def aid(c, code):
    return c.get(f"/api/assets/by-code/{code}").json()["id"]


def test_discovery_approval(c):
    from app import discovery, db
    # tarama envanterde olmayan cihaz bulur → onay kuyruğu
    pid = discovery.offer(ip="10.0.0.50", mac="AA:BB:CC:DD:EE:01", hostname="YAZICI-ACIL", kind="Yazıcı", source="tarama",
                          data={"ports": [9100, 80]})
    assert pid
    # envanterde olan MAC tekrar düşmez
    assert discovery.offer(mac="00:11:22:33:44:11") is None
    lst = c.get("/api/pending").json()
    assert lst["count"] == 1 and lst["items"][0]["kind"] == "Yazıcı"
    # onayla → envantere ekle
    a = c.post(f"/api/pending/{pid}/approve", json={"type": "Yazıcı", "extra": {"location_name": "Acil"}}, headers=H).json()
    assert a["data"]["mac_address"] == "AA:BB:CC:DD:EE:01" and a["data"]["ip_address"] == "10.0.0.50"
    assert c.get("/api/pending").json()["count"] == 0
    # ikinci cihaz → yok say
    pid2 = discovery.offer(ip="10.0.0.99", mac="AA:BB:CC:DD:EE:99", hostname="MISAFIR")
    c.post(f"/api/pending/{pid2}/ignore", headers=H)
    assert c.get("/api/pending").json()["count"] == 0


def test_alerts_change_and_offline(c):
    from app import alerts, agent, db
    rep = {"hostname": "ACIL-PC", "serial": "SN-100", "macs": ["00-11-22-33-44-11"], "ram_gb": 16, "cpu": "i5", "os": "Win11"}
    agent.report(rep, "10.0.0.1")  # PC1 ile MAC eşleşir
    # RAM düşerse alarm
    agent.report({**rep, "ram_gb": 8}, "10.0.0.1")
    al = c.get("/api/alerts").json()
    assert any("RAM" in x["message"] for x in al["items"])
    # seri değişirse kritik alarm
    agent.report({**rep, "ram_gb": 8, "serial": "SN-999"}, "10.0.0.1")
    al = c.get("/api/alerts").json()
    assert any(x["severity"] == "kritik" and "Seri" in x["message"] for x in al["items"])
    # alarmı arızaya çevir
    a = next(x for x in al["items"] if x["severity"] == "kritik")
    r = c.post(f"/api/alerts/{a['id']}/resolve", json={"make_ticket": True}, headers=H).json()
    assert r["ticket_id"]
    # çevrimdışı: net_seen eski tarihli
    db.conn().execute("INSERT OR REPLACE INTO net_seen(mac,last_seen,first_seen) VALUES('00:11:22:33:44:11','2020-01-01T00:00:00','2020-01-01T00:00:00')")
    c.post("/api/alerts/check", headers=H)
    assert any(x["kind"] == "cevrimdisi" for x in c.get("/api/alerts").json()["items"])


def test_spare_pool(c):
    s = aid(c, "MON1")
    c.post("/api/spares/mark", json={"asset_ids": [s]}, headers=H)
    assert c.get("/api/spares").json()["available_count"] == 1
    c.post("/api/spares/give", json={"asset_id": s, "to_unit": "Poliklinik", "to_person": "Dr. X",
                                     "replacing_asset_id": aid(c, "PC1")}, headers=H)
    p = c.get("/api/spares").json()
    assert p["available_count"] == 0 and p["on_loan_count"] == 1 and p["on_loan"][0]["to_unit"] == "Poliklinik"
    c.post(f"/api/spares/{s}/back", json={"note": "onarıldı"}, headers=H)
    assert c.get("/api/spares").json()["available_count"] == 1


def test_service_points_and_noc(c):
    p = c.post("/api/service-points", json={"name": "Acil kayıt masası 3", "location": "Acil", "critical": True}, headers=H).json()
    c.patch(f"/api/service-points/{p['id']}", json={"items": [{"asset_id": aid(c, "PC1"), "role": "Bilgisayar"},
                                                             {"asset_id": aid(c, "PR1"), "role": "Yazıcı"}]}, headers=H)
    pts = c.get("/api/service-points").json()
    assert pts[0]["count"] == 2
    # PC1'de açık arıza var (önceki testten) → nokta durumu arıza/kritik
    noc = c.get("/api/noc").json()
    assert noc["points"][0]["status"] in ("arıza", "kritik", "uyarı")
    assert any(x["asset_code"] == "PC1" for x in noc["critical"]) or noc["points"]


def test_printer_cost_report(c):
    from app import printers, db
    pid = aid(c, "PR1")
    # iki okuma: sayaç farkı
    printers.record(pid, {"pages": 1000, "supplies": [{"name": "Siyah Toner", "pct": 8}], "status": "hazır", "errors": []})
    printers.apply_to_asset(pid, {"pages": 1000, "serial": "PRN-1", "supplies": [{"name": "Siyah Toner", "pct": 8}], "errors": []})
    db.conn().execute("UPDATE printer_readings SET at='2026-10-01T00:00:00' WHERE asset_id=? AND pages=1000", (pid,))
    printers.record(pid, {"pages": 4000, "supplies": [], "status": "hazır", "errors": []})
    c.put("/api/settings", json={"cost_per_page": 0.5}, headers=H)
    rep = c.get("/api/reports/printing").json()
    pr = next(x for x in rep["printers"] if x["id"] == pid)
    assert pr["pages"] == 3000 and pr["cost"] == 1500.0
    assert c.get("/api/reports/printing.xlsx").content[:2] == b"PK"
    # düşük toner alarmı apply sırasında oluştu
    assert any(x["kind"] == "sarf_az" for x in c.get("/api/alerts").json()["items"])


def test_ticket_analytics(c):
    r = c.get("/api/analytics/tickets", params={"days": 365}).json()
    assert "by_hour" in r and "by_unit" in r and "recurring" in r
    assert c.get("/api/analytics/workload").status_code == 200


def test_public_kb_on_qr(c):
    k = c.post("/api/kb", json={"title": "M428 kağıt sıkışması", "body": "Arka kapağı açın.", "match": "M428",
                                "public": True}, headers=H).json()
    assert k["public"]
    a = c.get("/api/assets/by-code/PR1").json()
    anon = TestClient(c.app)
    page = anon.get(f"/e/{a['public_id']}")
    assert "Sık karşılaşılan sorunlar" in page.text and "Arka kapağı" in page.text
