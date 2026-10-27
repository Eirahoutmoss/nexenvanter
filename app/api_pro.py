"""Pro modüllerin HTTP katmanı: arıza, sayım, zimmet, bakım, sarf, bilgi bankası, ağ, ajan, raporlar,
kurumlar paneli, API anahtarları, AD testi, lisans, QR sayfası ve yazdırılabilir tutanaklar."""
import html
import json
import re
import string
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from . import (agent, assets as A, assignments as Z, auth, counts as C, db, exporter, federation, fields as F, kb,
               license, maintenance as M, network as N, reports as R, stock as S, tickets as T)
from . import VERSION
from .api import ApiError, base_url, body, current_user, ip, need, scoped_asset
from .paths import DIRS

router = APIRouter()
esc = html.escape


def _xlsx(data: bytes, name: str):
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _ids(v) -> list[int]:
    ids = [int(x) for x in (v.split(",") if isinstance(v, str) else v or []) if str(x).strip().isdigit()]
    if not ids:
        raise ApiError(400, "BAD_REQUEST", "Cihaz seçilmedi")
    return ids[:5000]


def _scoped_ids(u, ids):
    for i in ids:
        scoped_asset(u, i)
    return ids


class _Safe(dict):
    def __missing__(self, k):
        return ""


def remote_url(a: dict) -> str | None:
    tpl = (db.get_setting("remote_url_template") or "").strip()
    if not tpl:
        return None
    vals = _Safe({"asset_code": a["asset_code"], "public_id": a["public_id"], **{k: str(v) for k, v in a["data"].items()}})
    keys = [f for _, f, _, _ in string.Formatter().parse(tpl) if f]
    if any(not vals.get(k) for k in keys):
        return None
    return tpl.format_map(vals)


def asset_extras(a: dict, u: dict) -> dict:
    return {
        "assignment": Z.active(a["id"]), "assignments": Z.history(a["id"]), "maintenance": M.for_asset(a["id"]),
        "kb": kb.for_asset(a) if auth.can(u, "kb.read") else [], "consumables": S.for_asset(a) if auth.can(u, "stock.read") else [],
        "network": N.for_asset(a) if auth.can(u, "network") else [],
        "tickets": T.query(asset_id=a["id"], size=20)["items"] if auth.can(u, "ticket.read") else [],
        "remote_url": remote_url(a),
    }


# ---------------- özet ----------------
def summary_data(u=None) -> dict:
    sc = auth.scope(u)
    st = A.stats(sc)
    ag = M.agenda(locations=sc)
    tc = T.counts(sc)
    c = db.conn()
    return {"org_name": db.get_setting("org_name"), "version": VERSION, "assets": st["total"],
            "by_status": st["by_status"], "archived": st["archived"], "tickets_open": tc["open"], "tickets_new": tc["yeni"],
            "maint_overdue": ag["overdue"], "maint_due": len(ag["due"]), "warranty_soon": len(ag["warranty"]),
            "low_stock": S.low_count() if sc is None else 0,
            "counts_open": c.execute("SELECT COUNT(*) FROM counts WHERE status='açık'").fetchone()[0],
            "assigned": c.execute("SELECT COUNT(*) FROM assignments WHERE ended_at IS NULL").fetchone()[0]}


@router.get("/api/summary")
def summary(u=Depends(need("asset.read"))):
    return summary_data(u)


@router.get("/api/badges")
def badges(u=Depends(need("asset.read"))):
    sc = auth.scope(u)
    tc = T.counts(sc)
    return {"tickets_new": tc["yeni"], "tickets_open": tc["open"], "maint_overdue": M.agenda(locations=sc)["overdue"],
            "low_stock": S.low_count() if auth.can(u, "stock.read") else 0}


# ---------------- arıza ----------------
@router.get("/api/tickets")
def tickets_list(status: str = "open", q: str = "", asset_id: int = 0, assigned: str = "", page: int = 1,
                 u=Depends(need("ticket.read"))):
    return T.query(status or None, q, asset_id or None, assigned or None, page, 50, auth.scope(u))


@router.post("/api/tickets")
async def ticket_create(req: Request, u=Depends(need("ticket.create"))):
    b = await body(req)
    aid = int(b.get("asset_id") or 0) or None
    if aid:
        scoped_asset(u, aid)
    t = T.create(b.get("description"), aid, b.get("category"), b.get("reporter_name") or u["full_name"] or u["username"],
                 b.get("reporter_contact"), b.get("reporter_unit"), ip(req), "panel", u["username"], b.get("priority", "normal"))
    db.audit(u["username"], "ticket_create", t["id"], ip=ip(req))
    return t


