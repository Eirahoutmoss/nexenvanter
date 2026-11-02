"""v0.3: tür/kategori numaralandırma, etiket stilleri, yazıcı profili, ağ blokları."""
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

H = {"x-nx": "1"}


@pytest.fixture(scope="module")
def c(tmp_path_factory):
    from app.paths import DIRS
    DIRS.init(str(tmp_path_factory.mktemp("v3")))
    from app import api, db
    db._local.__dict__.clear()
    db.init()
    cl = TestClient(api.app)
    assert cl.post("/api/setup", json={"username": "admin", "password": "Parola123"}, headers=H).status_code == 200
    return cl


def test_auto_number_by_type(c):
    cat = c.get("/api/catalog").json()
    blg = next(k for k in cat["categories"] if k["name"] == "Bilgisayar")
    assert blg["next_code"] == "BLG-00001"
    assert c.get("/api/catalog/next", params={"type": "masaüstü bilgisayar"}).json()["code"] == "BLG-00001"
    a1 = c.post("/api/assets", json={"hardware_info": "Masaüstü Bilgisayar"}, headers=H).json()
    a2 = c.post("/api/assets", json={"hardware_info": "Dizüstü Bilgisayar", "asset_code": ""}, headers=H).json()
    assert (a1["asset_code"], a2["asset_code"]) == ("BLG-00001", "BLG-00002")
    assert a1["data"]["category"] == "Bilgisayar"
    # elle girilen ve kalıba uyan numara sayacı ileri alır, çakışan numara atlanır
    c.post("/api/assets", json={"hardware_info": "All-in-One Bilgisayar", "asset_code": "BLG-00010"}, headers=H)
    assert c.post("/api/assets", json={"hardware_info": "İnce İstemci"}, headers=H).json()["asset_code"] == "BLG-00011"
    # başka kategori kendi sayacını kullanır
    assert c.post("/api/assets", json={"hardware_info": "Yazıcı"}, headers=H).json()["asset_code"] == "YZC-00001"
    # tanımsız tür + barkod yok → hata
    r = c.post("/api/assets", json={"hardware_info": "Uzay Gemisi"}, headers=H)
    assert r.status_code == 422
    # kategori kalıbı değişir
    yid = next(k["id"] for k in c.get("/api/catalog").json()["categories"] if k["name"].startswith("Yazıcı"))
    c.patch(f"/api/catalog/categories/{yid}", json={"prefix": "PRN", "digits": 3, "next_no": 50}, headers=H)
    assert c.post("/api/assets", json={"hardware_info": "Tarayıcı"}, headers=H).json()["asset_code"] == "PRN050"
    # yeni tür + eş ad
    c.post("/api/catalog/types", json={"name": "Tablet", "category_id": yid}, headers=H)
    t = next(x for x in c.get("/api/catalog").json()["types"] if x["name"] == "Tablet")
    c.patch(f"/api/catalog/types/{t['id']}", json={"aliases": ["iPad"]}, headers=H)
    assert c.post("/api/assets", json={"hardware_info": "ipad"}, headers=H).json()["asset_code"] == "PRN051"


def test_import_auto_code(c):
    wb = openpyxl.Workbook()
    for r in [["DONANIM BİLGİSİ", "MARKA MODEL", "BARKOT NUMARASI"], ["Monitör", "Dell P2422", ""], ["Monitör", "LG", None],
              ["Bilinmeyen", "x", ""], ["Monitör", "HP", "MON-99999"]]:
        wb.active.append(r)
    b = io.BytesIO(); wb.save(b)
    an = c.post("/api/import/upload", files={"file": ("m.xlsx", b.getvalue())}, headers=H).json()
    mp = {str(x["index"]): x["suggestion"] for x in an["columns"]}
    res = c.post("/api/import/run", json={"token": an["token"], "sheet": an["sheet"], "header_row": an["header_row"], "mapping": mp,
                                          "auto_code": True, "dry_run": False}, headers=H).json()
    assert res["stats"]["inserted"] == 3 and res["stats"]["errors"] == 1
    assert c.get("/api/assets/by-code/MON-00001").status_code == 200
    assert c.get("/api/assets/by-code/MON-00002").status_code == 200
    # MON-99999 elle girildi → sayaç 100000
    assert c.get("/api/catalog/next", params={"type": "Monitör"}).json()["code"] == "MON-100000"


def test_label_styles_and_quality(c):
    from app import labels
    fams = labels.available_families()
    assert fams
    a = {"asset_code": "BLG-00001", "data": {"brand_model": "FUJITSU ESPRIMO D556 MINI TOWER KASA UZUN AD", "location_name": "ACİL"}}
    img = labels.render(a, "http://x/e/abc", {"width_mm": 80, "height_mm": 40, "row_layout": {"label_col_pct": 40},
                                               "styles": {"value": {"family": fams[0], "size": 9, "bold": True}},
                                               "barcode": {"enabled": True}, "quality": {"mono": True, "boost": 1}})
    assert img.size == (1134, 567)
    assert not any(img.histogram()[1:255])  # saf siyah-beyaz
    # aynı şablon farklı DPI'da birebir mm ölçüsünde çizilir
    assert labels.render(a, "u", {"width_mm": 80, "height_mm": 40}, dpi=180).size == (567, 283)
    assert labels.calibration({"width_mm": 80, "height_mm": 40}).size == (1134, 567)
    t = c.get("/api/labels/template").json()
    assert t["fonts"] and any(p["width_mm"] == 80 and p["height_mm"] == 40 for p in t["presets"])
    r = c.post("/api/labels/preview", json={"template": {"width_mm": 80, "height_mm": 40}, "calibration": True}, headers=H)
    assert r.content[:4] == b"\x89PNG"
    assert c.get("/api/labels/calibration.pdf").content[:4] == b"%PDF"


