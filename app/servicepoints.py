"""Hizmet noktaları: 'Acil kayıt masası 3' gibi fiziksel noktalar; PC+yazıcı+ekran bir bütün olarak görünür.
Arıza ve durum 'hangi cihaz' değil 'hangi masa' düzeyinde izlenir."""
import json

from . import assets as A, db
from .textnorm import fold

ROLES = ["Bilgisayar", "Monitör", "Yazıcı", "Telefon", "Tarayıcı", "Diğer"]


def _status_of(asset_id) -> str:
    """Cihazın canlı durumu: açık alarm > arıza > ağ durumu > kayıt durumu."""
    c = db.conn()
    if c.execute("SELECT 1 FROM alerts WHERE asset_id=? AND state='açık' AND severity='kritik'", (asset_id,)).fetchone():
        return "kritik"
    if c.execute("SELECT 1 FROM tickets WHERE asset_id=? AND status IN ('yeni','atandı','işlemde','beklemede')", (asset_id,)).fetchone():
        return "arıza"
    if c.execute("SELECT 1 FROM alerts WHERE asset_id=? AND state='açık'", (asset_id,)).fetchone():
        return "uyarı"
    a = A.get(asset_id)
    return "pasif" if not a or a["status"] in ("arızalı", "hurda", "serviste") else "ok"


_RANK = {"kritik": 0, "arıza": 1, "uyarı": 2, "pasif": 3, "ok": 4}


def list_points(locations=None, with_items=True) -> list[dict]:
    c = db.conn()
    out = []
    for p in c.execute("SELECT * FROM service_points WHERE active=1 ORDER BY location, name"):
        if locations is not None and fold(p["location"] or "") not in {fold(x) for x in locations}:
            continue
        items = []
        worst = "ok"
        for it in c.execute("SELECT i.asset_id, i.role, a.asset_code, a.status, json_extract(a.data,'$.brand_model') brand_model "
                            "FROM service_point_items i JOIN assets a ON a.id=i.asset_id WHERE i.point_id=?", (p["id"],)):
            st = _status_of(it["asset_id"])
            if _RANK[st] < _RANK[worst]:
                worst = st
            items.append({**dict(it), "live": st})
        d = {**dict(p), "status": worst, "items": items if with_items else [], "count": len(items)}
        out.append(d)
    out.sort(key=lambda x: (_RANK.get(x["status"], 9), x["location"] or "", x["name"]))
    return out


def get(pid) -> dict | None:
    p = db.conn().execute("SELECT * FROM service_points WHERE id=?", (pid,)).fetchone()
    if not p:
        return None
    pts = list_points()
    return next((x for x in pts if x["id"] == pid), dict(p))


def save(data, pid=None) -> dict:
    d = {k: data[k] for k in ("name", "location", "note", "critical", "active") if k in data}
    if "name" in d and not (d["name"] or "").strip():
        raise ValueError("Nokta adı gerekli")
    for k in ("critical", "active"):
        if k in d:
            d[k] = int(bool(d[k]))
    c = db.conn()
    if pid:
        if d:
            c.execute(f"UPDATE service_points SET {','.join(k + '=?' for k in d)} WHERE id=?", (*d.values(), pid))
    else:
        d.setdefault("name", "")
        pid = c.execute(f"INSERT INTO service_points({','.join(d)},created_at) VALUES({','.join('?' * len(d))},?)",
                        (*d.values(), db.now())).lastrowid
    return get(pid)


def set_items(pid, items: list[dict]):
    """items: [{asset_id, role}]. Bir cihaz yalnızca bir noktada olabilir."""
    c = db.conn()
    c.execute("DELETE FROM service_point_items WHERE point_id=?", (pid,))
    for it in items:
        aid = int(it.get("asset_id") or 0)
        if aid and A.get(aid):
            c.execute("INSERT OR REPLACE INTO service_point_items(point_id,asset_id,role) VALUES(?,?,?)",
                      (pid, aid, (it.get("role") or "")[:40] or None))
    return get(pid)


def delete(pid):
    c = db.conn()
    c.execute("DELETE FROM service_point_items WHERE point_id=?", (pid,))
    c.execute("DELETE FROM service_points WHERE id=?", (pid,))


def point_of(asset_id) -> dict | None:
    r = db.conn().execute("SELECT p.id, p.name, p.location FROM service_point_items i JOIN service_points p ON p.id=i.point_id "
                          "WHERE i.asset_id=?", (asset_id,)).fetchone()
    return dict(r) if r else None