def _ticket(u, tid):
    t = T.get(tid)
    if not t:
        raise ApiError(404, "NOT_FOUND", "Arıza kaydı bulunamadı")
    sc = auth.scope(u)
    if sc is not None:
        loc = (t["asset"] or {}).get("data", {}).get("location_name") or t.get("reporter_unit")
        if not auth.in_scope(u, loc):
            raise ApiError(404, "NOT_FOUND", "Arıza kaydı bulunamadı")
    return t


@router.get("/api/tickets/{tid}")
def ticket_get(tid: int, u=Depends(need("ticket.read"))):
    return _ticket(u, tid)


@router.patch("/api/tickets/{tid}")
async def ticket_patch(tid: int, req: Request, u=Depends(need("ticket.manage"))):
    _ticket(u, tid)
    b = await body(req)
    t = T.update(tid, b, u["username"])
    db.audit(u["username"], "ticket_update", tid, {k: b[k] for k in b if k in ("status", "assigned_to", "priority")}, ip(req))
    return t


@router.post("/api/tickets/{tid}/notes")
async def ticket_note(tid: int, req: Request, u=Depends(need("ticket.read"))):
    _ticket(u, tid)
    T.add_note(tid, u["username"], (await body(req)).get("note"))
    return T.get(tid)


@router.post("/api/public/tickets")
async def public_ticket(req: Request):
    b = await body(req)
    a = A.get(public_id=str(b.get("public_id") or ""))
    if not a or a["archived"]:
        raise ApiError(404, "NOT_FOUND", "Cihaz bulunamadı")
    try:
        t = T.create(b.get("description"), a["id"], b.get("category"), b.get("reporter_name"), b.get("reporter_contact"),
                     b.get("reporter_unit") or a["data"].get("location_name"), ip(req), "qr")
    except PermissionError as e:
        raise ApiError(429, "RATE_LIMIT", str(e))
    db.audit(b.get("reporter_name"), "ticket_public", t["id"], ip=ip(req))
    return {"id": t["id"], "code": t["public_code"], "track_url": f"/t/{t['public_code']}"}


# ---------------- sayım ----------------
def _count(u, cid, perm_location=True):
    cnt = C.get_raw(cid)
    if not cnt:
        raise ApiError(404, "NOT_FOUND", "Sayım bulunamadı")
    if auth.scope(u) is not None and not (cnt["location"] and auth.in_scope(u, cnt["location"])):
        raise ApiError(404, "NOT_FOUND", "Sayım bulunamadı")
    return cnt


@router.get("/api/counts")
def counts_list(u=Depends(need("count"))):
    return C.list_counts(auth.scope(u))


@router.post("/api/counts")
async def counts_create(req: Request, u=Depends(need("count"))):
    b = await body(req)
    if not auth.can(u, "count.manage"):  # birim temsilcisi yalnızca kendi birimi için sayım açabilir
        if not b.get("location") or not auth.in_scope(u, b["location"]):
            raise ApiError(403, "FORBIDDEN", "Yalnızca kendi biriminiz için sayım başlatabilirsiniz")
    return C.create(b.get("name"), b.get("location"), u["username"])


@router.get("/api/counts/{cid}")
def counts_get(cid: int, u=Depends(need("count"))):
    _count(u, cid)
    return C.detail(cid)


@router.post("/api/counts/{cid}/scan")
async def counts_scan(cid: int, req: Request, u=Depends(need("count"))):
    _count(u, cid)
    b = await body(req)
    return C.scan(cid, str(b.get("code") or ""), u["username"])


@router.post("/api/counts/{cid}/scan-batch")
async def counts_scan_batch(cid: int, req: Request, u=Depends(need("count"))):
    """Çevrimdışı biriken okutmaların toplu gönderimi."""
    _count(u, cid)
    items = (await body(req)).get("items") or []
    out = []
    for it in items[:2000]:
        at = str(it.get("at") or "")[:19] or None
        if at and not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?", at):
            at = None
        try:
            out.append(C.scan(cid, str(it.get("code") or ""), u["username"], at))
        except ValueError as e:
            out.append({"result": "error", "message": str(e)})
    return {"results": out}


@router.post("/api/counts/{cid}/close")
async def counts_close(cid: int, req: Request, u=Depends(need("count"))):
    cnt = _count(u, cid)
    b = await body(req)
    if not auth.can(u, "count.manage") and b.get("move_foreign"):
        raise ApiError(403, "FORBIDDEN", "Yer güncelleme yetkiniz yok")
    if not auth.can(u, "count.manage") and cnt["created_by"] != u["username"]:
        raise ApiError(403, "FORBIDDEN", "Bu sayımı yalnızca başlatan veya BİM kapatabilir")
    return C.close(cid, u["username"], bool(b.get("move_foreign")))