def test_print_plan_and_profile(c, monkeypatch):
    from app import printing
    # 80x40 etiket, 36 mm şerit (basılabilir ~80x32): döndürmeden %80 küçültme
    assert printing._plan(80, 40, 80, 32, {"rotate": "auto", "fit": "fit"}) == (0, 0.8)
    # dikey kağıt sürücüsü (40x80) → otomatik 90° döndürme, ölçeksiz
    assert printing._plan(80, 40, 40.5, 80.5, {"rotate": "auto", "fit": "fit"}) == (90, 1.0)
    assert printing._plan(80, 40, 50, 30, {"rotate": "0", "fit": "actual"}) == (0, 1.0)
    p = c.put("/api/printers/profile", json={"name": "Brother PT-P900W", "profile": {"tape_mm": 36, "rotate": "auto",
                                                                                     "offset_x_mm": "0.5"}}, headers=H).json()
    assert p["tape_mm"] == 36 and p["offset_x_mm"] == 0.5
    assert c.get("/api/printers/profile", params={"name": "Brother PT-P900W"}).json()["tape_mm"] == 36

    calls = {}

    class Fake(printing.PrinterAdapter):
        id = "windows"

        def available(self):
            return True

        def list_printers(self):
            return [{"name": "Brother PT-P900W", "default": True}]

        def print_labels(self, printer, render, w, h, count, copies=1, profile=None):
            calls["imgs"] = [render(i, 288) for i in range(count)]
            calls["profile"] = profile
    monkeypatch.setitem(printing.ADAPTERS, "windows", Fake())
    aid = c.get("/api/assets/by-code/BLG-00001").json()["id"]
    r = c.post("/api/print", json={"ids": [aid], "printer": "Brother PT-P900W"}, headers=H).json()
    assert r["ok"] and calls["profile"]["tape_mm"] == 36
    assert calls["imgs"][0].size[0] == round(70 * 288 / 25.4)  # şablon DPI'ı değil, yazıcı DPI'ı ile çizildi
    assert c.post("/api/print", json={"calibration": True, "printer": "Brother PT-P900W"}, headers=H).json()["ok"]


def test_network_targets():
    from app import network as N
    t = N.parse_targets(["Acil: 10.20.1.0/24", "10.30.5.10-10.30.5.20", "Poli: 10.30.6.40-60", "192.168.1.7"])
    assert [(x["name"], len(x["hosts"])) for x in t] == [("Acil", 254), ("10.30.5.10-10.30.5.20", 11), ("Poli", 21),
                                                        ("192.168.1.7", 1)]
    with pytest.raises(ValueError):
        N.parse_targets(["10.0.0.0/8"])
    with pytest.raises(ValueError):
        N.parse_targets(["10.0.0.0/18", "10.1.0.0/18"])  # toplam sınır
    tid = b"\x12\x34"
    names = b"".join(n.ljust(15).encode() + bytes([s]) + f.to_bytes(2, "big")
                     for n, s, f in [("WORKGROUP", 0, 0x8400), ("ACIL-PC01", 0, 0x0400)])
    rr = N._nb_encode() + b"\x00\x21\x00\x01" + b"\x00" * 4 + (1 + len(names) + 6).to_bytes(2, "big") + bytes([2]) + names \
        + bytes.fromhex("001122aabbcc")
    assert N.parse_nbstat(tid + b"\x84\x00\x00\x00\x00\x01\x00\x00\x00\x00" + rr, tid) == ("ACIL-PC01", "00:11:22:AA:BB:CC")
    assert N._kind("9100,80") == "Yazıcı" and N._kind("135,445") == "Windows"


def test_session_print_agent(c):
    """Hizmet SYSTEM iken kullanıcı oturumundaki aracı yazıcıları bildirir ve işi basar."""
    import threading
    from app import printagent, printing
    assert printagent.hello("ag1", "hasan", ["\\\\srv\\Brother PT-P900W"])["job"] is None
    assert any(p["adapter"] == "agent" for p in printing.all_printers())
    a = printing.adapter_for("\\\\srv\\Brother PT-P900W")
    assert a.id == "agent"
    got = {}

    def agent():
        for _ in range(50):
            j = printagent.hello("ag1", "hasan", ["\\\\srv\\Brother PT-P900W"])["job"]
            if j:
                got["png"] = printagent.page(j["id"], 0, 180)
                printagent.done(j["id"], None)
                return
            threading.Event().wait(0.05)
    th = threading.Thread(target=agent)
    th.start()
    aid = c.get("/api/assets/by-code/BLG-00001").json()["id"]
    r = c.post("/api/print", json={"ids": [aid], "printer": "\\\\srv\\Brother PT-P900W"}, headers=H)
    th.join()
    assert r.status_code == 200, r.text
    assert got["png"][:4] == b"\x89PNG"
    # aracıya doğrudan erişim yalnızca yerelden + anahtarla
    assert c.post("/api/printagent/hello", json={"id": "x"}, headers=H).status_code == 403
