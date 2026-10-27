"""Periyodik bakım planları ve garanti bitiş uyarıları."""
from datetime import date, timedelta

from . import assets as A, db
from .textnorm import fold


def create(asset_ids, title, interval_days, first_due, user, note=None) -> int:
    title = (title or "").strip()
    if not title:
        raise ValueError("Bakım adı gerekli")
    interval_days = int(interval_days or 0)
    if not 1 <= interval_days <= 3650:
        raise ValueError("Periyot 1–3650 gün olmalı")
    first_due = date.fromisoformat(first_due).isoformat() if first_due else (date.today() + timedelta(days=interval_days)).isoformat()
    n = 0
    for aid in asset_ids:
        if not A.get(aid):
            continue
        db.conn().execute("INSERT INTO maintenance_plans(asset_id,title,interval_days,next_due,note,created_by,created_at)"
                          " VALUES(?,?,?,?,?,?,?)", (aid, title[:120], interval_days, first_due, note, user, db.now()))
        n += 1
    return n


def done(pid, user, note=None, done_date=None) -> dict:
    c = db.conn()
    p = c.execute("SELECT * FROM maintenance_plans WHERE id=?", (pid,)).fetchone()
    if not p:
        raise KeyError(pid)
    d = date.fromisoformat(done_date) if done_date else date.today()
    nxt = (d + timedelta(days=p["interval_days"])).isoformat()
    c.execute("UPDATE maintenance_plans SET last_done=?, next_due=? WHERE id=?", (d.isoformat(), nxt, pid))
    A.add_event(p["asset_id"], user, "bakim", f"{p['title']} yapıldı" + (f" — {note}" if note else "") + f" (sonraki: {nxt})")
    return {"next_due": nxt}


def update(pid, patch):
    sets = {k: patch[k] for k in ("title", "interval_days", "next_due", "note", "active") if k in patch}
    if "active" in sets:
        sets["active"] = int(bool(sets["active"]))
    if sets:
        db.conn().execute(f"UPDATE maintenance_plans SET {','.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), pid))


def for_asset(aid):
    return [dict(r) for r in db.conn().execute(
        "SELECT * FROM maintenance_plans WHERE asset_id=? AND active=1 ORDER BY next_due", (aid,))]


def _loc_filter(locations, alias="a"):
    if locations is None:
        return "", []
    locs = sorted({fold(x) for x in locations})
    return f" AND fold(json_extract({alias}.data,'$.location_name')) IN ({','.join('?' * len(locs))})", locs


def agenda(days=None, locations=None) -> dict:
    days = int(days if days is not None else db.get_setting("maintenance_warn_days", 14))
    wdays = int(db.get_setting("warranty_warn_days", 60))
    today = date.today()
    lim = (today + timedelta(days=days)).isoformat()
    lw, la = _loc_filter(locations)
    c = db.conn()
    plans = [dict(r) for r in c.execute(
        f"SELECT m.*, a.asset_code, json_extract(a.data,'$.brand_model') brand_model, json_extract(a.data,'$.location_name') location "
        f"FROM maintenance_plans m JOIN assets a ON a.id=m.asset_id WHERE m.active=1 AND a.archived=0 AND m.next_due<=?{lw} "
        f"ORDER BY m.next_due", (lim, *la))]
    for p in plans:
        p["overdue"] = p["next_due"] < today.isoformat()
    wlim = (today + timedelta(days=wdays)).isoformat()
    warr = [dict(r) for r in c.execute(
        f"SELECT a.id, a.asset_code, json_extract(a.data,'$.brand_model') brand_model, json_extract(a.data,'$.location_name') location, "
        f"json_extract(a.data,'$.warranty_end') warranty_end FROM assets a WHERE a.archived=0 "
        f"AND json_extract(a.data,'$.warranty_end') IS NOT NULL AND json_extract(a.data,'$.warranty_end') <= ? "
        f"AND json_extract(a.data,'$.warranty_end') >= ?{lw} ORDER BY warranty_end", (wlim, (today - timedelta(days=30)).isoformat(), *la))]
    for w in warr:
        w["expired"] = w["warranty_end"] < today.isoformat()
    all_plans = [dict(r) for r in c.execute(
        f"SELECT m.*, a.asset_code, json_extract(a.data,'$.brand_model') brand_model FROM maintenance_plans m "
        f"JOIN assets a ON a.id=m.asset_id WHERE m.active=1{lw} ORDER BY m.next_due LIMIT 1000", la)]
    return {"due": plans, "warranty": warr, "plans": all_plans,
            "overdue": sum(1 for p in plans if p["overdue"]), "days": days, "warranty_days": wdays}
