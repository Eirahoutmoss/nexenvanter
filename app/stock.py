"""Sarf malzeme stoku: toner, kartuş, kablo vb.; giriş/çıkış hareketleri ve en az stok uyarısı."""
from . import assets as A, db
from .textnorm import fold


def _row(r):
    d = dict(r)
    d["low"] = d["stock"] <= d["min_stock"]
    return d


def query(q="", low_only=False):
    where, args = ["active=1"], []
    for tok in fold(q).split():
        where.append("fold(name||' '||coalesce(code,'')||' '||coalesce(compatible,'')||' '||coalesce(location,'')) LIKE ?")
        args.append(f"%{tok}%")
    if low_only:
        where.append("stock<=min_stock")
    rows = db.conn().execute(f"SELECT * FROM consumables WHERE {' AND '.join(where)} ORDER BY (stock<=min_stock) DESC, name", args)
    return [_row(r) for r in rows]


def get(cid):
    r = db.conn().execute("SELECT * FROM consumables WHERE id=?", (cid,)).fetchone()
    if not r:
        return None
    d = _row(r)
    d["moves"] = [dict(x) for x in db.conn().execute(
        "SELECT m.*, a.asset_code FROM consumable_moves m LEFT JOIN assets a ON a.id=m.asset_id "
        "WHERE consumable_id=? ORDER BY m.id DESC LIMIT 200", (cid,))]
    return d


FIELDS = ("name", "code", "unit", "min_stock", "compatible", "location", "note", "active")


def save(data: dict, cid=None) -> dict:
    d = {k: data.get(k) for k in FIELDS if k in data}
    if not cid and not (d.get("name") or "").strip():
        raise ValueError("Malzeme adı gerekli")
    if "min_stock" in d:
        d["min_stock"] = float(d["min_stock"] or 0)
    if "active" in d:
        d["active"] = int(bool(d["active"]))
    c = db.conn()
    if cid:
        if d:
            c.execute(f"UPDATE consumables SET {','.join(k + '=?' for k in d)} WHERE id=?", (*d.values(), cid))
    else:
        d.setdefault("unit", "adet")
        cid = c.execute(f"INSERT INTO consumables({','.join(d)}) VALUES({','.join('?' * len(d))})", tuple(d.values())).lastrowid
    return get(cid)


def move(cid, qty, user, asset_id=None, note=None) -> dict:
    qty = float(qty)
    if qty == 0:
        raise ValueError("Miktar 0 olamaz")
    with db.tx() as t:
        r = t.execute("SELECT * FROM consumables WHERE id=?", (cid,)).fetchone()
        if not r:
            raise KeyError(cid)
        if r["stock"] + qty < 0:
            raise ValueError(f"Yetersiz stok (mevcut {r['stock']:g} {r['unit']})")
        t.execute("UPDATE consumables SET stock=stock+? WHERE id=?", (qty, cid))
        t.execute("INSERT INTO consumable_moves(consumable_id,at,user,qty,asset_id,note) VALUES(?,?,?,?,?,?)",
                  (cid, db.now(), user, qty, asset_id, (note or "")[:300] or None))
        if asset_id and qty < 0:
            A.add_event(asset_id, user, "sarf", f"{-qty:g} {r['unit']} {r['name']}" + (f" — {note}" if note else ""))
    return get(cid)


def for_asset(asset: dict) -> list[dict]:
    text = fold(" ".join(str(asset.get("data", {}).get(k) or "") for k in ("brand_model", "hardware_info")))
    out = []
    for r in db.conn().execute("SELECT * FROM consumables WHERE active=1 AND compatible IS NOT NULL AND compatible<>''"):
        if text.strip() and any(fold(k) and fold(k) in text for k in r["compatible"].split(",")):
            out.append(_row(r))
    return out


def low_count() -> int:
    return db.conn().execute("SELECT COUNT(*) FROM consumables WHERE active=1 AND stock<=min_stock").fetchone()[0]
