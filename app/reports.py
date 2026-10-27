"""Raporlar: yenileme/yatırım gerekçesi, denetim paketi (zip), taşınır listesi, hurda (terkin) tutanağı."""
import io
import json
import zipfile
from datetime import date, timedelta

from . import APP_NAME, VERSION, assets as A, db, exporter
from .textnorm import fold


def _years(d):
    try:
        return round((date.today() - date.fromisoformat(d[:10])).days / 365.25, 1)
    except Exception:
        return None


def renewal(locations=None) -> dict:
    cfg = db.get_setting("renewal") or {}
    age_lim, t_lim = float(cfg.get("age_years") or 5), int(cfg.get("tickets_12m") or 3)
    since = (date.today() - timedelta(days=365)).isoformat()
    c = db.conn()
    tick = {r[0]: r[1] for r in c.execute("SELECT asset_id, COUNT(*) FROM tickets WHERE created_at>=? AND asset_id IS NOT NULL "
                                          "GROUP BY asset_id", (since,))}
    maint = {r[0]: r[1] for r in c.execute("SELECT asset_id, COUNT(*) FROM asset_events WHERE action IN ('bakim','ariza_cozuldu') "
                                           "AND at>=? GROUP BY asset_id", (since,))}
    locs = None if locations is None else {fold(x) for x in locations}
    units: dict[str, dict] = {}
    cands = []
    for r in c.execute("SELECT id, asset_code, status, data FROM assets WHERE archived=0"):
        d = json.loads(r["data"])
        loc = d.get("location_name") or "(Belirtilmemiş)"
        if locs is not None and fold(loc) not in locs:
            continue
        age = _years(d.get("purchase_date")) if d.get("purchase_date") else None
        t, m = tick.get(r["id"], 0), maint.get(r["id"], 0)
        u = units.setdefault(loc, {"location": loc, "count": 0, "ages": [], "tickets": 0, "maint": 0, "faulty": 0, "candidates": 0})
        u["count"] += 1
        u["tickets"] += t
        u["maint"] += m
        u["faulty"] += r["status"] in ("arızalı", "serviste", "bakımda")
        if age is not None:
            u["ages"].append(age)
        reasons = []
        if age is not None and age >= age_lim:
            reasons.append(f"{age:g} yaş")
        if t >= t_lim:
            reasons.append(f"12 ayda {t} arıza")
        if r["status"] == "arızalı":
            reasons.append("arızalı")
        if reasons:
            u["candidates"] += 1
            cands.append({"id": r["id"], "asset_code": r["asset_code"], "location": loc, "brand_model": d.get("brand_model"),
                          "hardware_info": d.get("hardware_info"), "age": age, "tickets": t, "status": r["status"],
                          "reasons": ", ".join(reasons), "score": (age or 0) / age_lim + t / max(1, t_lim)})
    rows = []
    for u in units.values():
        ages = u.pop("ages")
        u["avg_age"] = round(sum(ages) / len(ages), 1) if ages else None
        u["age_known"] = len(ages)
        u["tickets_per_device"] = round(u["tickets"] / u["count"], 2) if u["count"] else 0
        rows.append(u)
    rows.sort(key=lambda x: (-x["candidates"], -(x["avg_age"] or 0)))
    cands.sort(key=lambda x: -x["score"])
    return {"units": rows, "candidates": cands[:1000], "thresholds": {"age_years": age_lim, "tickets_12m": t_lim}}


def renewal_xlsx(locations=None) -> bytes:
    r = renewal(locations)
    return exporter.book_multi({
        "Birimler": (["Birim", "Cihaz", "Ort. yaş", "Yaşı bilinen", "12 ay arıza", "Cihaz başı arıza", "Bakım/onarım", "Arızalı/serviste",
                      "Yenileme adayı"],
                     [[u["location"], u["count"], u["avg_age"], u["age_known"], u["tickets"], u["tickets_per_device"], u["maint"],
                       u["faulty"], u["candidates"]] for u in r["units"]]),
        "Yenileme adayları": (["Barkod", "Birim", "Donanım", "Marka Model", "Yaş", "12 ay arıza", "Durum", "Gerekçe"],
                              [[x["asset_code"], x["location"], x["hardware_info"], x["brand_model"], x["age"], x["tickets"],
                                x["status"], x["reasons"]] for x in r["candidates"]]),
    })


def tasinir_xlsx() -> bytes:
    rows = []
    for r in db.conn().execute("SELECT asset_code, status, archived, data FROM assets ORDER BY asset_code"):
        d = json.loads(r["data"])
        rows.append([d.get("tasinir_kodu"), d.get("sicil_no"), r["asset_code"],
                     " ".join(x for x in (d.get("hardware_info"), d.get("brand_model")) if x), d.get("serial_number"),
                     d.get("purchase_date"), d.get("purchase_price"), d.get("supplier"), d.get("location_name"),
                     "hurda/terkin" if r["archived"] and r["status"] == "hurda" else r["status"]])
    return exporter.book_multi({"Taşınır listesi": (
        ["Taşınır Kodu", "Sicil No", "Barkod", "Taşınır Adı", "Seri No", "Edinme Tarihi", "Edinme Bedeli", "Tedarikçi", "Birim", "Durum"],
        rows)})


def _xl_rows(sql, args=()):
    cur = db.conn().execute(sql, args)
    return [d[0] for d in cur.description], [list(r) for r in cur]


