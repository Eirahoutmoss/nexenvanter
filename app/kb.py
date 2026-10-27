"""Bilgi bankası (kurumsal hafıza): model/donanım bazlı bilinen sorun → çözüm notları."""
from . import db
from .textnorm import fold


def _search(title, body, match, tags):
    return fold(" ".join(x or "" for x in (title, body, match, tags)))


def create(title, body, match=None, tags=None, user=None) -> dict:
    title, body = (title or "").strip(), (body or "").strip()
    if not title or not body:
        raise ValueError("Başlık ve içerik gerekli")
    ts = db.now()
    cur = db.conn().execute(
        "INSERT INTO kb(title,body,match,tags,created_by,created_at,updated_by,updated_at,search) VALUES(?,?,?,?,?,?,?,?,?)",
        (title[:200], body[:20000], (match or "")[:500] or None, (tags or "")[:200] or None, user, ts, user, ts,
         _search(title, body, match, tags)))
    return get(cur.lastrowid)


def update(kid, patch, user) -> dict:
    e = get(kid)
    if not e:
        raise KeyError(kid)
    for k in ("title", "body", "match", "tags"):
        if k in patch:
            e[k] = patch[k]
    db.conn().execute("UPDATE kb SET title=?,body=?,match=?,tags=?,updated_by=?,updated_at=?,search=? WHERE id=?",
                      (e["title"], e["body"], e["match"], e["tags"], user, db.now(),
                       _search(e["title"], e["body"], e["match"], e["tags"]), kid))
    return get(kid)


def delete(kid):
    db.conn().execute("DELETE FROM kb WHERE id=?", (kid,))


def get(kid, count_view=False) -> dict | None:
    c = db.conn()
    if count_view:
        c.execute("UPDATE kb SET views=views+1 WHERE id=?", (kid,))
    r = c.execute("SELECT * FROM kb WHERE id=?", (kid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d.pop("search", None)
    return d


def query(q="", limit=200):
    where, args = [], []
    for tok in fold(q).split():
        where.append("search LIKE ?")
        args.append(f"%{tok}%")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.conn().execute(f"SELECT id,title,match,tags,updated_at,updated_by,views FROM kb{w} ORDER BY updated_at DESC LIMIT ?",
                             (*args, limit))
    return [dict(r) for r in rows]


def for_asset(asset: dict, limit=10) -> list[dict]:
    """Cihazın marka-model/donanım metninde anahtar kelimesi geçen kayıtlar."""
    text = fold(" ".join(str(asset.get("data", {}).get(k) or "") for k in ("brand_model", "hardware_info")))
    if not text.strip():
        return []
    out = []
    for r in db.conn().execute("SELECT id,title,match,views FROM kb WHERE match IS NOT NULL AND match<>''"):
        keys = [fold(k) for k in r["match"].split(",") if fold(k)]
        if any(k in text for k in keys):
            out.append(dict(r))
    return sorted(out, key=lambda x: -x["views"])[:limit]
