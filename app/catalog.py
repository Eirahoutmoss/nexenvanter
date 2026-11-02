"""Envanter türleri ve kategoriler: tür seçilince kategori atanır, barkod boşsa kategoriye ait ardışık numara verilir."""
import json
import threading

from . import db
from .textnorm import fold

LOCK = threading.RLock()  # numara ayırma ile kayıt oluşturma arasında yarış olmasın


def categories(active_only=False) -> list[dict]:
    q = "SELECT c.*, (SELECT COUNT(*) FROM asset_types t WHERE t.category_id=c.id) types FROM asset_categories c"
    rows = [dict(r) for r in db.conn().execute(q + (" WHERE c.active=1" if active_only else "") + " ORDER BY c.name")]
    for r in rows:
        r["next_code"] = format_code(r, r["next_no"])
    return rows


def types(active_only=False) -> list[dict]:
    q = ("SELECT t.*, c.name category, c.prefix, c.digits, c.next_no FROM asset_types t "
         "JOIN asset_categories c ON c.id=t.category_id")
    rows = [dict(r) for r in db.conn().execute(q + (" WHERE t.active=1" if active_only else "") + " ORDER BY t.name")]
    for r in rows:
        r["aliases"] = json.loads(r["aliases"] or "[]")
    return rows


def format_code(cat: dict, n: int) -> str:
    return f"{cat.get('prefix') or ''}{int(n):0{int(cat.get('digits') or 0)}d}"


def resolve(type_name) -> dict | None:
    """Tür adından (veya eş adından ya da doğrudan kategori adından) kategori bul."""
    key = fold(type_name)
    if not key:
        return None
    for t in types(active_only=True):
        if fold(t["name"]) == key or key in (fold(a) for a in t["aliases"]):
            return {"type": t["name"], "category_id": t["category_id"], "category": t["category"]}
    r = db.conn().execute("SELECT id, name FROM asset_categories WHERE active=1 AND fold(name)=?", (key,)).fetchone()
    return {"type": None, "category_id": r["id"], "category": r["name"]} if r else None


def _cat(cid) -> dict:
    return dict(db.conn().execute("SELECT * FROM asset_categories WHERE id=?", (cid,)).fetchone())


def peek_code(category_id) -> str:
    """Kullanılmamış ilk numara (ardışık; elle girilmiş çakışanlar atlanır)."""
    cat = _cat(category_id)
    n = cat["next_no"]
    c = db.conn()
    while c.execute("SELECT 1 FROM assets WHERE asset_code=?", (format_code(cat, n),)).fetchone():
        n += 1
    return format_code(cat, n)


def commit_code(category_id, code: str):
    """Kayıt oluştuktan sonra sayaç verilen numaranın bir sonrasına ilerler."""
    cat = _cat(category_id)
    pre = cat["prefix"] or ""
    tail = code[len(pre):] if code.startswith(pre) else ""
    if tail.isdigit():
        db.conn().execute("UPDATE asset_categories SET next_no=MAX(next_no, ?) WHERE id=?", (int(tail) + 1, category_id))


def next_for(type_name) -> dict | None:
    r = resolve(type_name)
    return {**r, "code": peek_code(r["category_id"])} if r else None


# ---------- yönetim ----------
def save_category(data: dict, cid=None) -> dict:
    d = {k: data[k] for k in ("name", "prefix", "digits", "next_no", "active") if k in data}
    if "name" in d:
        d["name"] = (d["name"] or "").strip()
        if not d["name"]:
            raise ValueError("Kategori adı gerekli")
    if "digits" in d and not 0 <= int(d["digits"]) <= 12:
        raise ValueError("Basamak sayısı 0–12 olmalı")
    if "next_no" in d and int(d["next_no"]) < 1:
        raise ValueError("Sıradaki numara 1 veya büyük olmalı")
    if "prefix" in d:
        d["prefix"] = (d["prefix"] or "").strip()[:20]
    if "active" in d:
        d["active"] = int(bool(d["active"]))
    c = db.conn()
    try:
        if cid:
            if d:
                c.execute(f"UPDATE asset_categories SET {','.join(k + '=?' for k in d)} WHERE id=?", (*d.values(), cid))
        else:
            cid = c.execute(f"INSERT INTO asset_categories({','.join(d)}) VALUES({','.join('?' * len(d))})",
                            tuple(d.values())).lastrowid
    except Exception as e:
        if "UNIQUE" in str(e):
            raise ValueError("Bu adla kategori zaten var")
        raise
    return next(x for x in categories() if x["id"] == cid)


def save_type(data: dict, tid=None) -> dict:
    d = {}
    if "name" in data:
        d["name"] = (data["name"] or "").strip()
        if not d["name"]:
            raise ValueError("Tür adı gerekli")
    if "category_id" in data:
        if not db.conn().execute("SELECT 1 FROM asset_categories WHERE id=?", (data["category_id"],)).fetchone():
            raise ValueError("Kategori bulunamadı")
        d["category_id"] = int(data["category_id"])
    if "aliases" in data:
        d["aliases"] = json.dumps([a.strip() for a in data["aliases"] if a.strip()], ensure_ascii=False)
    if "active" in data:
        d["active"] = int(bool(data["active"]))
    if not tid and ("name" not in d or "category_id" not in d):
        raise ValueError("Tür adı ve kategori gerekli")
    c = db.conn()
    try:
        if tid:
            if d:
                c.execute(f"UPDATE asset_types SET {','.join(k + '=?' for k in d)} WHERE id=?", (*d.values(), tid))
        else:
            tid = c.execute(f"INSERT INTO asset_types({','.join(d)}) VALUES({','.join('?' * len(d))})", tuple(d.values())).lastrowid
    except Exception as e:
        if "UNIQUE" in str(e):
            raise ValueError("Bu adla tür zaten var")
        raise
    return next(x for x in types() if x["id"] == tid)


def delete_type(tid):
    db.conn().execute("DELETE FROM asset_types WHERE id=?", (tid,))


def delete_category(cid):
    c = db.conn()
    if c.execute("SELECT 1 FROM asset_types WHERE category_id=?", (cid,)).fetchone():
        raise ValueError("Bu kategoriye bağlı türler var; önce türleri taşıyın veya silin")
    c.execute("DELETE FROM asset_categories WHERE id=?", (cid,))