def audit_pack(start: str, end: str, user: str) -> bytes:
    end_x = end + "T23:59:59"
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("01_envanter_tum.xlsx", exporter.export_assets(archived="all", sort="asset_code", direction="asc"))
        z.writestr("02_tasinir_listesi.xlsx", tasinir_xlsx())
        for name, sql, args in [
            ("03_zimmetler.xlsx", "SELECT z.doc_no Belge, a.asset_code Barkod, z.kind Tur, z.holder_name ZimmetAlan, z.holder_title Unvan, "
                                  "z.holder_unit Birim, z.started_at Baslangic, z.ended_at Bitis, z.return_doc_no IadeBelge, "
                                  "z.created_by Kaydeden, CASE WHEN z.signature IS NOT NULL THEN 'Evet' ELSE '' END Imzali "
                                  "FROM assignments z JOIN assets a ON a.id=z.asset_id ORDER BY z.id", ()),
            ("04_hurda_terkin.xlsx", "SELECT doc_no Belge, at Tarih, user Kullanici, reason Gerekce, commission Komisyon, asset_ids Kayitlar "
                                     "FROM disposals ORDER BY id", ()),
            ("05_degisiklik_gecmisi.xlsx", "SELECT e.at Tarih, a.asset_code Barkod, e.user Kullanici, e.action Islem, e.changes Degisiklik, "
                                           "e.note Not_ FROM asset_events e JOIN assets a ON a.id=e.asset_id WHERE e.at BETWEEN ? AND ? "
                                           "ORDER BY e.id", (start, end_x)),
            ("06_denetim_kaydi.xlsx", "SELECT at Tarih, user Kullanici, ip IP, action Islem, target Hedef, detail Ayrinti FROM audit "
                                      "WHERE at BETWEEN ? AND ? ORDER BY id", (start, end_x)),
            ("07_sayimlar.xlsx", "SELECT id No, name Ad, location Birim, status Durum, created_at Baslangic, created_by Baslatan, "
                                 "closed_at Bitis, closed_by Kapatan, (SELECT COUNT(*) FROM count_items WHERE count_id=counts.id) Sayilan "
                                 "FROM counts ORDER BY id", ()),
            ("08_arizalar.xlsx", "SELECT t.id No, t.created_at Tarih, a.asset_code Barkod, t.category Kategori, t.description Aciklama, "
                                 "t.reporter_name Bildiren, t.status Durum, t.assigned_to Atanan, t.resolved_at Cozum_Tarihi, t.resolution Cozum "
                                 "FROM tickets t LEFT JOIN assets a ON a.id=t.asset_id WHERE t.created_at BETWEEN ? AND ? ORDER BY t.id",
             (start, end_x)),
        ]:
            h, rows = _xl_rows(sql, args)
            z.writestr(name, exporter.book_multi({"Veri": (h, rows)}))
        s = db.all_settings()
        z.writestr("BENIOKU.txt", (
            f"{APP_NAME} {VERSION} denetim paketi\r\nKurum: {s.get('org_name')}\r\nBirim: {s.get('unit_name')}\r\n"
            f"Dönem: {start} — {end}\r\nOluşturan: {user}\r\nOluşturma: {db.now()}\r\n\r\n"
            "01 tüm envanter (arşiv dahil), 02 taşınır listesi, 03 zimmet/devir kayıtları, 04 hurda-terkin tutanakları,\r\n"
            "05 dönem içi kayıt değişiklikleri, 06 dönem içi sistem denetim kaydı, 07 sayımlar, 08 dönem içi arıza kayıtları.\r\n"
        ).encode("utf-8-sig"))
    db.audit(user, "audit_pack", None, {"start": start, "end": end})
    return b.getvalue()


def _next_doc():
    year = db.now()[:4]
    r = db.conn().execute("SELECT doc_no FROM disposals WHERE doc_no LIKE ? ORDER BY doc_no DESC LIMIT 1", (f"H-{year}-%",)).fetchone()
    return f"H-{year}-{(int(r[0].rsplit('-', 1)[1]) + 1) if r else 1:05d}"


def dispose(asset_ids, reason, commission, user) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Hurdaya ayırma gerekçesi gerekli")
    if not asset_ids:
        raise ValueError("Cihaz seçilmedi")
    members = [m for m in (commission or []) if (m.get("name") or "").strip()]
    doc = _next_doc()
    for aid in asset_ids:
        A.update(aid, {"status": "hurda"}, user, action="hurda")
        A.set_archived(aid, True, user, f"{doc}: {reason}")
    db.conn().execute("INSERT INTO disposals(doc_no,at,user,reason,commission,asset_ids) VALUES(?,?,?,?,?,?)",
                      (doc, db.now(), user, reason[:2000], json.dumps(members, ensure_ascii=False), json.dumps(asset_ids)))
    db.audit(user, "dispose", doc, {"count": len(asset_ids)})
    return {"doc_no": doc}


def disposal(doc_no) -> dict | None:
    r = db.conn().execute("SELECT * FROM disposals WHERE doc_no=?", (doc_no,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["commission"] = json.loads(d["commission"] or "[]")
    d["assets"] = [A.get(i) for i in json.loads(d["asset_ids"])]
    return d


def disposals():
    return [dict(r) for r in db.conn().execute("SELECT id,doc_no,at,user,reason,asset_ids FROM disposals ORDER BY id DESC")]
