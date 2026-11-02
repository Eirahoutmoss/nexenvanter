"""Arıza çağrılarının analizi (sosyolojik açı): hangi birim, hangi saat, hangi modelde tekrar eden sorun.
Sorunun cihazda mı yoksa kullanım/eğitim alışkanlığında mı olduğunu ayırt etmeye yardımcı olur."""
import json
from datetime import date, datetime, timedelta

from . import db
from .textnorm import fold


def ticket_analysis(days=90, locations=None) -> dict:
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    c = db.conn()
    where = "t.created_at>=?"
    args = [since]
    if locations is not None:
        locs = sorted({fold(x) for x in locations})
        where += (f" AND (fold(json_extract(a.data,'$.location_name')) IN ({','.join('?' * len(locs))}) "
                  f"OR fold(t.reporter_unit) IN ({','.join('?' * len(locs))}))")
        args += locs + locs
    rows = list(c.execute(
        f"SELECT t.id, t.created_at, t.category, t.resolved_at, t.reporter_unit, t.reporter_name, "
        f"json_extract(a.data,'$.location_name') aloc, json_extract(a.data,'$.brand_model') model, "
        f"json_extract(a.data,'$.hardware_info') kind FROM tickets t LEFT JOIN assets a ON a.id=t.asset_id WHERE {where}", args))
    by_unit, by_hour, by_wday, by_model, by_cat = {}, [0] * 24, [0] * 7, {}, {}
    res_hours = []
    repeat_users = {}
    for r in rows:
        unit = r["aloc"] or r["reporter_unit"] or "(Belirtilmemiş)"
        by_unit[unit] = by_unit.get(unit, 0) + 1
        by_cat[r["category"] or "(Belirtilmemiş)"] = by_cat.get(r["category"] or "(Belirtilmemiş)", 0) + 1
        try:
            dt = datetime.fromisoformat(r["created_at"])
            by_hour[dt.hour] += 1
            by_wday[dt.weekday()] += 1
        except Exception:
            pass
        if r["model"]:
            m = by_model.setdefault(r["model"], {"model": r["model"], "count": 0, "cats": {}})
            m["count"] += 1
            m["cats"][r["category"] or "?"] = m["cats"].get(r["category"] or "?", 0) + 1
        if r["resolved_at"]:
            try:
                h = (datetime.fromisoformat(r["resolved_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds() / 3600
                if h >= 0:
                    res_hours.append(h)
            except Exception:
                pass
        if r["reporter_name"]:
            repeat_users[r["reporter_name"]] = repeat_users.get(r["reporter_name"], 0) + 1
    units = sorted(({"unit": k, "count": v} for k, v in by_unit.items()), key=lambda x: -x["count"])
    models = sorted(by_model.values(), key=lambda x: -x["count"])
    # Tekrar eden sorun: aynı modelde aynı kategori 3+ kez → cihaz/eğitim ayrımı için işaret
    recurring = []
    for m in models:
        for cat, n in m["cats"].items():
            if n >= 3:
                recurring.append({"model": m["model"], "category": cat, "count": n})
    recurring.sort(key=lambda x: -x["count"])
    wd = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    return {
        "days": days, "total": len(rows),
        "by_unit": units[:15],
        "by_category": sorted(({"category": k, "count": v} for k, v in by_cat.items()), key=lambda x: -x["count"]),
        "by_hour": [{"hour": h, "count": by_hour[h]} for h in range(24)],
        "by_weekday": [{"day": wd[i], "count": by_wday[i]} for i in range(7)],
        "top_models": models[:15],
        "recurring": recurring[:30],
        "repeat_reporters": sorted(({"name": k, "count": v} for k, v in repeat_users.items() if v >= 3), key=lambda x: -x["count"])[:15],
        "avg_resolution_hours": round(sum(res_hours) / len(res_hours), 1) if res_hours else None,
        "peak_hour": max(range(24), key=lambda h: by_hour[h]) if rows else None,
    }


def workload(days=30) -> dict:
    """BİM personeli arasında iş yükü dağılımı (atanan/çözülen arıza)."""
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    c = db.conn()
    out = {}
    for r in c.execute("SELECT assigned_to, COUNT(*) n, SUM(CASE WHEN status IN ('çözüldü','kapalı') THEN 1 ELSE 0 END) done "
                       "FROM tickets WHERE created_at>=? AND assigned_to IS NOT NULL GROUP BY assigned_to", (since,)):
        out[r["assigned_to"]] = {"user": r["assigned_to"], "assigned": r["n"], "resolved": r["done"]}
    return {"days": days, "staff": sorted(out.values(), key=lambda x: -x["assigned"])}