@router.get("/api/counts/{cid}/report.xlsx")
def counts_report(cid: int, u=Depends(need("count"))):
    _count(u, cid)
    d = C.detail(cid)
    h = ["Barkod", "Donanım", "Marka Model", "Kayıtlı Birim", "Durum"]
    row = lambda x: [x["asset_code"], x["hardware_info"], x["brand_model"], x["location"], x["status"]]  # noqa: E731
    return _xlsx(exporter.book_multi({
        "Özet": (["Sayım", "Birim", "Durum", "Beklenen", "Sayılan", "Bulunamayan", "Başka birimden", "Tanınmayan", "İlerleme %"],
                 [[d["name"], d["location"] or "Tümü", d["status"], d["expected"], d["seen"], d["missing"], d["foreign"], d["unknown"],
                   d["progress"]]]),
        "Bulunamayan": (h, [row(x) for x in d["missing_items"]]),
        "Başka birimden": (h + ["Görülme", "Sayan"], [row(x) + [x["seen_at"], x["seen_by"]] for x in d["foreign_items"]]),
        "Sayılan": (h + ["Görülme", "Sayan"], [row(x) + [x["seen_at"], x["seen_by"]] for x in d["seen_items"]]),
        "Tanınmayan": (["Kod", "Zaman", "Sayan"], [[x["code"], x["seen_at"], x["seen_by"]] for x in d["unknown_items"]]),
    }), f"sayim-{cid}.xlsx")


# ---------------- zimmet ----------------
@router.get("/api/assignments")
def assign_list(q: str = "", active: int = 1, page: int = 1, u=Depends(need("asset.read"))):
    return Z.query(q, bool(active), page, 100, auth.scope(u))


@router.post("/api/assignments")
async def assign_create(req: Request, u=Depends(need("assign"))):
    b = await body(req)
    return Z.assign(_scoped_ids(u, _ids(b.get("asset_ids"))), b.get("kind", "kişi"), b.get("holder_name"), u["username"],
                    b.get("holder_title"), b.get("holder_unit"), b.get("note"), b.get("signature"), b.get("giver_signature"))


@router.post("/api/assignments/return")
async def assign_return(req: Request, u=Depends(need("assign"))):
    b = await body(req)
    return Z.release(_scoped_ids(u, _ids(b.get("asset_ids"))), u["username"], b.get("return_signature"), b.get("note"))


# ---------------- bakım ----------------
@router.get("/api/maintenance")
def maint_agenda(days: int = -1, u=Depends(need("asset.read"))):
    return M.agenda(None if days < 0 else days, auth.scope(u))


@router.post("/api/maintenance")
async def maint_create(req: Request, u=Depends(need("maint"))):
    b = await body(req)
    n = M.create(_scoped_ids(u, _ids(b.get("asset_ids"))), b.get("title"), b.get("interval_days"), b.get("first_due"),
                 u["username"], b.get("note"))
    return {"created": n}


@router.post("/api/maintenance/{pid}/done")
async def maint_done(pid: int, req: Request, u=Depends(need("maint"))):
    b = await body(req)
    try:
        return M.done(pid, u["username"], b.get("note"), b.get("date"))
    except KeyError:
        raise ApiError(404, "NOT_FOUND", "Plan bulunamadı")


@router.patch("/api/maintenance/{pid}")
async def maint_patch(pid: int, req: Request, u=Depends(need("maint"))):
    M.update(pid, await body(req))
    return {"ok": True}


# ---------------- sarf ----------------
@router.get("/api/stock")
def stock_list(q: str = "", low: int = 0, u=Depends(need("stock.read"))):
    return S.query(q, bool(low))


@router.get("/api/stock/{cid}")
def stock_get(cid: int, u=Depends(need("stock.read"))):
    x = S.get(cid)
    if not x:
        raise ApiError(404, "NOT_FOUND", "Malzeme bulunamadı")
    return x


@router.post("/api/stock")
async def stock_create(req: Request, u=Depends(need("stock"))):
    b = await body(req)
    x = S.save(b)
    if float(b.get("stock") or 0) > 0:
        x = S.move(x["id"], float(b["stock"]), u["username"], note="Açılış stoku")
    return x


@router.patch("/api/stock/{cid}")
async def stock_patch(cid: int, req: Request, u=Depends(need("stock"))):
    return S.save(await body(req), cid)


@router.post("/api/stock/{cid}/move")
async def stock_move(cid: int, req: Request, u=Depends(need("stock"))):
    b = await body(req)
    aid = int(b.get("asset_id") or 0) or None
    if b.get("asset_code") and not aid:
        a = A.get_by_code(b["asset_code"])
        if not a:
            raise ApiError(404, "NOT_FOUND", "Bu barkodla cihaz yok")
        aid = a["id"]
    try:
        return S.move(cid, b.get("qty"), u["username"], aid, b.get("note"))
    except KeyError:
        raise ApiError(404, "NOT_FOUND", "Malzeme bulunamadı")


# ---------------- bilgi bankası ----------------
@router.get("/api/kb")
def kb_list(q: str = "", u=Depends(need("kb.read"))):
    return kb.query(q)


