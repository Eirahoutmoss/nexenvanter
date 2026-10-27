"""Arıza / destek kayıtları. QR sayfasından oturumsuz bildirim + BİM iş takibi."""
import secrets
import time

from . import assets as A, db, kb
from .textnorm import fold

STATUSES = ["yeni", "atandı", "işlemde", "beklemede", "çözüldü", "kapalı"]
OPEN = ("yeni", "atandı", "işlemde", "beklemede")
PRIORITIES = ["düşük", "normal", "yüksek", "acil"]
_rate: dict[str, list[float]] = {}


def _row(r):
    return dict(r) if r else None


def create(description, asset_id=None, category=None, reporter_name=None, reporter_contact=None, reporter_unit=None,
           ip=None, source="panel", user=None, priority="normal") -> dict:
    description = (description or "").strip()
    if len(description) < 5:
        raise ValueError("Lütfen sorunu kısaca açıklayın (en az 5 karakter)")
    if priority not in PRIORITIES:
        priority = "normal"
    if source == "qr":
        if not db.get_setting("public_tickets", True):
            raise PermissionError("QR üzerinden arıza bildirimi kapalı")
        recent = [t for t in _rate.get(ip or "?", []) if t > time.time() - 600]
        if len(recent) >= 5:
            raise PermissionError("Çok fazla bildirim gönderildi; lütfen biraz sonra tekrar deneyin veya BİM'i arayın")
        _rate[ip or "?"] = recent + [time.time()]
        if not reporter_name or not str(reporter_name).strip():
            raise ValueError("Adınızı yazın")
    ts = db.now()
    code = secrets.token_hex(4).upper()
    cur = db.conn().execute(
        "INSERT INTO tickets(asset_id,status,priority,category,description,reporter_name,reporter_contact,reporter_unit,"
        "reporter_ip,source,created_at,updated_at,public_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (asset_id, "yeni", priority, (category or "")[:80] or None, description[:4000], (reporter_name or "")[:120] or None,
         (reporter_contact or "")[:120] or None, (reporter_unit or "")[:120] or None, ip, source, ts, ts, code))
    tid = cur.lastrowid
    if asset_id:
        A.add_event(asset_id, user or (reporter_name and f"{reporter_name} (QR)") or "QR", "ariza",
                    f"#{tid} {category or ''} — {description[:300]}")
    return get(tid)


def get(tid) -> dict | None:
    c = db.conn()
    t = _row(c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone())
    if not t:
        return None
    t["notes"] = [dict(r) for r in c.execute("SELECT * FROM ticket_notes WHERE ticket_id=? ORDER BY id", (tid,))]
    t["asset"] = A.get(t["asset_id"]) if t["asset_id"] else None
    return t


def by_code(code) -> dict | None:
    r = db.conn().execute("SELECT id FROM tickets WHERE public_code=?", ((code or "").upper(),)).fetchone()
    return get(r[0]) if r else None


def query(status=None, q="", asset_id=None, assigned=None, page=1, size=50, locations=None):
    where, args = [], []
    if status == "open":
        where.append(f"t.status IN ({','.join('?' * len(OPEN))})")
        args += OPEN
    elif status:
        where.append("t.status=?")
        args.append(status)
    if asset_id:
        where.append("t.asset_id=?")
        args.append(asset_id)
    if assigned:
        where.append("t.assigned_to=?")
        args.append(assigned)
    if locations is not None:
        locs = sorted({fold(x) for x in locations})
        where.append(f"(fold(json_extract(a.data,'$.location_name')) IN ({','.join('?' * len(locs))}) "
                     f"OR fold(t.reporter_unit) IN ({','.join('?' * len(locs))}))")
        args += locs + locs
    for tok in fold(q).split():
        where.append("fold(coalesce(t.description,'')||' '||coalesce(t.reporter_name,'')||' '||coalesce(a.asset_code,'')"
                     "||' '||coalesce(t.category,'')||' #'||t.id) LIKE ?")
        args.append(f"%{tok}%")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM tickets t LEFT JOIN assets a ON a.id=t.asset_id{w}"
    c = db.conn()
    total = c.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    size = max(1, min(int(size), 500))
    rows = c.execute(f"SELECT t.*, a.asset_code, json_extract(a.data,'$.location_name') location, "
                     f"json_extract(a.data,'$.brand_model') brand_model {base} "
                     f"ORDER BY CASE t.status WHEN 'yeni' THEN 0 WHEN 'atandı' THEN 1 WHEN 'işlemde' THEN 2 WHEN 'beklemede' THEN 3 ELSE 4 END,"
                     f" CASE t.priority WHEN 'acil' THEN 0 WHEN 'yüksek' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, t.id DESC LIMIT ? OFFSET ?",
                     (*args, size, (max(1, int(page)) - 1) * size))
    return {"total": total, "items": [dict(r) for r in rows]}


