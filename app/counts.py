"""Envanter sayımı: birim dolaşılarak QR/barkod okutulur; görülen / bulunamayan / yer değiştiren raporu."""
import re

from . import assets as A, db
from .textnorm import fold

_PUB = re.compile(r"/e/([A-Za-z0-9_-]{6,})")


def create(name, location, user) -> dict:
    name = (name or "").strip() or f"Sayım {db.now()[:10]}"
    cur = db.conn().execute("INSERT INTO counts(name,location,created_at,created_by) VALUES(?,?,?,?)",
                            (name[:120], (location or "").strip() or None, db.now(), user))
    db.audit(user, "count_create", cur.lastrowid, {"location": location})
    return summary(cur.lastrowid)


def _expected_sql(cnt):
    if cnt["location"]:
        return "archived=0 AND fold(json_extract(data,'$.location_name'))=?", [fold(cnt["location"])]
    return "archived=0", []


def get_raw(cid):
    r = db.conn().execute("SELECT * FROM counts WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def summary(cid) -> dict:
    cnt = get_raw(cid)
    if not cnt:
        raise KeyError(cid)
    c = db.conn()
    w, a = _expected_sql(cnt)
    cnt["expected"] = c.execute(f"SELECT COUNT(*) FROM assets WHERE {w}", a).fetchone()[0]
    cnt["seen"] = c.execute("SELECT COUNT(*) FROM count_items WHERE count_id=?", (cid,)).fetchone()[0]
    cnt["seen_expected"] = c.execute(
        f"SELECT COUNT(*) FROM count_items ci JOIN assets ON assets.id=ci.asset_id WHERE ci.count_id=? AND {w}", (cid, *a)).fetchone()[0]
    cnt["unknown"] = c.execute("SELECT COUNT(*) FROM count_unknown WHERE count_id=?", (cid,)).fetchone()[0]
    cnt["missing"] = cnt["expected"] - cnt["seen_expected"]
    cnt["foreign"] = cnt["seen"] - cnt["seen_expected"]
    cnt["progress"] = round(100 * cnt["seen_expected"] / cnt["expected"], 1) if cnt["expected"] else 0
    return cnt


def list_counts(locations=None):
    rows = [dict(r) for r in db.conn().execute("SELECT id FROM counts ORDER BY id DESC LIMIT 100")]
    out = [summary(r["id"]) for r in rows]
    if locations is not None:
        ls = {fold(x) for x in locations}
        out = [x for x in out if x["location"] and fold(x["location"]) in ls]
    return out


def resolve_code(code: str) -> dict | None:
    code = (code or "").strip()
    if not code:
        return None
    m = _PUB.search(code)
    if m:
        return A.get(public_id=m.group(1))
    return A.get_by_code(code)


def scan(cid, code, user, offline_at=None) -> dict:
    cnt = get_raw(cid)
    if not cnt:
        raise KeyError(cid)
    if cnt["status"] != "açık":
        raise ValueError("Bu sayım kapatılmış")
    a = resolve_code(code)
    c = db.conn()
    at = offline_at or db.now()
    if not a:
        c.execute("INSERT INTO count_unknown(count_id,code,seen_at,seen_by) VALUES(?,?,?,?)", (cid, code.strip()[:200], at, user))
        return {"result": "unknown", "code": code, "message": "Envanterde bulunamadı"}
    loc = a["data"].get("location_name")
    if c.execute("SELECT 1 FROM count_items WHERE count_id=? AND asset_id=?", (cid, a["id"])).fetchone():
        return {"result": "already", "asset": a, "message": "Zaten sayıldı"}
    c.execute("INSERT INTO count_items(count_id,asset_id,seen_at,seen_by,seen_location) VALUES(?,?,?,?,?)",
              (cid, a["id"], at, user, cnt["location"] or loc))
    other = bool(cnt["location"]) and fold(loc or "") != fold(cnt["location"])
    return {"result": "other_location" if other else "ok", "asset": a,
            "message": f"Kayıtlı yeri: {loc or '—'}" if other else "Sayıldı"}


def detail(cid) -> dict:
    cnt = summary(cid)
    c = db.conn()
    w, a = _expected_sql(cnt)
    sel = "SELECT id, asset_code, status, json_extract(data,'$.brand_model') brand_model, " \
          "json_extract(data,'$.hardware_info') hardware_info, json_extract(data,'$.location_name') location"
    cnt["missing_items"] = [dict(r) for r in c.execute(
        f"{sel} FROM assets WHERE {w} AND id NOT IN (SELECT asset_id FROM count_items WHERE count_id=?) ORDER BY asset_code", (*a, cid))]
    cnt["foreign_items"] = [dict(r) for r in c.execute(
        f"{sel}, ci.seen_at, ci.seen_by FROM count_items ci JOIN assets ON assets.id=ci.asset_id WHERE ci.count_id=? "
        f"AND NOT ({w}) ORDER BY asset_code", (cid, *a))] if cnt["location"] else []
    cnt["seen_items"] = [dict(r) for r in c.execute(
        f"{sel}, ci.seen_at, ci.seen_by FROM count_items ci JOIN assets ON assets.id=ci.asset_id WHERE ci.count_id=? "
        f"ORDER BY ci.seen_at DESC LIMIT 500", (cid,))]
    cnt["unknown_items"] = [dict(r) for r in c.execute("SELECT * FROM count_unknown WHERE count_id=? ORDER BY id DESC", (cid,))]
    return cnt


def close(cid, user, move_foreign=False) -> dict:
    cnt = detail(cid)
    if cnt["status"] != "açık":
        raise ValueError("Sayım zaten kapalı")
    moved = 0
    if move_foreign and cnt["location"]:
        for it in cnt["foreign_items"]:
            A.update(it["id"], {"location_name": cnt["location"]}, user, action="count")
            moved += 1
    for it in cnt["seen_items"]:
        A.add_event(it["id"], user, "sayim", f"{cnt['name']} — görüldü")
    db.conn().execute("UPDATE counts SET status='kapalı', closed_at=?, closed_by=? WHERE id=?", (db.now(), user, cid))
    db.audit(user, "count_close", cid, {"seen": cnt["seen"], "missing": cnt["missing"], "moved": moved})
    return {**summary(cid), "moved": moved}
