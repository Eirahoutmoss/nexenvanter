"""HTTP katmanı: REST API, QR önizleme sayfası ve statik web arayüzü."""
import html
import json
import socket

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import APP_NAME, AUTHOR, VERSION, assets as A, auth, db, exporter, fields as F, importer, labels, license, printing, updater
from .paths import DIRS, WEB_DIR

COOKIE = "nx_session"
app = FastAPI(title=APP_NAME, version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
app.state.port = 8750
app.state.shutdown = lambda: None


class ApiError(Exception):
    def __init__(self, status, code, msg, extra=None):
        self.status, self.code, self.msg, self.extra = status, code, msg, extra or {}


def _err(status, code, msg, extra=None):
    return JSONResponse({"error": {"code": code, "message": msg, **(extra or {})}}, status_code=status)


@app.exception_handler(ApiError)
async def _api_err(_, e: ApiError):
    return _err(e.status, e.code, e.msg, e.extra)


@app.exception_handler(A.AssetError)
async def _asset_err(_, e: A.AssetError):
    return _err(e.status, e.code, e.msg, e.extra)


@app.exception_handler(ValueError)
async def _val_err(_, e: ValueError):
    return _err(400, "BAD_REQUEST", str(e))


@app.exception_handler(printing.PrinterError)
async def _prn_err(_, e):
    return _err(503, "PRINTER_ERROR", str(e))


@app.middleware("http")
async def _guard(request: Request, call_next):
    # CSRF: değiştiren API çağrıları özel başlık taşımalı (başka siteden form ile gönderilemez)
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-nx") != "1":
            return _err(403, "CSRF", "Geçersiz istek kaynağı")
    if license.LICENSE_REQUIRED and not license.is_valid() and request.url.path.startswith("/api/") \
            and request.url.path not in ("/api/state", "/api/license"):
        return _err(402, "LICENSE", "Geçerli lisans bulunamadı")
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


# ---------- yardımcılar ----------
def ip(req: Request):
    return req.client.host if req.client else "?"


def current_user(req: Request):
    return auth.session_user(req.cookies.get(COOKIE))


def need(perm: str):
    def dep(req: Request):
        u = current_user(req)
        if not u:
            raise ApiError(401, "UNAUTHORIZED", "Oturum açmanız gerekiyor")
        if not auth.can(u, perm):
            raise ApiError(403, "FORBIDDEN", "Bu işlem için yetkiniz yok")
        return u
    return dep


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def base_url() -> str:
    b = (db.get_setting("base_url") or "").strip().rstrip("/")
    return b or f"http://{lan_ip()}:{app.state.port}"


def qr_url(a: dict) -> str:
    return f"{base_url()}/e/{a['public_id']}"


async def body(req: Request) -> dict:
    try:
        return await req.json()
    except Exception:
        raise ApiError(400, "BAD_JSON", "Geçersiz JSON")


def _asset_or_404(aid: int) -> dict:
    a = A.get(aid)
    if not a:
        raise ApiError(404, "NOT_FOUND", "Kayıt bulunamadı")
    return a


# ---------- oturum / kurulum ----------
@app.get("/api/state")
def state(req: Request):
    u = current_user(req)
    s = db.all_settings()
    return {"app": {"name": APP_NAME, "version": VERSION, "author": AUTHOR}, "setup_needed": not auth.has_users(),
            "user": u, "perms": auth.perms_of(u["role"]) if u else [], "roles": auth.ROLES, "statuses": db.STATUSES,
            "org": {k: s.get(k) for k in ("org_name", "unit_name", "system_title")}, "license": license.status(),
            "base_url": base_url()}


@app.post("/api/setup")
async def setup(req: Request):
    if auth.has_users():
        raise ApiError(409, "ALREADY_SETUP", "Kurulum zaten tamamlanmış")
    b = await body(req)
    u = auth.create_user(b.get("username"), b.get("password"), "admin", b.get("full_name"))
    db.audit(u["username"], "setup", ip=ip(req))
    return _login(req, b)


@app.post("/api/login")
async def login(req: Request):
    return _login(req, await body(req))


def _login(req: Request, b: dict):
    try:
        token, u = auth.login(b.get("username"), b.get("password"), ip(req))
    except PermissionError as e:
        db.audit(b.get("username"), "login_failed", ip=ip(req))
        raise ApiError(401, "LOGIN_FAILED", str(e))
    db.audit(u["username"], "login", ip=ip(req))
    r = JSONResponse({"user": u, "perms": auth.perms_of(u["role"])})
    r.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=auth.SESSION_TTL,
                 secure=base_url().startswith("https"))
    return r


