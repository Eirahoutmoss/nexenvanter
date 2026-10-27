"""Envanter kayıtları: ekle, güncelle, ara, arşivle, geçmiş."""
import json
import secrets

from . import db, fields as F
from .textnorm import fold


class AssetError(Exception):
    def __init__(self, code, msg, status=400, extra=None):
        super().__init__(msg)
        self.code, self.msg, self.status, self.extra = code, msg, status, extra or {}


def _search_text(code, status, data: dict) -> str:
    return fold(" ".join([code or "", status or ""] + [str(v) for v in data.values() if v]))


def _out(r) -> dict:
    d = dict(r)
    d["data"] = json.loads(d["data"])
    d.pop("search", None)
    d["archived"] = bool(d["archived"])
    return d


def validate(payload: dict, partial=False) -> tuple[str | None, str | None, dict, dict]:
    """→ (asset_code, status, data, errors). payload düz sözlük: {asset_code, status, <alan>: değer}."""
    fmap = F.by_key()
    errors, data = {}, {}
    code = status = None
    if "asset_code" in payload or not partial:
        try:
            code = F.coerce(fmap["asset_code"], payload.get("asset_code"))
        except ValueError as e:
            errors["asset_code"] = str(e)
        if not code and "asset_code" not in errors:
            errors["asset_code"] = "Barkod / envanter no zorunlu"
    if "status" in payload:
        try:
            status = F.coerce(fmap["status"], payload.get("status")) or "aktif"
        except ValueError as e:
            errors["status"] = str(e)
    for k, v in payload.items():
        if k in ("asset_code", "status"):
            continue
        f = fmap.get(k)
        if not f or f["system"]:
            continue  # bilinmeyen anahtarlar yok sayılır
        try:
            data[k] = F.coerce(f, v)
        except ValueError as e:
            errors[k] = str(e)
    if not partial:
        for f in F.data_fields():
            if f["required"] and not data.get(f["key"]):
                errors[f["key"]] = f"'{f['label']}' zorunlu"
    return code, status, data, errors


def get(asset_id=None, public_id=None) -> dict | None:
    c = db.conn()
    r = (c.execute("SELECT * FROM assets WHERE id=?", (asset_id,)) if asset_id is not None
         else c.execute("SELECT * FROM assets WHERE public_id=?", (public_id,))).fetchone()
    return _out(r) if r else None


def get_by_code(code) -> dict | None:
    r = db.conn().execute("SELECT * FROM assets WHERE asset_code=?", (str(code),)).fetchone()
    return _out(r) if r else None


def create(payload: dict, user: str, source_import=None, t=None) -> dict:
    from . import license
    try:
        license.check_limit("assets", db.conn().execute("SELECT COUNT(*) FROM assets WHERE archived=0").fetchone()[0])
    except PermissionError as e:
        raise AssetError("LICENSE_LIMIT", str(e), 402)
    code, status, data, errors = validate(payload)
    if errors:
        raise AssetError("VALIDATION_ERROR", "Doğrulama hatası", 422, {"fields": errors})
    c = t or db.conn()
    if c.execute("SELECT 1 FROM assets WHERE asset_code=?", (code,)).fetchone():
        raise AssetError("ASSET_CODE_DUPLICATE", f"Bu barkod zaten kayıtlı: {code}", 409)
    data = {k: v for k, v in data.items() if v is not None}
    status = status or "aktif"
    ts = db.now()
    cur = c.execute(
        "INSERT INTO assets(public_id,asset_code,status,data,search,source_import,created_at,updated_at,created_by,updated_by)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (secrets.token_urlsafe(9), code, status, json.dumps(data, ensure_ascii=False), _search_text(code, status, data),
         source_import, ts, ts, user, user))
    aid = cur.lastrowid
    c.execute("INSERT INTO asset_events(asset_id,at,user,action,changes) VALUES(?,?,?,?,?)",
              (aid, ts, user, "import" if source_import else "create",
               json.dumps({"asset_code": code, **data}, ensure_ascii=False)))
    return get(aid) if t is None else {"id": aid}


