"""Yazıcı SNMP sorgusu (Printer-MIB): seri no, model, sayfa sayacı, toner/drum doluluğu, durum.
Okunanlar envantere işlenir; sayaç geçmişinden birim bazlı baskı ve maliyet raporu çıkar."""
import json

from . import assets as A, db, snmp
from .textnorm import fold

# Standart Printer-MIB / Host Resources OID'leri (marka bağımsız, çoğu ağ yazıcısında açık)
OID = {
    "sysdescr": "1.3.6.1.2.1.1.1.0",
    "serial": "1.3.6.1.2.1.43.5.1.1.17.1",      # prtGeneralSerialNumber
    "pages": "1.3.6.1.2.1.43.10.2.1.4.1.1",     # prtMarkerLifeCount (toplam sayfa)
    "model": "1.3.6.1.2.1.25.3.2.1.3",          # hrDeviceDescr (walk)
    "pstatus": "1.3.6.1.2.1.25.3.5.1.1",        # hrPrinterStatus (walk)
    "perror": "1.3.6.1.2.1.25.3.5.1.2",         # hrPrinterDetectedErrorState (walk, bitmask)
    "sup_desc": "1.3.6.1.2.1.43.11.1.1.6.1",    # prtMarkerSuppliesDescription (walk)
    "sup_level": "1.3.6.1.2.1.43.11.1.1.9.1",   # prtMarkerSuppliesLevel (walk)
    "sup_max": "1.3.6.1.2.1.43.11.1.1.8.1",     # prtMarkerSuppliesMaxCapacity (walk)
}
PSTATUS = {1: "diğer", 2: "bilinmiyor", 3: "hazır", 4: "yazdırıyor", 5: "ısınıyor"}
ERRORS = ["düşük toner", "toner bitti", "kağız az", "kağıt bitti", "kapak açık", "kağıt sıkışması", "çevrimdışı",
          "servis gerekli", "giriş tepsisi boş", "çıkış dolu", "arıza", "ısınıyor", "hazırlanıyor", "bakım gerekli"]


def _one(host, community, key, timeout=2.0):
    r = snmp.walk(host, community, OID[key], timeout=timeout, limit=1)
    return r[0][1] if r else None


def _txt(v):
    return v.decode("utf-8", "replace").strip() if isinstance(v, (bytes, bytearray)) else (str(v).strip() if v is not None else None)


def _errors(bits) -> list[str]:
    if not isinstance(bits, (bytes, bytearray)):
        return []
    out = []
    for i, byte in enumerate(bits):
        for b in range(8):
            if byte & (0x80 >> b):
                idx = i * 8 + b
                if idx < len(ERRORS):
                    out.append(ERRORS[idx])
    return out


def query(host: str, community="public", timeout=2.0) -> dict:
    """Yazıcıyı SNMP ile sorgula. Hata → RuntimeError."""
    desc = _one(host, community, "sysdescr", timeout)
    if desc is None:
        raise RuntimeError("Yazıcı SNMP'ye yanıt vermedi (community/erişim veya SNMP kapalı)")
    serial = _txt(_one(host, community, "serial", timeout))
    pages = _one(host, community, "pages", timeout)
    models = [_txt(v) for _, v in snmp.walk(host, community, OID["model"], timeout=timeout) if _txt(v)]
    model = next((m for m in models if "printer" in m.lower() or any(k in m.lower() for k in ("hp", "brother", "canon", "xerox", "lexmark", "samsung", "epson", "kyocera", "ricoh"))), models[0] if models else _txt(desc))
    st = snmp.walk(host, community, OID["pstatus"], timeout=timeout)
    status = PSTATUS.get(st[0][1], "bilinmiyor") if st else "bilinmiyor"
    errs = []
    for _, v in snmp.walk(host, community, OID["perror"], timeout=timeout):
        errs += _errors(v)
    descs = {idx: _txt(v) for idx, v in snmp.walk(host, community, OID["sup_desc"], timeout=timeout)}
    levels = {idx: v for idx, v in snmp.walk(host, community, OID["sup_level"], timeout=timeout)}
    maxs = {idx: v for idx, v in snmp.walk(host, community, OID["sup_max"], timeout=timeout)}
    supplies = []
    for idx, name in descs.items():
        lv, mx = levels.get(idx), maxs.get(idx)
        pct = None
        if isinstance(lv, int) and isinstance(mx, int) and mx > 0 and lv >= 0:
            pct = round(lv * 100 / mx)
        elif lv == -3:
            pct = -3  # "biraz kaldı"
        supplies.append({"name": name, "pct": pct, "level": lv, "max": mx})
    return {"host": host, "model": model, "serial": serial, "pages": int(pages) if isinstance(pages, int) else None,
            "status": status, "errors": sorted(set(errs)), "supplies": supplies}


def record(asset_id: int, r: dict):
    db.conn().execute("INSERT INTO printer_readings(asset_id,at,pages,supplies,status,errors) VALUES(?,?,?,?,?,?)",
                      (asset_id, db.now(), r.get("pages"), json.dumps(r.get("supplies") or [], ensure_ascii=False),
                       r.get("status"), json.dumps(r.get("errors") or [], ensure_ascii=False)))


def apply_to_asset(asset_id: int, r: dict, user="snmp"):
    a = A.get(asset_id)
    cur = a["data"]
    payload = {}
    if r.get("serial") and not cur.get("serial_number"):
        payload["serial_number"] = r["serial"]
    if r.get("model") and not cur.get("brand_model"):
        payload["brand_model"] = r["model"]
    if r.get("pages") is not None:
        payload["page_count"] = str(r["pages"])
    if not cur.get("hardware_info"):
        payload["hardware_info"] = "Yazıcı"
    if payload:
        try:
            A.update(asset_id, payload, user, blank_overwrites=False, action="snmp")
        except A.AssetError:
            pass
    record(asset_id, r)
    _check_alerts(asset_id, a, r)