@app.post("/api/logout")
def logout(req: Request):
    auth.logout(req.cookies.get(COOKIE))
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


@app.post("/api/me/password")
async def my_password(req: Request, u=Depends(need("asset.read"))):
    b = await body(req)
    r = db.conn().execute("SELECT pw_hash FROM users WHERE id=?", (u["id"],)).fetchone()
    if not auth.check_pw(b.get("old_password") or "", r[0]):
        raise ApiError(400, "BAD_PASSWORD", "Mevcut parola hatalı")
    auth.update_user(u["id"], {"password": b.get("new_password")}, actor_id=u["id"])
    db.audit(u["username"], "password_change", ip=ip(req))
    return {"ok": True}


# ---------- alanlar ----------
@app.get("/api/fields")
def list_fields(all: int = 0, u=Depends(need("asset.read"))):
    return F.all_fields(active_only=not all)


@app.post("/api/fields")
async def add_field(req: Request, u=Depends(need("fields"))):
    b = await body(req)
    f = F.create(b.get("label") or "", b.get("type") or "text", aliases=b.get("aliases"),
                 **{k: b[k] for k in ("show_list", "show_preview", "public", "options") if k in b})
    db.audit(u["username"], "field_create", f["key"], f, ip(req))
    return f


@app.patch("/api/fields/{key}")
async def edit_field(key: str, req: Request, u=Depends(need("fields"))):
    b = await body(req)
    try:
        f = F.update(key, b)
    except KeyError:
        raise ApiError(404, "NOT_FOUND", "Alan bulunamadı")
    db.audit(u["username"], "field_update", key, b, ip(req))
    return f


# ---------- envanter ----------
@app.get("/api/assets")
def list_assets(req: Request, q: str = "", status: str = "", archived: str = "0", sort: str = "updated_at",
                dir: str = "desc", page: int = 1, size: int = 50, u=Depends(need("asset.read"))):
    filters = {k[2:]: v for k, v in req.query_params.items() if k.startswith("f.")}
    return A.query(q, status or None, archived, filters, sort, dir, page, size)


@app.post("/api/assets")
async def create_asset(req: Request, u=Depends(need("asset.write"))):
    a = A.create(await body(req), u["username"])
    db.audit(u["username"], "asset_create", a["id"], {"asset_code": a["asset_code"]}, ip(req))
    return a


@app.get("/api/assets/by-code/{code}")
def asset_by_code(code: str, u=Depends(need("asset.read"))):
    a = A.get_by_code(code)
    if not a:
        raise ApiError(404, "NOT_FOUND", "Bu barkodla kayıt yok")
    return a


@app.get("/api/assets/{aid}")
def get_asset(aid: int, u=Depends(need("asset.read"))):
    a = _asset_or_404(aid)
    return {**a, "events": A.events(aid), "qr_url": qr_url(a)}


@app.patch("/api/assets/{aid}")
async def patch_asset(aid: int, req: Request, u=Depends(need("asset.write"))):
    b = await body(req)
    a = A.update(aid, b, u["username"])
    db.audit(u["username"], "asset_update", aid, list(b.keys()), ip(req))
    return a


@app.post("/api/assets/{aid}/archive")
async def archive_asset(aid: int, req: Request, u=Depends(need("asset.archive"))):
    b = await body(req)
    a = A.set_archived(aid, bool(b.get("archived", True)), u["username"], b.get("note"))
    db.audit(u["username"], "asset_archive" if a["archived"] else "asset_restore", aid, ip=ip(req))
    return a


@app.post("/api/assets/{aid}/events")
async def add_event(aid: int, req: Request, u=Depends(need("asset.write"))):
    _asset_or_404(aid)
    b = await body(req)
    action = (b.get("action") or "not").strip()[:40]
    note = (b.get("note") or "").strip()[:2000]
    if not note:
        raise ApiError(400, "BAD_REQUEST", "Not boş olamaz")
    A.add_event(aid, u["username"], action, note)
    return A.events(aid)


@app.get("/api/values/{key}")
def values(key: str, u=Depends(need("asset.read"))):
    return A.distinct_values(key)


@app.get("/api/stats")
def stats(u=Depends(need("asset.read"))):
    return A.stats()


def _xlsx(data: bytes, name: str):
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/export.xlsx")
def export(req: Request, q: str = "", status: str = "", archived: str = "0", sort: str = "asset_code", dir: str = "asc",
           ids: str = "", u=Depends(need("export"))):
    filters = {k[2:]: v for k, v in req.query_params.items() if k.startswith("f.")}
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()] or None
    data = exporter.export_assets(q=q, status=status or None, archived=archived, filters=filters, sort=sort,
                                  direction=dir, ids=id_list)
    db.audit(u["username"], "export", None, {"q": q, "filters": filters}, ip(req))
    return _xlsx(data, f"envanter-{db.now()[:10]}.xlsx")


