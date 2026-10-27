"""Dinamik alan kayıt defteri ve değer doğrulama."""
import json

from . import db
from .textnorm import cell_text, header_key, norm_date, norm_mac, norm_number, slug

TYPES = ("text", "longtext", "number", "date", "mac", "select")
LIMITS = {"text": 300, "longtext": 4000}


def _row(r) -> dict:
    d = dict(r)
    for k in ("options", "aliases"):
        d[k] = json.loads(d[k] or "[]")
    for k in ("required", "show_list", "show_preview", "public", "system", "active"):
        d[k] = bool(d[k])
    return d


def all_fields(active_only=True) -> list[dict]:
    q = "SELECT * FROM fields" + (" WHERE active=1" if active_only else "") + " ORDER BY sort, label"
    return [_row(r) for r in db.conn().execute(q)]


def by_key() -> dict:
    return {f["key"]: f for f in all_fields(False)}


def data_fields() -> list[dict]:
    """assets.data JSON içinde saklanan (sistem dışı) aktif alanlar."""
    return [f for f in all_fields() if not f["system"]]


def coerce(field: dict, value):
    """Ham değeri alan tipine göre normalize et. Hata → ValueError (Türkçe mesaj)."""
    t = field["type"]
    if t == "date":
        return norm_date(value)
    if t == "mac":
        return norm_mac(value)
    if t == "number":
        return norm_number(value)
    s = cell_text(value)
    if s is None:
        return None
    if t == "select" and field["options"] and s not in field["options"]:
        # büyük/küçük harf duyarsız eşleştir
        m = next((o for o in field["options"] if header_key(o) == header_key(s)), None)
        if m is None:
            raise ValueError(f"'{field['label']}' için geçersiz seçenek: {s}")
        s = m
    lim = LIMITS.get(t, 300)
    if len(s) > lim:
        raise ValueError(f"'{field['label']}' en fazla {lim} karakter olabilir")
    return s


def create(label: str, type_="text", key: str | None = None, aliases=None, **flags) -> dict:
    if type_ not in TYPES:
        raise ValueError("Geçersiz alan tipi")
    existing = by_key()
    key = slug(key or label)
    base, i = key, 2
    while key in existing:
        key = f"{base}_{i}"
        i += 1
    al = list(dict.fromkeys([header_key(label)] + [header_key(a) for a in (aliases or [])]))
    sort = max([f["sort"] for f in existing.values()] + [100]) + 10
    db.conn().execute(
        "INSERT INTO fields(key,label,type,aliases,show_list,show_preview,public,sort,options) VALUES(?,?,?,?,?,?,?,?,?)",
        (key, label.strip(), type_, json.dumps(al), int(flags.get("show_list", 1)), int(flags.get("show_preview", 0)),
         int(flags.get("public", 0)), sort, json.dumps(flags.get("options", []), ensure_ascii=False)))
    return by_key()[key]


EDITABLE = ("label", "type", "options", "aliases", "required", "show_list", "show_preview", "public", "sort", "active")


def update(key: str, patch: dict) -> dict:
    f = by_key().get(key)
    if not f:
        raise KeyError(key)
    sets, vals = [], []
    for k in EDITABLE:
        if k not in patch:
            continue
        v = patch[k]
        if f["system"] and k in ("type", "active") or (key == "asset_code" and k == "required"):
            continue
        if k == "type" and v not in TYPES:
            raise ValueError("Geçersiz alan tipi")
        if k in ("options", "aliases"):
            v = json.dumps([header_key(a) for a in v] if k == "aliases" else v, ensure_ascii=False)
        elif isinstance(v, bool):
            v = int(v)
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        db.conn().execute(f"UPDATE fields SET {','.join(sets)} WHERE key=?", (*vals, key))
    return by_key()[key]


def match_header(header: str, fields: list[dict], ignore: list[str]) -> str | None:
    """Excel başlığını alan anahtarına eşle. '__ignore__' / None (eşleşmedi)."""
    h = header_key(header)
    if not h:
        return "__ignore__"
    if h in [header_key(x) for x in ignore]:
        return "__ignore__"
    for f in fields:
        if h == header_key(f["label"]) or h == f["key"].replace("_", " ") or h in f["aliases"]:
            return f["key"]
    # kısmi eşleşme: başlık bir eş adı tam kelime olarak içeriyor (en uzun eş ad kazanır)
    best, blen = None, 0
    for f in fields:
        for a in f["aliases"]:
            if len(a) >= 3 and (f" {a} " in f" {h} ") and len(a) > blen:
                best, blen = f["key"], len(a)
    return best