def update(asset_id: int, payload: dict, user: str, blank_overwrites=True, t=None, action="update") -> dict:
    """Kısmi güncelleme. blank_overwrites=False ise boş değerler mevcut değeri silmez (Excel güncelleme)."""
    c = t or db.conn()
    r = c.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not r:
        raise AssetError("NOT_FOUND", "Kayıt bulunamadı", 404)
    cur = _out(r)
    code, status, data, errors = validate(payload, partial=True)
    if errors:
        raise AssetError("VALIDATION_ERROR", "Doğrulama hatası", 422, {"fields": errors})
    changes = {}
    new_code = cur["asset_code"]
    if code and code != cur["asset_code"]:
        if c.execute("SELECT 1 FROM assets WHERE asset_code=? AND id<>?", (code, asset_id)).fetchone():
            raise AssetError("ASSET_CODE_DUPLICATE", f"Bu barkod zaten kayıtlı: {code}", 409)
        changes["asset_code"] = [cur["asset_code"], code]
        new_code = code
    new_status = cur["status"]
    if status and status != cur["status"]:
        changes["status"] = [cur["status"], status]
        new_status = status
    nd = dict(cur["data"])
    for k, v in data.items():
        if v is None and not blank_overwrites:
            continue
        if nd.get(k) != v:
            changes[k] = [nd.get(k), v]
            if v is None:
                nd.pop(k, None)
            else:
                nd[k] = v
    if not changes:
        return cur if t is None else {"id": asset_id, "changed": False}
    ts = db.now()
    c.execute("UPDATE assets SET asset_code=?,status=?,data=?,search=?,updated_at=?,updated_by=? WHERE id=?",
              (new_code, new_status, json.dumps(nd, ensure_ascii=False), _search_text(new_code, new_status, nd), ts, user, asset_id))
    c.execute("INSERT INTO asset_events(asset_id,at,user,action,changes) VALUES(?,?,?,?,?)",
              (asset_id, ts, user, action, json.dumps(changes, ensure_ascii=False)))
    return get(asset_id) if t is None else {"id": asset_id, "changed": True}


def set_archived(asset_id: int, archived: bool, user: str, note=None):
    c = db.conn()
    if not c.execute("SELECT 1 FROM assets WHERE id=?", (asset_id,)).fetchone():
        raise AssetError("NOT_FOUND", "Kayıt bulunamadı", 404)
    ts = db.now()
    c.execute("UPDATE assets SET archived=?,updated_at=?,updated_by=? WHERE id=?", (int(archived), ts, user, asset_id))
    c.execute("INSERT INTO asset_events(asset_id,at,user,action,note) VALUES(?,?,?,?,?)",
              (asset_id, ts, user, "archive" if archived else "restore", note))
    return get(asset_id)


def add_event(asset_id: int, user: str, action: str, note: str = None):
    """Bakım/devir gibi elle girilen olaylar."""
    db.conn().execute("INSERT INTO asset_events(asset_id,at,user,action,note) VALUES(?,?,?,?,?)",
                      (asset_id, db.now(), user, action, note))


def events(asset_id: int, limit=200) -> list[dict]:
    rows = db.conn().execute("SELECT * FROM asset_events WHERE asset_id=? ORDER BY id DESC LIMIT ?", (asset_id, limit))
    return [{**dict(r), "changes": json.loads(r["changes"] or "{}")} for r in rows]


def _col(key: str, fmap: dict) -> str:
    if key in ("asset_code", "status", "created_at", "updated_at", "id"):
        return key
    if key in fmap:  # anahtarlar slug ([a-z0-9_]) — kayıt defterinden doğrulandı
        return f"json_extract(data,'$.{key}')"
    raise AssetError("BAD_FIELD", f"Bilinmeyen alan: {key}")