@app.get("/api/template.xlsx")
def template(u=Depends(need("asset.read"))):
    return _xlsx(exporter.template(), "envanter-sablon.xlsx")


# ---------- içe aktarma ----------
@app.post("/api/import/upload")
async def import_upload(file: UploadFile = File(...), u=Depends(need("import"))):
    raw = await file.read()
    token = importer.save_upload(raw, file.filename or "dosya.xlsx")
    return importer.analyze(token)


@app.post("/api/import/analyze")
async def import_analyze(req: Request, u=Depends(need("import"))):
    b = await body(req)
    return importer.analyze(b["token"], b.get("sheet"), b.get("header_row"))


@app.post("/api/import/run")
async def import_run(req: Request, u=Depends(need("import"))):
    b = await body(req)
    return importer.run(b["token"], b.get("sheet"), int(b.get("header_row") or 1), b.get("mapping") or {},
                        b.get("new_fields"), b.get("mode", "skip"), bool(b.get("blank_overwrites")),
                        bool(b.get("dry_run", True)), u["username"])


@app.get("/api/import/jobs")
def import_jobs(u=Depends(need("import"))):
    return importer.jobs()


@app.get("/api/import/jobs/{jid}/report.xlsx")
def import_report(jid: int, u=Depends(need("import"))):
    return _xlsx(exporter.report(importer.job_report(jid)), f"ice-aktarma-{jid}.xlsx")


# ---------- etiket ----------
@app.get("/api/labels/template")
def get_tpl(u=Depends(need("asset.read"))):
    return {"template": labels.get_template(), "default": labels.DEFAULT_TEMPLATE,
            "logos": {s: labels.logo_path(s).exists() for s in ("left", "right")}}


@app.put("/api/labels/template")
async def put_tpl(req: Request, u=Depends(need("labels"))):
    t = (await body(req)).get("template")
    if not isinstance(t, dict):
        raise ApiError(400, "BAD_REQUEST", "Şablon gerekli")
    for k in ("width_mm", "height_mm"):
        if not (5 <= float(t.get(k, 0)) <= 300):
            raise ApiError(400, "BAD_REQUEST", "Etiket ölçüsü 5–300 mm aralığında olmalı")
    db.set_setting("label_template", t)
    db.audit(u["username"], "label_template", None, None, ip(req))
    return labels.get_template()


@app.post("/api/labels/logo/{side}")
async def put_logo(side: str, file: UploadFile = File(...), u=Depends(need("labels"))):
    if side not in ("left", "right"):
        raise ApiError(400, "BAD_REQUEST", "Geçersiz konum")
    from PIL import Image
    import io
    try:
        img = Image.open(io.BytesIO(await file.read()))
        img.convert("RGBA").save(labels.logo_path(side))
    except Exception:
        raise ApiError(400, "BAD_IMAGE", "Görsel okunamadı")
    return {"ok": True}


@app.delete("/api/labels/logo/{side}")
def del_logo(side: str, u=Depends(need("labels"))):
    if side in ("left", "right"):
        labels.logo_path(side).unlink(missing_ok=True)
    return {"ok": True}


def _sample_asset():
    return {"asset_code": "1000001", "public_id": "ORNEK", "status": "aktif",
            "data": {"brand_model": "FUJİTSU ESPRIMO D556", "location_name": "BİLGİ İŞLEM", "serial_number": "123123123",
                     "hardware_info": "Bilgisayar"}}


