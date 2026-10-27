"""Kurumlar paneli: diğer NexEnvanter sunucularının özetini (API anahtarıyla, salt okuma) tek ekranda toplar."""
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import APP_NAME, VERSION, db


def _get(url, token, timeout=8):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": f"{APP_NAME}/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def remotes():
    return [{**dict(r), "token": "••••" + r["token"][-4:]} for r in db.conn().execute("SELECT * FROM federation ORDER BY name")]


def save(data, rid=None):
    c = db.conn()
    url = (data.get("url") or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        raise ValueError("Adres http:// veya https:// ile başlamalı")
    if rid:
        sets = {k: v for k, v in {"name": data.get("name"), "url": url or None, "token": data.get("token") or None,
                                  "active": data.get("active")}.items() if v is not None}
        if sets:
            c.execute(f"UPDATE federation SET {','.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), rid))
    else:
        if not (data.get("name") and url and data.get("token")):
            raise ValueError("Ad, adres ve API anahtarı gerekli")
        c.execute("INSERT INTO federation(name,url,token) VALUES(?,?,?)", (data["name"].strip(), url, data["token"].strip()))


def delete(rid):
    db.conn().execute("DELETE FROM federation WHERE id=?", (rid,))


def poll(local_summary: dict) -> list[dict]:
    rows = [dict(r) for r in db.conn().execute("SELECT * FROM federation WHERE active=1 ORDER BY name")]

    def one(r):
        try:
            s = _get(r["url"] + "/api/summary", r["token"])
            return {"id": r["id"], "name": r["name"], "url": r["url"], "ok": True, "summary": s}
        except Exception as e:
            return {"id": r["id"], "name": r["name"], "url": r["url"], "ok": False, "error": str(e)[:200]}

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, rows))
    c = db.conn()
    for x in res:
        if x["ok"]:
            c.execute("UPDATE federation SET last_ok=?, last_error=NULL WHERE id=?", (db.now(), x["id"]))
        else:
            c.execute("UPDATE federation SET last_error=? WHERE id=?", (x["error"], x["id"]))
    me = {"id": 0, "name": local_summary.get("org_name") or "Bu kurum", "url": "", "ok": True, "summary": local_summary, "local": True}
    return [me] + res