@router.get("/api/kb/{kid}")
def kb_get(kid: int, u=Depends(need("kb.read"))):
    e = kb.get(kid, count_view=True)
    if not e:
        raise ApiError(404, "NOT_FOUND", "Kayıt bulunamadı")
    return e


@router.post("/api/kb")
async def kb_create(req: Request, u=Depends(need("kb.write"))):
    b = await body(req)
    return kb.create(b.get("title"), b.get("body"), b.get("match"), b.get("tags"), u["username"])


@router.patch("/api/kb/{kid}")
async def kb_patch(kid: int, req: Request, u=Depends(need("kb.write"))):
    try:
        return kb.update(kid, await body(req), u["username"])
    except KeyError:
        raise ApiError(404, "NOT_FOUND", "Kayıt bulunamadı")


@router.delete("/api/kb/{kid}")
def kb_delete(kid: int, u=Depends(need("kb.write"))):
    kb.delete(kid)
    return {"ok": True}


# ---------------- ağ ----------------
@router.get("/api/network")
def net_overview(u=Depends(need("network"))):
    return N.overview()


@router.post("/api/network/scan")
def net_scan(u=Depends(need("network"))):
    try:
        N.scan_async(u["username"])
    except RuntimeError as e:
        raise ApiError(409, "BUSY", str(e))
    return {"started": True}


@router.put("/api/network/config")
async def net_config(req: Request, u=Depends(need("network"))):
    b = await body(req)
    subnets = [s.strip() for s in b.get("subnets") or [] if s.strip()]
    N.hosts_of(subnets)  # doğrula
    cfg = {"subnets": subnets, "interval_hours": max(0.0, float(b.get("interval_hours") or 0)),
           "stale_days": max(1, int(b.get("stale_days") or 30))}
    db.set_setting("net_scan", cfg)
    return cfg


@router.post("/api/network/switches")
async def net_sw_add(req: Request, u=Depends(need("network"))):
    N.save_switch(await body(req))
    return N.overview()["switches"]


@router.patch("/api/network/switches/{sid}")
async def net_sw_patch(sid: int, req: Request, u=Depends(need("network"))):
    N.save_switch(await body(req), sid)
    return {"ok": True}


@router.delete("/api/network/switches/{sid}")
def net_sw_del(sid: int, u=Depends(need("network"))):
    N.delete_switch(sid)
    return {"ok": True}


# ---------------- ajan ----------------
@router.get("/agent.ps1", response_class=PlainTextResponse)
def agent_script(t: str = ""):
    if not agent.check_token(t):
        raise ApiError(403, "FORBIDDEN", "Geçersiz ajan anahtarı")
    return PlainTextResponse(agent.script(base_url()), media_type="text/plain; charset=utf-8")


@router.post("/api/agent/report")
async def agent_report(req: Request):
    if not agent.check_token(req.headers.get("x-agent-token")):
        raise ApiError(403, "FORBIDDEN", "Geçersiz ajan anahtarı")
    return agent.report(await body(req), ip(req))


@router.get("/api/agent/reports")
def agent_reports(unmatched: int = 0, u=Depends(need("network"))):
    return agent.reports(bool(unmatched))


@router.post("/api/agent/link")
async def agent_link(req: Request, u=Depends(need("network"))):
    b = await body(req)
    try:
        return agent.link(b.get("hostname"), int(b.get("asset_id") or 0) or None, b.get("new_code"), u["username"])
    except KeyError:
        raise ApiError(404, "NOT_FOUND", "Ajan kaydı bulunamadı")


@router.post("/api/agent/token/rotate")
def agent_rotate(req: Request, u=Depends(need("settings"))):
    import secrets
    db.set_setting("agent_token", secrets.token_urlsafe(24))
    db.audit(u["username"], "agent_token_rotate", ip=ip(req))
    return {"agent_token": db.get_setting("agent_token")}


# ---------------- raporlar ----------------
@router.get("/api/reports/renewal")
def rep_renewal(u=Depends(need("reports"))):
    return R.renewal(auth.scope(u))


@router.get("/api/reports/renewal.xlsx")
def rep_renewal_x(u=Depends(need("reports"))):
    return _xlsx(R.renewal_xlsx(auth.scope(u)), f"yenileme-raporu-{date.today()}.xlsx")


@router.get("/api/reports/tasinir.xlsx")
def rep_tasinir(u=Depends(need("reports"))):
    return _xlsx(R.tasinir_xlsx(), f"tasinir-listesi-{date.today()}.xlsx")


