"""Değişiklik ve kayıp alarmları: donanım değişikliği, seri no değişimi, çevrimdışı kalma, toner/yazıcı hatası.
Açık alarmlar panoda ve rozetlerde görünür; istenirse arıza kaydına dönüştürülür."""
import json
from datetime import datetime, timedelta

from . import assets as A, db
from .textnorm import fold

SEVERITIES = ("bilgi", "uyarı", "kritik")


def raise_alert(asset_id, kind, message, severity="uyarı", data=None, dedup=None, ticket=False):
    """Aynı dedup ile açık alarm varsa tekrar oluşturmaz (yalnızca zamanını günceller)."""
    c = db.conn()
    if dedup:
        ex = c.execute("SELECT id FROM alerts WHERE dedup=? AND state='açık'", (dedup,)).fetchone()
        if ex:
            c.execute("UPDATE alerts SET at=?, message=?, data=? WHERE id=?",
                      (db.now(), message, json.dumps(data or {}, ensure_ascii=False), ex[0]))
            return ex[0]
    tid = None
    if ticket and asset_id:
        from . import tickets
        tid = tickets.create(message, asset_id, "Otomatik", "NexEnvanter", source="panel", user="sistem")["id"]
    aid = c.execute("INSERT INTO alerts(at,asset_id,kind,severity,message,data,dedup,ticket_id) VALUES(?,?,?,?,?,?,?,?)",
                    (db.now(), asset_id, kind, severity, message, json.dumps(data or {}, ensure_ascii=False), dedup, tid)).lastrowid
    return aid


def query(state="açık", severity=None, page=1, size=100, locations=None):
    where, args = [], []
    if state and state != "all":
        where.append("al.state=?")
        args.append(state)
    if severity:
        where.append("al.severity=?")
        args.append(severity)
    if locations is not None:
        locs = sorted({fold(x) for x in locations})
        where.append(f"fold(json_extract(a.data,'$.location_name')) IN ({','.join('?' * len(locs))})")
        args += locs
    w = (" WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM alerts al LEFT JOIN assets a ON a.id=al.asset_id{w}"
    c = db.conn()
    total = c.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
    rows = c.execute(f"SELECT al.*, a.asset_code, json_extract(a.data,'$.location_name') location, "
                     f"json_extract(a.data,'$.brand_model') brand_model {base} "
                     f"ORDER BY CASE al.severity WHEN 'kritik' THEN 0 WHEN 'uyarı' THEN 1 ELSE 2 END, al.at DESC LIMIT ? OFFSET ?",
                     (*args, size, (max(1, page) - 1) * size))
    out = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"] or "{}")
        out.append(d)
    return {"total": total, "items": out, "open": c.execute("SELECT COUNT(*) FROM alerts WHERE state='açık'").fetchone()[0]}


def count_open(locations=None) -> int:
    if locations is None:
        return db.conn().execute("SELECT COUNT(*) FROM alerts WHERE state='açık'").fetchone()[0]
    locs = sorted({fold(x) for x in locations})
    return db.conn().execute(
        f"SELECT COUNT(*) FROM alerts al JOIN assets a ON a.id=al.asset_id WHERE al.state='açık' "
        f"AND fold(json_extract(a.data,'$.location_name')) IN ({','.join('?' * len(locs))})", locs).fetchone()[0]


def resolve(alert_id, user, make_ticket=False) -> dict:
    c = db.conn()
    al = c.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
    if not al:
        raise KeyError(alert_id)
    tid = al["ticket_id"]
    if make_ticket and not tid and al["asset_id"]:
        from . import tickets
        tid = tickets.create(al["message"], al["asset_id"], "Otomatik", user, source="panel", user=user)["id"]
    c.execute("UPDATE alerts SET state='kapalı', ack_by=?, ack_at=?, ticket_id=COALESCE(ticket_id,?) WHERE id=?",
              (user, db.now(), tid, alert_id))
    return {"ok": True, "ticket_id": tid}


def ack(alert_id, user):
    db.conn().execute("UPDATE alerts SET state='görüldü', ack_by=?, ack_at=? WHERE id=?", (user, db.now(), alert_id))


# ---------------- otomatik denetimler ----------------
def check_offline():
    """Envanterdeki, ağda görülen ama N gündür görülmeyen (özellikle kritik) cihazlar için alarm."""
    days = int(db.get_setting("offline_alert_days", 3) or 3)
    lim = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    c = db.conn()
    seen = {}
    for r in c.execute("SELECT mac, last_seen FROM net_seen"):
        seen[r["mac"]] = r["last_seen"]
    for r in c.execute("SELECT ip, last_seen FROM net_hosts"):
        pass
    for a in c.execute("SELECT id, asset_code, critical, data FROM assets WHERE archived=0 "
                       "AND json_extract(data,'$.mac_address') IS NOT NULL"):
        d = json.loads(a["data"])
        macs = [m.strip().upper() for m in str(d.get("mac_address") or "").split(",") if m.strip()]
        last = max((seen.get(m, "") for m in macs), default="")
        ever = any(m in seen for m in macs)
        if ever and last and last < lim:
            raise_alert(a["id"], "cevrimdisi", f"{a['asset_code']} {days} gündür ağda görülmüyor (son: {last[:10]})",
                        severity="kritik" if a["critical"] else "uyarı", data={"last_seen": last},
                        dedup=f"offline:{a['id']}")


def check_agent_change(asset_id, before: dict, after: dict):
    """Ajan bildirimi öncesi/sonrası donanım karşılaştırması (parça değişimi / cihaz değişimi şüphesi)."""
    a = A.get(asset_id)
    if not a:
        return
    code = a["asset_code"]
    for key, label in [("serial", "Seri no"), ("ram_gb", "RAM"), ("disk", "Disk"), ("cpu", "İşlemci")]:
        b, af = before.get(key), after.get(key)
        if b and af and fold(str(b)) != fold(str(af)):
            sev = "kritik" if key == "serial" else "uyarı"
            raise_alert(asset_id, "donanim_degisti", f"{code}: {label} değişti ({b} → {af})", severity=sev,
                        data={"field": key, "before": b, "after": af}, dedup=f"hw:{asset_id}:{key}:{fold(str(af))}")


def scheduler():
    import threading
    import time

    def loop():
        time.sleep(120)
        while True:
            try:
                check_offline()
            except Exception as e:
                print("Alarm denetimi hatası:", e)
            time.sleep(6 * 3600)
    threading.Thread(target=loop, daemon=True, name="alerts").start()