def _scope_sql(locations, where, args):
    if locations is not None:
        locs = sorted({fold(x) for x in locations})
        where.append(f"fold(json_extract(data,'$.location_name')) IN ({','.join('?' * len(locs))})")
        args += locs


def query(q="", status=None, archived="0", filters=None, sort="updated_at", direction="desc", page=1, size=50,
          ids=None, locations=None):
    fmap = F.by_key()
    where, args = [], []
    _scope_sql(locations, where, args)
    if archived in ("0", "1"):
        where.append("archived=?")
        args.append(int(archived))
    if status:
        where.append("status=?")
        args.append(status)
    if ids:
        where.append(f"id IN ({','.join('?' * len(ids))})")
        args += [int(i) for i in ids]
    for tok in fold(q).split():
        where.append("search LIKE ?")
        args.append(f"%{tok}%")
    for k, v in (filters or {}).items():
        if v in (None, ""):
            continue
        if k == "asset_code":
            where.append("asset_code LIKE ?")
            args.append(f"%{v}%")
        else:
            where.append(f"{_col(k, fmap)} = ?")
            args.append(v)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    c = db.conn()
    total = c.execute(f"SELECT COUNT(*) FROM assets{w}", args).fetchone()[0]
    d = "ASC" if str(direction).lower() == "asc" else "DESC"
    size = max(1, min(int(size), 1000))
    page = max(1, int(page))
    rows = c.execute(f"SELECT * FROM assets{w} ORDER BY {_col(sort, fmap)} COLLATE NOCASE {d}, id {d} LIMIT ? OFFSET ?",
                     (*args, size, (page - 1) * size))
    return {"total": total, "page": page, "size": size, "items": [_out(r) for r in rows]}


def distinct_values(key: str, limit=500, locations=None) -> list[str]:
    col = _col(key, F.by_key())
    where, args = [], []
    _scope_sql(locations, where, args)
    w = "".join(" AND " + x for x in where)
    rows = db.conn().execute(f"SELECT {col} v, COUNT(*) n FROM assets WHERE archived=0 AND {col} IS NOT NULL{w} "
                             f"GROUP BY v ORDER BY n DESC LIMIT ?", (*args, limit))
    return [r[0] for r in rows]


def stats(locations=None) -> dict:
    c = db.conn()
    where, a = [], []
    _scope_sql(locations, where, a)
    w = "".join(" AND " + x for x in where)
    by_status = {r[0]: r[1] for r in c.execute(f"SELECT status, COUNT(*) FROM assets WHERE archived=0{w} GROUP BY status", a)}
    by_loc = [{"name": r[0] or "(Belirtilmemiş)", "count": r[1]} for r in c.execute(
        f"SELECT json_extract(data,'$.location_name') l, COUNT(*) FROM assets WHERE archived=0{w} GROUP BY l ORDER BY 2 DESC LIMIT 12", a)]
    by_hw = [{"name": r[0] or "(Belirtilmemiş)", "count": r[1]} for r in c.execute(
        f"SELECT json_extract(data,'$.hardware_info') h, COUNT(*) FROM assets WHERE archived=0{w} GROUP BY h ORDER BY 2 DESC LIMIT 12", a)]
    recent = [_out(r) for r in c.execute(f"SELECT * FROM assets WHERE 1=1{w} ORDER BY updated_at DESC, id DESC LIMIT 8", a)]
    return {
        "total": sum(by_status.values()),
        "archived": c.execute(f"SELECT COUNT(*) FROM assets WHERE archived=1{w}", a).fetchone()[0],
        "by_status": by_status, "by_location": by_loc, "by_hardware": by_hw, "recent": recent,
        "failed_prints": c.execute("SELECT COUNT(*) FROM print_jobs WHERE status='failed'").fetchone()[0],
    }