@router.get("/api/reports/audit-pack.zip")
def rep_pack(req: Request, start: str = "", end: str = "", u=Depends(need("reports"))):
    end = end or date.today().isoformat()
    start = start or (date.today() - timedelta(days=365)).isoformat()
    try:
        date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise ApiError(400, "BAD_REQUEST", "Tarih biçimi YYYY-AA-GG olmalı")
    return Response(R.audit_pack(start, end, u["username"]), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="denetim-paketi-{start}_{end}.zip"'})


@router.get("/api/disposals")
def disp_list(u=Depends(need("reports"))):
    return R.disposals()


@router.post("/api/disposals")
async def disp_create(req: Request, u=Depends(need("asset.archive"))):
    b = await body(req)
    return R.dispose(_ids(b.get("asset_ids")), b.get("reason"), b.get("commission"), u["username"])


# ---------------- kurumlar ----------------
@router.get("/api/federation")
def fed_list(u=Depends(need("federation"))):
    return federation.remotes()


@router.post("/api/federation")
async def fed_add(req: Request, u=Depends(need("federation"))):
    federation.save(await body(req))
    return federation.remotes()


@router.patch("/api/federation/{rid}")
async def fed_patch(rid: int, req: Request, u=Depends(need("federation"))):
    federation.save(await body(req), rid)
    return {"ok": True}


@router.delete("/api/federation/{rid}")
def fed_del(rid: int, u=Depends(need("federation"))):
    federation.delete(rid)
    return {"ok": True}


@router.get("/api/federation/poll")
def fed_poll(u=Depends(need("federation"))):
    return federation.poll(summary_data(u))


# ---------------- API anahtarları ----------------
@router.get("/api/tokens")
def tokens(u=Depends(need("tokens"))):
    return auth.list_tokens()


@router.post("/api/tokens")
async def token_create(req: Request, u=Depends(need("tokens"))):
    b = await body(req)
    t = auth.create_token(b.get("name"), b.get("role", "auditor"), u["username"])
    db.audit(u["username"], "token_create", t["name"], {"role": t["role"]}, ip(req))
    return t


@router.delete("/api/tokens/{tid}")
def token_revoke(tid: int, req: Request, u=Depends(need("tokens"))):
    auth.revoke_token(tid)
    db.audit(u["username"], "token_revoke", tid, ip=ip(req))
    return {"ok": True}


# ---------------- AD / lisans / TLS ----------------
@router.post("/api/ldap/test")
async def ldap_test(req: Request, u=Depends(need("settings"))):
    b = await body(req)
    info = auth.ldap_authenticate(b.get("username") or "", b.get("password") or "")
    if not info:
        return {"ok": False, "message": "Bağlanılamadı ya da kullanıcı adı/parola hatalı"}
    role, units = auth.ldap_role(info["groups"])
    return {"ok": True, "info": info, "role": role, "role_name": auth.ROLES.get(role), "units": units}


@router.post("/api/license")
async def license_install(req: Request, u=Depends(need("settings"))):
    try:
        lic = license.install((await body(req)).get("text") or "")
    except ValueError as e:
        raise ApiError(400, "LICENSE", str(e))
    db.audit(u["username"], "license_install", lic.get("licensee"), ip=ip(req))
    return license.status()


@router.post("/api/tls/selfsigned")
async def tls_selfsigned(req: Request, u=Depends(need("settings"))):
    from . import tls
    b = await body(req)
    info = tls.make_selfsigned(b.get("hostnames") or [])
    db.set_setting("tls", {"enabled": True})
    db.audit(u["username"], "tls_selfsigned", None, info, ip(req))
    return {**info, "message": "Sertifika oluşturuldu. Programı yeniden başlatınca HTTPS etkin olur."}


@router.put("/api/tls")
async def tls_toggle(req: Request, u=Depends(need("settings"))):
    from . import tls
    b = await body(req)
    if b.get("enabled") and not tls.available():
        raise ApiError(400, "NO_CERT", "Önce sertifika oluşturun veya data\\tls klasörüne cert.pem/key.pem koyun")
    db.set_setting("tls", {"enabled": bool(b.get("enabled"))})
    return {"enabled": bool(b.get("enabled")), "message": "Değişiklik program yeniden başlatılınca geçerli olur."}


@router.get("/api/tls")
def tls_info(u=Depends(need("settings"))):
    from . import tls
    return {"enabled": bool((db.get_setting("tls") or {}).get("enabled")), "available": tls.available(), **tls.info()}


# ---------------- QR sayfası (telefon) ----------------
_PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<link rel="stylesheet" href="/static/preview.css"></head><body><main class="card">
<header><div class="org">{org}</div><div class="unit">{unit}</div></header>
{body}</main><footer>NexEnvanter</footer>{script}</body></html>"""


def _page(title, body_html, script="", status=200):
    s = db.all_settings()
    return HTMLResponse(_PAGE.format(title=esc(title), org=esc(s["org_name"]), unit=esc(s["unit_name"]), body=body_html,
                                     script=script), status)


_QR_JS = """<script>
const H={'Content-Type':'application/json','x-nx':'1'};
async function post(u,b){const r=await fetch(u,{method:'POST',headers:H,body:JSON.stringify(b)});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error((j.error||{}).message||r.statusText);return j;}
const f=document.getElementById('tf');
if(f){document.getElementById('topen').onclick=()=>{f.hidden=!f.hidden;};
f.onsubmit=async e=>{e.preventDefault();const b=Object.fromEntries(new FormData(f));const m=document.getElementById('tmsg');
try{const r=await post('/api/public/tickets',b);f.hidden=true;document.getElementById('topen').hidden=true;
m.className='state ok';m.innerHTML='Bildiriminiz alındı. Takip no: <b>'+r.code+'</b><br><a href="'+r.track_url+'">Durumu izle →</a>';}
catch(err){m.className='state bad';m.textContent=err.message;}};}
document.querySelectorAll('[data-count]').forEach(b=>b.onclick=async()=>{const m=document.getElementById('cmsg');
try{const r=await post('/api/counts/'+b.dataset.count+'/scan',{code:location.href});m.className='state '+(r.result==='ok'?'ok':'warn');m.textContent=b.dataset.name+': '+r.message;}
catch(err){m.className='state bad';m.textContent=err.message;}});
</script>"""


@router.get("/e/{public_id}", response_class=HTMLResponse)
def qr_page(public_id: str, req: Request):
    a = A.get(public_id=public_id) if re.fullmatch(r"[A-Za-z0-9_-]{4,40}", public_id) else None
    if not a:
        return _page("Bulunamadı", '<div class="state bad">Kayıt bulunamadı</div>'
                                    '<p class="muted">Etiket geçersiz ya da kayıt silinmiş olabilir.</p>', status=404)
    u = current_user(req)
    rows = []
    for f in F.all_fields():
        if not (f["public"] or (u and f["show_preview"])):
            continue
        v = a.get(f["key"]) if f["system"] else a["data"].get(f["key"])
        if v:
            rows.append(f"<dt>{esc(f['label'])}</dt><dd>{esc(str(v))}</dd>")
    zim = Z.active(a["id"])
    if zim and u:
        rows.append(f"<dt>Zimmet</dt><dd>{esc(zim['holder_name'])}</dd>")
    state = '<div class="state warn">Arşivde</div>' if a["archived"] else '<div class="state ok">Cihaz bilgisi bulundu</div>'
    open_t = T.query("open", asset_id=a["id"], size=5)["items"]
    tinfo = f'<p class="muted">Bu cihaz için açık {len(open_t)} arıza kaydı var.</p>' if open_t else ""
    if u and auth.can(u, "asset.read") and auth.in_scope(u, a["data"].get("location_name")):
        detail = f'<a class="btn" href="/#/asset/{a["id"]}">Detayları Gör →</a>'
    else:
        detail = f'<a class="btn sec" href="/#/login?next=/asset/{a["id"]}">Personel girişi →</a>'
    count_btns = ""
    if u and auth.can(u, "count"):
        for cnt in C.list_counts(auth.scope(u)):
            if cnt["status"] == "açık":
                count_btns += (f'<button class="btn ok" data-count="{cnt["id"]}" data-name="{esc(cnt["name"])}">✓ Sayıma ekle: '
                               f'{esc(cnt["name"])}</button>')
        if count_btns:
            count_btns = f'<div id="cmsg"></div>{count_btns}'
    form = ""
    if db.get_setting("public_tickets", True) and not a["archived"]:
        cats = "".join(f"<option>{esc(c)}</option>" for c in db.get_setting("ticket_categories") or [])
        form = f"""<button class="btn warn" id="topen" type="button">⚠ Arıza bildir</button><div id="tmsg"></div>
<form id="tf" class="tform" hidden><input type="hidden" name="public_id" value="{esc(a['public_id'])}">
<label>Sorun türü<select name="category">{cats}</select></label>
<label>Sorunu kısaca yazın<textarea name="description" rows="3" required minlength="5"></textarea></label>
<label>Adınız soyadınız<input name="reporter_name" required value="{esc((u or {}).get('full_name') or '')}"></label>
<label>Dahili / telefon<input name="reporter_contact" inputmode="tel"></label>
<button class="btn">Gönder</button></form>"""
    b = f'{state}<div class="code">{esc(a["asset_code"])}</div><dl>{"".join(rows)}</dl>{tinfo}{count_btns}{form}{detail}'
    return _page(a["asset_code"], b, _QR_JS)


@router.get("/t/{code}", response_class=HTMLResponse)
def track_page(code: str):
    t = T.by_code(code) if re.fullmatch(r"[A-Fa-f0-9]{8}", code) else None
    if not t:
        return _page("Bulunamadı", '<div class="state bad">Takip numarası bulunamadı</div>', status=404)
    cls = "ok" if t["status"] in ("çözüldü", "kapalı") else "warn"
    asset = f"<dt>Cihaz</dt><dd>{esc(t['asset']['asset_code'])}</dd>" if t["asset"] else ""
    res = f"<dt>Çözüm</dt><dd>{esc(t['resolution'])}</dd>" if t.get("resolution") and cls == "ok" else ""
    b = (f'<div class="state {cls}">Durum: {esc(t["status"])}</div><div class="code">#{t["id"]}</div><dl>{asset}'
         f'<dt>Bildirim</dt><dd>{esc(t["created_at"].replace("T", " ")[:16])}</dd><dt>Konu</dt><dd>{esc(t["category"] or "")}</dd>'
         f'<dt>Açıklama</dt><dd>{esc(t["description"])}</dd>{res}</dl>')
    return _page(f"Arıza #{t['id']}", b)


# ---------------- yazdırılabilir tutanaklar ----------------
_DOC = """<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>{title}</title><style>
@page{{size:A4;margin:16mm}}body{{font:12px/1.45 "Segoe UI",Arial,sans-serif;color:#000;max-width:190mm;margin:0 auto}}
h1{{font-size:16px;text-align:center;margin:4px 0 2px}}.hd{{text-align:center;font-weight:700}}.sub{{text-align:center;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;margin:10px 0}}td,th{{border:1px solid #000;padding:4px 6px;text-align:left;vertical-align:top}}
th{{background:#eee}}.meta td{{border:none;padding:2px 4px}}.sig{{display:flex;gap:16px;margin-top:28px}}.sig>div{{flex:1;text-align:center;display:flex;flex-direction:column;justify-content:flex-end}}
.sig img{{max-height:60px;max-width:100%}}.line{{border-top:1px solid #000;margin-top:48px;padding-top:4px}}
.noprint{{margin:12px 0}}@media print{{.noprint{{display:none}}}}</style></head><body>
<div class="noprint"><button onclick="print()">Yazdır / PDF</button></div>
<div class="hd">{org}</div><div class="sub">{unit}</div><h1>{title}</h1>{body}</body></html>"""


def _doc(title, body_html):
    s = db.all_settings()
    return HTMLResponse(_DOC.format(title=esc(title), org=esc(s["org_name"]), unit=esc(s["unit_name"]), body=body_html))


def _sig(label, name, img):
    im = f'<img src="{esc(img)}">' if img else ""
    return f'<div>{im}<div class="line">{esc(name or "")}<br><small>{esc(label)}</small></div></div>'


def _asset_rows(items, extra=lambda x: []):
    flds = [("asset_code", "Barkod"), ("hardware_info", "Donanım"), ("brand_model", "Marka Model"), ("serial_number", "Seri No"),
            ("sicil_no", "Sicil No")]
    head = "".join(f"<th>{h}</th>" for _, h in flds) + "".join(f"<th>{h}</th>" for h in extra(None) or [])
    rows = ""
    for i, a in enumerate(items, 1):
        cells = "".join(f"<td>{esc(str((a.get(k) if k == 'asset_code' else a['data'].get(k)) or ''))}</td>" for k, _ in flds)
        rows += f"<tr><td>{i}</td>{cells}{''.join(f'<td>{esc(str(v))}</td>' for v in extra(a) or [])}</tr>"
    return f"<table><tr><th>#</th>{head}</tr>{rows}</table>"


@router.get("/print/zimmet/{doc_no}", response_class=HTMLResponse)
def print_assign(doc_no: str, u=Depends(need("asset.read"))):
    d = Z.document(doc_no)
    if not d:
        raise ApiError(404, "NOT_FOUND", "Belge bulunamadı")
    first = d["items"][0]
    if d["kind"] == "iade":
        title = "DEMİRBAŞ İADE TUTANAĞI"
        meta = (f"<table class='meta'><tr><td>Belge No: <b>{esc(doc_no)}</b></td><td>Tarih: {esc(first['ended_at'][:16].replace('T', ' '))}</td></tr>"
                f"<tr><td colspan=2>İade eden: <b>{esc(first['holder_name'])}</b> {esc(first['holder_title'] or '')} "
                f"{esc(first['holder_unit'] or '')}</td></tr></table>")
        text = "<p>Aşağıda dökümü yapılan demirbaş(lar) eksiksiz ve çalışır durumda teslim alınmıştır.</p>"
        sigs = _sig("İade Eden", first["holder_name"], first.get("return_signature")) + _sig("Teslim Alan", first.get("ended_by"), None)
    else:
        title = "DEMİRBAŞ ZİMMET VE DEVİR-TESLİM TUTANAĞI" if d["kind"] == "devir" else "DEMİRBAŞ ZİMMET TUTANAĞI"
        meta = (f"<table class='meta'><tr><td>Belge No: <b>{esc(doc_no)}</b></td><td>Tarih: {esc(first['started_at'][:16].replace('T', ' '))}</td></tr>"
                f"<tr><td colspan=2>Zimmet alan ({esc(first['kind'])}): <b>{esc(first['holder_name'])}</b> {esc(first['holder_title'] or '')} "
                f"{('— ' + esc(first['holder_unit'])) if first['holder_unit'] else ''}</td></tr></table>")
        prev = ""
        if d["previous"]:
            names = sorted({p["holder_name"] for p in d["previous"]})
            prev = f"<p>Devreden: <b>{esc(', '.join(names))}</b></p>"
        text = (f"{prev}<p>Aşağıda dökümü yapılan demirbaş(lar) sağlam ve çalışır durumda teslim alınmış olup, kullanımından, "
                f"korunmasından ve kurum içi kurallara uygun kullanılmasından zimmet alan sorumludur.</p>")
        sigs = (_sig("Teslim Eden", first.get("created_by"), first.get("giver_signature"))
                + _sig("Teslim Alan", first["holder_name"], first.get("signature")))
    note = f"<p>Not: {esc(first['note'])}</p>" if first.get("note") else ""
    return _doc(title, meta + text + _asset_rows([x["asset"] for x in d["items"] if x["asset"]]) + note + f'<div class="sig">{sigs}</div>')


@router.get("/print/hurda/{doc_no}", response_class=HTMLResponse)
def print_disposal(doc_no: str, u=Depends(need("reports"))):
    d = R.disposal(doc_no)
    if not d:
        raise ApiError(404, "NOT_FOUND", "Belge bulunamadı")
    meta = (f"<table class='meta'><tr><td>Belge No: <b>{esc(doc_no)}</b></td><td>Tarih: {esc(d['at'][:10])}</td></tr></table>"
            f"<p>Aşağıda dökümü yapılan taşınırlar komisyonumuzca incelenmiş; <b>{esc(d['reason'])}</b> gerekçesiyle "
            f"kullanılamaz durumda olduğu tespit edilerek hurdaya ayrılması uygun görülmüştür.</p>")
    rows = _asset_rows([a for a in d["assets"] if a], lambda a: ["Edinme Tarihi"] if a is None else [a["data"].get("purchase_date") or ""])
    sigs = "".join(_sig(m.get("title") or "Üye", m.get("name"), None) for m in d["commission"]) or _sig("Komisyon", "", None)
    return _doc("TAŞINIR HURDAYA AYIRMA (TERKİN) TUTANAĞI", meta + rows + f'<div class="sig">{sigs}</div>')


@router.get("/print/sayim/{cid}", response_class=HTMLResponse)
def print_count(cid: int, u=Depends(need("count"))):
    _count(u, cid)
    d = C.detail(cid)
    meta = (f"<table class='meta'><tr><td>Sayım: <b>{esc(d['name'])}</b></td><td>Birim: {esc(d['location'] or 'Tümü')}</td></tr>"
            f"<tr><td>Başlangıç: {esc(d['created_at'][:16].replace('T', ' '))} ({esc(d['created_by'] or '')})</td>"
            f"<td>Durum: {esc(d['status'])}</td></tr></table>"
            f"<p>Beklenen: <b>{d['expected']}</b> · Sayılan: <b>{d['seen']}</b> · Bulunamayan: <b>{d['missing']}</b> · "
            f"Başka birimden: <b>{d['foreign']}</b> · Tanınmayan kod: <b>{d['unknown']}</b></p>")

    def tbl(title, items):
        if not items:
            return ""
        r = "".join(f"<tr><td>{esc(x['asset_code'])}</td><td>{esc(x['hardware_info'] or '')}</td><td>{esc(x['brand_model'] or '')}</td>"
                    f"<td>{esc(x['location'] or '')}</td></tr>" for x in items)
        return f"<h3>{title}</h3><table><tr><th>Barkod</th><th>Donanım</th><th>Marka Model</th><th>Kayıtlı Birim</th></tr>{r}</table>"
    sigs = _sig("Sayımı Yapan", d["created_by"], None) + _sig("Birim Sorumlusu", "", None) + _sig("BİM", "", None)
    return _doc("ENVANTER SAYIM TUTANAĞI", meta + tbl("Bulunamayanlar", d["missing_items"])
                + tbl("Başka birimde kayıtlı olup burada bulunanlar", d["foreign_items"]) + f'<div class="sig">{sigs}</div>')


# ---------------- yardımcı: arayüz listeleri ----------------
@router.get("/api/meta")
def meta(u=Depends(need("asset.read"))):
    return {"ticket_statuses": T.STATUSES, "ticket_priorities": T.PRIORITIES, "ticket_categories": db.get_setting("ticket_categories"),
            "staff": [x["username"] for x in auth.list_users() if x["active"] and x["role"] in ("admin", "manager", "operator")]
            if auth.can(u, "ticket.manage") else [], "data_dir": str(DIRS.data) if auth.can(u, "settings") else None}
