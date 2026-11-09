"""NexAgent yönetim API'si (Ağ & Ajan sayfası ve cihaz kartı)."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from . import nexagent as NA
from .api import ApiError, body, ip, need

router = APIRouter(prefix="/api/nexagent")


def _node(aid: str) -> dict:
    n = NA.node(aid)
    if not n:
        raise ApiError(404, "NOT_FOUND", "Ajan bulunamadı")
    return n


@router.get("")
def overview(u=Depends(need("network"))):
    return NA.overview()


@router.put("/settings")
async def settings(req: Request, u=Depends(need("settings"))):
    try:
        NA.update_cfg(u["username"], await body(req))
    except (ValueError, TypeError) as e:
        raise ApiError(400, "BAD_REQUEST", str(e))
    return NA.overview()["cfg"]


@router.post("/discover")
async def discover(req: Request, u=Depends(need("settings"))):
    b = await body(req)
    targets = [x for x in (b.get("targets") or "").splitlines() if x.strip()] if isinstance(b.get("targets"), str) else b.get("targets") or []
    try:
        started = NA.discover(targets, u["username"])
    except ValueError as e:
        raise ApiError(400, "BAD_REQUEST", str(e))
    return {"started": started}


@router.post("/pull")
async def pull(req: Request, u=Depends(need("network"))):
    b = await body(req)
    return {"started": NA.pull_all(b.get("ids") or None, bool(b.get("fresh")), u["username"])}


@router.get("/job")
def job(u=Depends(need("network"))):
    return NA.STATE


@router.get("/nodes/{aid}")
def node(aid: str, u=Depends(need("network"))):
    return {"node": _node(aid), "snapshot": NA.snapshot(aid)}


@router.post("/nodes/{aid}/pull")
def pull_one(aid: str, u=Depends(need("network"))):
    _node(aid)
    try:
        return NA.pull_node(aid, True, u["username"])
    except NA.AgentError as e:
        raise ApiError(502, "AGENT_ERROR", str(e))


@router.post("/nodes/{aid}/override")
async def override(aid: str, req: Request, u=Depends(need("settings"))):
    _node(aid)
    NA.set_override(aid, (await body(req)).get("override"), u["username"])
    return NA.node(aid)


@router.post("/nodes/{aid}/accept-fingerprint")
def accept(aid: str, u=Depends(need("settings"))):
    _node(aid)
    try:
        NA.accept_fingerprint(aid, u["username"])
    except ValueError as e:
        raise ApiError(400, "BAD_REQUEST", str(e))
    return NA.node(aid)


@router.post("/nodes/{aid}/link")
async def link(aid: str, req: Request, u=Depends(need("network"))):
    _node(aid)
    b = await body(req)
    NA.link(aid, int(b.get("asset_id") or 0), u["username"])
    return NA.node(aid)


@router.post("/nodes/{aid}/uninstall")
async def uninstall(aid: str, req: Request, u=Depends(need("settings"))):
    n = _node(aid)
    b = await body(req)
    if (b.get("confirm") or "").strip().lower() != (n.get("hostname") or n["agent_id"]).lower():
        raise ApiError(400, "BAD_REQUEST", "Onay için bilgisayar adını yazın")
    try:
        NA.remote_uninstall(aid, u["username"], ip(req))
    except NA.AgentError as e:
        raise ApiError(502, "AGENT_ERROR", str(e))
    return NA.node(aid)


@router.delete("/nodes/{aid}")
def forget(aid: str, u=Depends(need("settings"))):
    _node(aid)
    NA.forget(aid, u["username"])
    return {"ok": True}


@router.get("/asset/{asset_id}")
def for_asset(asset_id: int, u=Depends(need("network"))):
    return NA.for_asset(asset_id) or {"node": None, "snapshot": None}


@router.post("/bins/fetch")
def fetch_bins(u=Depends(need("settings"))):
    try:
        return {"files": NA.fetch_bins_from_github()}
    except Exception as e:  # noqa: BLE001
        raise ApiError(502, "GITHUB", f"İndirilemedi: {e}")


@router.get("/package")
def package(os: str = "win", arch: str = "x64", u=Depends(need("settings"))):
    if os not in ("win", "linux") or arch not in ("x64", "arm64"):
        raise ApiError(400, "BAD_REQUEST", "Geçersiz hedef")
    try:
        data, name = NA.build_package(os, arch)
    except ValueError as e:
        raise ApiError(400, "BAD_REQUEST", str(e))
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})