@app.get("/api/labels/preview/{aid}.png")
def label_png(aid: int, u=Depends(need("asset.read"))):
    a = _sample_asset() if aid == 0 else _asset_or_404(aid)
    return Response(labels.png(labels.render(a, qr_url(a))), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/labels/preview")
async def label_png_draft(req: Request, u=Depends(need("asset.read"))):
    b = await body(req)
    aid = int(b.get("asset_id") or 0)
    a = _sample_asset() if not aid else _asset_or_404(aid)
    tpl = {**labels.DEFAULT_TEMPLATE, **(b.get("template") or {})}
    return Response(labels.png(labels.render(a, qr_url(a), tpl)), media_type="image/png")


def _ids(s) -> list[int]:
    ids = [int(x) for x in (s.split(",") if isinstance(s, str) else s or []) if str(x).strip().isdigit()]
    if not ids:
        raise ApiError(400, "BAD_REQUEST", "Kayıt seçilmedi")
    if len(ids) > 2000:
        raise ApiError(400, "BAD_REQUEST", "Tek seferde en fazla 2000 etiket")
    return ids


def _render_many(ids):
    tpl, s = labels.get_template(), db.all_settings()
    items = {a["id"]: a for a in A.query(ids=ids, archived="all", size=len(ids))["items"]}
    return [labels.render(items[i], qr_url(items[i]), tpl, s) for i in ids if i in items], tpl


@app.get("/api/labels/pdf")
def label_pdf(req: Request, ids: str, u=Depends(need("print"))):
    lst = _ids(ids)
    imgs, tpl = _render_many(lst)
    db.conn().execute("INSERT INTO print_jobs(at,user,printer,adapter,asset_ids,copies,status) VALUES(?,?,?,?,?,?,?)",
                      (db.now(), u["username"], "PDF", "pdf", json.dumps(lst), 1, "completed"))
    return Response(labels.pdf(imgs, int(tpl["dpi"])), media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="etiketler.pdf"'})


@app.get("/api/printers")
def printers(u=Depends(need("print"))):
    return {"adapters": [{"id": a.id, "name": a.name} for a in printing.available_adapters()],
            "printers": printing.all_printers(), "default": db.get_setting("default_printer") or ""}


@app.get("/api/printers/status")
def printer_status(name: str, adapter: str = "windows", u=Depends(need("print"))):
    a = printing.ADAPTERS.get(adapter)
    if not a or not a.available():
        raise ApiError(400, "NO_ADAPTER", "Yazıcı adaptörü kullanılamıyor")
    return a.status(name)


@app.post("/api/print")
async def do_print(req: Request, u=Depends(need("print"))):
    b = await body(req)
    lst = _ids(b.get("ids"))
    copies = max(1, min(int(b.get("copies") or 1), 20))
    a = printing.ADAPTERS.get(b.get("adapter") or "windows")
    if not a or not a.available():
        raise ApiError(400, "NO_ADAPTER", "Bu bilgisayarda doğrudan yazdırma kullanılamıyor; PDF çıktısını kullanın")
    printer = b.get("printer") or db.get_setting("default_printer")
    if not printer:
        raise ApiError(400, "NO_PRINTER", "Yazıcı seçilmedi")
    c = db.conn()
    jid = c.execute("INSERT INTO print_jobs(at,user,printer,adapter,asset_ids,copies,status) VALUES(?,?,?,?,?,?,?)",
                    (db.now(), u["username"], printer, a.id, json.dumps(lst), copies, "printing")).lastrowid
    imgs, tpl = _render_many(lst)
    try:
        a.print_images(printer, imgs, float(tpl["width_mm"]), float(tpl["height_mm"]), copies)
    except Exception as e:
        c.execute("UPDATE print_jobs SET status='failed', error=? WHERE id=?", (str(e), jid))
        raise ApiError(503, "PRINT_FAILED", str(e), {"job_id": jid})
    # Not: 'gönderildi' fiziksel baskı başarısının kesin kanıtı değildir.
    c.execute("UPDATE print_jobs SET status='sent' WHERE id=?", (jid,))
    for i in lst:
        A.add_event(i, u["username"], "label_print", f"{printer} ×{copies}")
    db.audit(u["username"], "print", jid, {"count": len(imgs), "printer": printer}, ip(req))
    return {"ok": True, "job_id": jid, "count": len(imgs)}


@app.get("/api/print/jobs")
def print_jobs(u=Depends(need("print"))):
    rows = db.conn().execute("SELECT * FROM print_jobs ORDER BY id DESC LIMIT 100")
    return [{**dict(r), "asset_ids": json.loads(r["asset_ids"] or "[]")} for r in rows]


# ---------- kullanıcılar / denetim / ayarlar ----------
@app.get("/api/users")
def users(u=Depends(need("users"))):
    return auth.list_users()


@app.post("/api/users")
async def add_user(req: Request, u=Depends(need("users"))):
    b = await body(req)
    nu = auth.create_user(b.get("username"), b.get("password"), b.get("role", "viewer"), b.get("full_name"))
    db.audit(u["username"], "user_create", nu["username"], {"role": nu["role"]}, ip(req))
    return nu


@app.patch("/api/users/{uid}")
async def edit_user(uid: int, req: Request, u=Depends(need("users"))):
    b = await body(req)
    nu = auth.update_user(uid, b, actor_id=u["id"])
    db.audit(u["username"], "user_update", nu["username"], [k for k in b if k != "password"] +
             (["password"] if b.get("password") else []), ip(req))
    return nu


@app.get("/api/audit")
def audit_log(page: int = 1, q: str = "", u=Depends(need("audit"))):
    w, args = "", []
    if q:
        w = " WHERE user LIKE ? OR action LIKE ? OR target LIKE ?"
        args = [f"%{q}%"] * 3
    c = db.conn()
    total = c.execute(f"SELECT COUNT(*) FROM audit{w}", args).fetchone()[0]
    rows = c.execute(f"SELECT * FROM audit{w} ORDER BY id DESC LIMIT 100 OFFSET ?", (*args, (max(1, page) - 1) * 100))
    return {"total": total, "items": [dict(r) for r in rows]}


SETTING_KEYS = ("org_name", "unit_name", "system_title", "base_url", "import_ignore_headers", "backup_keep", "default_printer")


@app.get("/api/settings")
def get_settings(u=Depends(need("asset.read"))):
    s = db.all_settings()
    return {k: s.get(k) for k in SETTING_KEYS} | {"detected_url": f"http://{lan_ip()}:{app.state.port}",
                                                  "data_dir": str(DIRS.data) if auth.can(u, "settings") else None}


@app.put("/api/settings")
async def put_settings(req: Request, u=Depends(need("settings"))):
    b = await body(req)
    for k in SETTING_KEYS:
        if k in b:
            db.set_setting(k, b[k])
    db.audit(u["username"], "settings", None, {k: b[k] for k in b if k in SETTING_KEYS}, ip(req))
    return get_settings(u)


@app.post("/api/backup")
def make_backup(req: Request, u=Depends(need("settings"))):
    name = db.backup("manual")
    db.audit(u["username"], "backup", name, ip=ip(req))
    return {"name": name}


@app.get("/api/backups")
def backups(u=Depends(need("settings"))):
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(DIRS.backups.glob("*.db"), reverse=True)]


@app.get("/api/backups/{name}")
def get_backup(name: str, u=Depends(need("settings"))):
    p = DIRS.backups / name
    if "/" in name or "\\" in name or not p.exists():
        raise ApiError(404, "NOT_FOUND", "Yedek bulunamadı")
    return FileResponse(p, filename=name)


@app.get("/api/license")
def lic(u=Depends(need("asset.read"))):
    return license.status()


@app.get("/api/update/check")
def upd_check(u=Depends(need("asset.read"))):
    return updater.check()


@app.post("/api/update/apply")
def upd_apply(req: Request, u=Depends(need("settings"))):
    db.backup("pre-update")
    db.audit(u["username"], "update_apply", ip=ip(req))
    try:
        return updater.apply(app.state.shutdown)
    except RuntimeError as e:
        raise ApiError(400, "UPDATE_FAILED", str(e))


# ---------- QR önizleme (telefon) ----------
_PREVIEW = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<link rel="stylesheet" href="/static/preview.css"></head><body><main class="card">
<header><div class="org">{org}</div><div class="unit">{unit}</div></header>
{body}</main><footer>NexEnvanter</footer></body></html>"""


@app.get("/e/{public_id}", response_class=HTMLResponse)
def preview(public_id: str, req: Request):
    s = db.all_settings()
    a = A.get(public_id=public_id) if public_id.replace("-", "").replace("_", "").isalnum() else None
    esc = html.escape
    if not a:
        b = '<div class="state bad">Kayıt bulunamadı</div><p class="muted">Etiket geçersiz ya da kayıt silinmiş olabilir.</p>'
        return HTMLResponse(_PREVIEW.format(title="Bulunamadı", org=esc(s["org_name"]), unit=esc(s["unit_name"]), body=b), 404)
    u = current_user(req)
    rows = []
    for f in F.all_fields():
        if not (f["public"] or (u and f["show_preview"])):
            continue
        v = a.get(f["key"]) if f["system"] else a["data"].get(f["key"])
        if v:
            rows.append(f"<dt>{esc(f['label'])}</dt><dd>{esc(str(v))}</dd>")
    state = '<div class="state warn">Arşivde</div>' if a["archived"] else '<div class="state ok">Cihaz bilgisi bulundu</div>'
    detail = (f'<a class="btn" href="/#/asset/{a["id"]}">Detayları Gör →</a>' if u and auth.can(u, "asset.read")
              else f'<a class="btn" href="/#/login?next=/asset/{a["id"]}">Giriş yap ve detayları gör →</a>')
    b = f'{state}<div class="code">{esc(a["asset_code"])}</div><dl>{"".join(rows)}</dl>{detail}'
    return HTMLResponse(_PREVIEW.format(title=esc(a["asset_code"]), org=esc(s["org_name"]), unit=esc(s["unit_name"]), body=b))


# ---------- web arayüzü ----------
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})