def _check_alerts(asset_id, a, r):
    from . import alerts
    lim = int(db.get_setting("toner_alert_pct", 10) or 10)
    for s in r.get("supplies") or []:
        if isinstance(s.get("pct"), int) and 0 <= s["pct"] <= lim:
            alerts.raise_alert(asset_id, "sarf_az", f"{a['asset_code']}: {s['name']} %{s['pct']}",
                               severity="uyarı", data={"supply": s["name"], "pct": s["pct"]},
                               dedup=f"sup:{asset_id}:{fold(s['name'])}")
    for e in r.get("errors") or []:
        if e in ("kağıt sıkışması", "kağıt bitti", "çevrimdışı", "kapak açık", "servis gerekli", "arıza"):
            alerts.raise_alert(asset_id, "yazici_hata", f"{a['asset_code']}: {e}", severity="uyarı",
                               data={"error": e}, dedup=f"err:{asset_id}:{fold(e)}")


def poll_asset(asset_id: int, user="snmp") -> dict:
    a = A.get(asset_id)
    if not a:
        raise KeyError(asset_id)
    ip = (a["data"].get("ip_address") or "").split(",")[0].strip()
    if not ip:
        raise RuntimeError("Cihazın IP adresi tanımlı değil")
    comm = a.get("snmp_community") or db.get_setting("default_community", "public")
    r = query(ip, comm)
    apply_to_asset(asset_id, r, user)
    return r


def readings(asset_id: int, limit=400):
    rows = db.conn().execute("SELECT * FROM printer_readings WHERE asset_id=? ORDER BY at DESC LIMIT ?", (asset_id, limit))
    out = []
    for r in rows:
        d = dict(r)
        d["supplies"] = json.loads(d["supplies"] or "[]")
        d["errors"] = json.loads(d["errors"] or "[]")
        out.append(d)
    return out


def latest(asset_id: int):
    rs = readings(asset_id, 1)
    return rs[0] if rs else None


def poll_all(user="zamanlayıcı") -> dict:
    """Envanterdeki, IP'si olan tüm yazıcıları sorgula."""
    c = db.conn()
    ids = [r[0] for r in c.execute(
        "SELECT id FROM assets WHERE archived=0 AND json_extract(data,'$.ip_address') IS NOT NULL "
        "AND (fold(json_extract(data,'$.hardware_info')) LIKE '%yazici%' OR fold(json_extract(data,'$.category')) LIKE '%yazici%')")]
    ok, fail = 0, []
    for aid in ids:
        try:
            poll_asset(aid, user)
            ok += 1
        except Exception as e:
            fail.append({"asset_id": aid, "error": str(e)[:200]})
    db.audit(user, "printer_poll", None, {"ok": ok, "fail": len(fail)})
    return {"polled": ok, "failed": fail, "total": len(ids)}


# ---------------- maliyet / sayaç raporu ----------------
def cost_report(months=6) -> dict:
    """Her yazıcı için ilk ve son okuma arasındaki sayfa farkı, birim bazlı toplam ve maliyet."""
    cost = float(db.get_setting("cost_per_page", 0) or 0)
    c = db.conn()
    printers, by_unit = [], {}
    for r in c.execute("SELECT DISTINCT asset_id FROM printer_readings"):
        aid = r[0]
        a = A.get(aid)
        if not a:
            continue
        rows = list(c.execute("SELECT at, pages FROM printer_readings WHERE asset_id=? AND pages IS NOT NULL ORDER BY at", (aid,)))
        if len(rows) < 1:
            continue
        first, last = rows[0], rows[-1]
        delta = (last[1] - first[1]) if len(rows) >= 2 else 0
        loc = a["data"].get("location_name") or "(Belirtilmemiş)"
        rec = {"id": aid, "asset_code": a["asset_code"], "model": a["data"].get("brand_model"), "location": loc,
               "first_at": first[0][:10], "last_at": last[0][:10], "first_pages": first[1], "last_pages": last[1],
               "pages": delta, "cost": round(delta * cost, 2), "readings": len(rows)}
        printers.append(rec)
        u = by_unit.setdefault(loc, {"location": loc, "printers": 0, "pages": 0, "cost": 0.0})
        u["printers"] += 1
        u["pages"] += delta
        u["cost"] = round(u["cost"] + rec["cost"], 2)
    printers.sort(key=lambda x: -x["pages"])
    units = sorted(by_unit.values(), key=lambda x: -x["pages"])
    return {"cost_per_page": cost, "printers": printers, "units": units,
            "total_pages": sum(p["pages"] for p in printers), "total_cost": round(sum(p["cost"] for p in printers), 2),
            "top_units": units[:10]}


def scheduler():
    import threading
    import time
    from datetime import datetime, timedelta
    last = [None]

    def loop():
        time.sleep(180)
        while True:
            try:
                h = float(db.get_setting("printer_poll_hours", 0) or 0)
                if h > 0 and (not last[0] or last[0] < datetime.now() - timedelta(hours=h)):
                    poll_all()
                    last[0] = datetime.now()
            except Exception as e:
                print("Yazıcı sorgu hatası:", e)
            time.sleep(600)
    threading.Thread(target=loop, daemon=True, name="printerpoll").start()