def add_note(tid, user, note):
    note = (note or "").strip()
    if not note:
        raise ValueError("Not boş olamaz")
    c = db.conn()
    c.execute("INSERT INTO ticket_notes(ticket_id,at,user,note) VALUES(?,?,?,?)", (tid, db.now(), user, note[:4000]))
    c.execute("UPDATE tickets SET updated_at=? WHERE id=?", (db.now(), tid))


def update(tid, patch: dict, user) -> dict:
    t = get(tid)
    if not t:
        raise KeyError(tid)
    sets, notes = {}, []
    if "status" in patch and patch["status"] != t["status"]:
        if patch["status"] not in STATUSES:
            raise ValueError("Geçersiz durum")
        sets["status"] = patch["status"]
        notes.append(f"Durum: {t['status']} → {patch['status']}")
        if patch["status"] in ("çözüldü", "kapalı") and not t["resolved_at"]:
            sets["resolved_at"] = db.now()
        if patch["status"] in OPEN:
            sets["resolved_at"] = None
    if "assigned_to" in patch and patch["assigned_to"] != t["assigned_to"]:
        sets["assigned_to"] = patch["assigned_to"] or None
        notes.append(f"Atanan: {patch['assigned_to'] or '—'}")
        if t["status"] == "yeni" and patch["assigned_to"] and "status" not in sets:
            sets["status"] = "atandı"
    if "priority" in patch and patch["priority"] in PRIORITIES and patch["priority"] != t["priority"]:
        sets["priority"] = patch["priority"]
        notes.append(f"Öncelik: {patch['priority']}")
    if "category" in patch:
        sets["category"] = patch["category"]
    if "asset_id" in patch and patch["asset_id"] != t["asset_id"]:
        sets["asset_id"] = patch["asset_id"] or None
    if "resolution" in patch:
        sets["resolution"] = (patch["resolution"] or "").strip() or None
    if sets:
        sets["updated_at"] = db.now()
        db.conn().execute(f"UPDATE tickets SET {','.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), tid))
    for n in notes:
        add_note(tid, user, n)
    if patch.get("note"):
        add_note(tid, user, patch["note"])
    if sets.get("status") in ("çözüldü", "kapalı") and t["asset_id"]:
        A.add_event(t["asset_id"], user, "ariza_cozuldu", f"#{tid} {sets.get('resolution') or t.get('resolution') or ''}")
    if patch.get("save_kb") and (sets.get("resolution") or t.get("resolution")):
        a = t["asset"] or {"data": {}}
        e = kb.create(patch.get("kb_title") or f"{t.get('category') or 'Arıza'}: {t['description'][:80]}",
                      f"Sorun:\n{t['description']}\n\nÇözüm:\n{sets.get('resolution') or t['resolution']}",
                      ", ".join(x for x in [a["data"].get("brand_model"), a["data"].get("hardware_info")] if x),
                      t.get("category"), user)
        db.conn().execute("UPDATE tickets SET kb_id=? WHERE id=?", (e["id"], tid))
    return get(tid)


def counts(locations=None) -> dict:
    where, args = "", []
    if locations is not None:
        locs = sorted({fold(x) for x in locations})
        where = f" AND fold(json_extract(a.data,'$.location_name')) IN ({','.join('?' * len(locs))})"
        args = locs
    r = db.conn().execute(
        f"SELECT t.status, COUNT(*) FROM tickets t LEFT JOIN assets a ON a.id=t.asset_id WHERE 1=1{where} GROUP BY t.status", args)
    d = {s: 0 for s in STATUSES}
    d.update({k: v for k, v in r})
    d["open"] = sum(d[s] for s in OPEN)
    return d
