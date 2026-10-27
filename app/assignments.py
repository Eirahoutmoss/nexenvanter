"""Zimmet ve devir-teslim: kişiye/birime zimmet, iade, imzalı tutanak."""
from . import assets as A, db
from .textnorm import fold

KINDS = ("kişi", "birim")


def _next_doc(prefix: str) -> str:
    year = db.now()[:4]
    col = "doc_no" if prefix == "Z" else "return_doc_no"
    r = db.conn().execute(f"SELECT {col} FROM assignments WHERE {col} LIKE ? ORDER BY {col} DESC LIMIT 1",
                          (f"{prefix}-{year}-%",)).fetchone()
    n = int(r[0].rsplit("-", 1)[1]) + 1 if r else 1
    return f"{prefix}-{year}-{n:05d}"


def _check_sig(s):
    if s and (not isinstance(s, str) or not s.startswith("data:image/png;base64,") or len(s) > 400_000):
        raise ValueError("Geçersiz imza görseli")
    return s or None


def active(asset_id) -> dict | None:
    r = db.conn().execute("SELECT * FROM assignments WHERE asset_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
                          (asset_id,)).fetchone()
    return dict(r) if r else None


def history(asset_id) -> list[dict]:
    return [_lite(r) for r in db.conn().execute("SELECT * FROM assignments WHERE asset_id=? ORDER BY id DESC", (asset_id,))]


def _lite(r):
    d = dict(r)
    d["signed"] = bool(d.pop("signature", None))
    d.pop("giver_signature", None)
    d.pop("return_signature", None)
    return d


def assign(asset_ids, kind, holder_name, user, holder_title=None, holder_unit=None, note=None, signature=None,
           giver_signature=None) -> dict:
    if kind not in KINDS:
        raise ValueError("Zimmet türü kişi veya birim olmalı")
    holder_name = (holder_name or "").strip()
    if not holder_name:
        raise ValueError("Zimmet alanın adı gerekli")
    if not asset_ids:
        raise ValueError("Cihaz seçilmedi")
    signature, giver_signature = _check_sig(signature), _check_sig(giver_signature)
    with db.tx() as t:
        doc = _next_doc("Z")
        ts = db.now()
        for aid in asset_ids:
            a = A.get(aid)
            if not a:
                raise ValueError(f"Kayıt yok: {aid}")
            prev = active(aid)
            if prev:  # devir: önceki zimmet bu belgeyle kapanır
                t.execute("UPDATE assignments SET ended_at=?, ended_by=?, return_doc_no=? WHERE id=?", (ts, user, doc, prev["id"]))
            t.execute("INSERT INTO assignments(doc_no,asset_id,kind,holder_name,holder_title,holder_unit,started_at,created_by,note,"
                      "signature,giver_signature) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (doc, aid, kind, holder_name[:120], (holder_title or "")[:120] or None, (holder_unit or "")[:120] or None,
                       ts, user, (note or "")[:1000] or None, signature, giver_signature))
            A.add_event(aid, user, "zimmet", f"{doc}: {holder_name}" + (f" ({holder_unit})" if holder_unit else "")
                        + (f" — devreden: {prev['holder_name']}" if prev else ""))
    db.audit(user, "assign", doc, {"assets": len(asset_ids), "holder": holder_name})
    return {"doc_no": doc}


def release(asset_ids, user, return_signature=None, note=None) -> dict:
    return_signature = _check_sig(return_signature)
    with db.tx() as t:
        doc = _next_doc("I")
        n = 0
        for aid in asset_ids:
            prev = active(aid)
            if not prev:
                continue
            t.execute("UPDATE assignments SET ended_at=?, ended_by=?, return_doc_no=?, return_signature=?, "
                      "note=coalesce(note,'')||? WHERE id=?",
                      (db.now(), user, doc, return_signature, f"\nİade: {note}" if note else "", prev["id"]))
            A.add_event(aid, user, "zimmet_iade", f"{doc}: {prev['holder_name']} iade etti")
            n += 1
    if not n:
        raise ValueError("Seçilen cihazlarda aktif zimmet yok")
    db.audit(user, "assign_return", doc, {"assets": n})
    return {"doc_no": doc, "count": n}


def document(doc_no) -> dict | None:
    c = db.conn()
    rows = [dict(r) for r in c.execute("SELECT * FROM assignments WHERE doc_no=? ORDER BY id", (doc_no,))]
    prev = [dict(r) for r in c.execute("SELECT * FROM assignments WHERE return_doc_no=? ORDER BY id", (doc_no,))]
    kind = "devir" if rows and prev else "zimmet"
    if not rows:
        rows, prev, kind = prev, [], "iade"
    if not rows:
        return None
    for r in rows + prev:
        r["asset"] = A.get(r["asset_id"])
    return {"doc_no": doc_no, "kind": kind, "items": rows, "previous": prev}


def query(q="", active_only=True, page=1, size=100, locations=None):
    where, args = [], []
    if active_only:
        where.append("z.ended_at IS NULL")
    for tok in fold(q).split():
        where.append("fold(z.holder_name||' '||coalesce(z.holder_unit,'')||' '||z.doc_no||' '||a.asset_code) LIKE ?")
        args.append(f"%{tok}%")
    if locations is not None:
        locs = sorted({fold(x) for x in locations})
        where.append(f"fold(json_extract(a.data,'$.location_name')) IN ({','.join('?' * len(locs))})")
        args += locs
    w = (" WHERE " + " AND ".join(where)) if where else ""
    c = db.conn()
    base = f"FROM assignments z JOIN assets a ON a.id=z.asset_id{w}"
    total = c.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = c.execute(f"SELECT z.id,z.doc_no,z.asset_id,z.kind,z.holder_name,z.holder_title,z.holder_unit,z.started_at,z.ended_at,"
                     f"z.return_doc_no,a.asset_code,json_extract(a.data,'$.brand_model') brand_model {base} "
                     f"ORDER BY z.id DESC LIMIT ? OFFSET ?", (*args, size, (max(1, page) - 1) * size))
    return {"total": total, "items": [dict(r) for r in rows]}
