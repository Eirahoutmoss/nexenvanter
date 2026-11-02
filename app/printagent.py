"""Kullanıcı oturumu yazdırma aracısı.

Hizmet (SYSTEM) olarak çalışan sunucu, kullanıcıya ait yazıcıları (ağ/paylaşılan yazıcı bağlantıları) göremez.
Oturum açan kullanıcının tepsi süreci bu aracıyı çalıştırır: yazıcı listesini sunucuya bildirir, kuyruktaki
işleri alıp kullanıcının yazıcısına basar. Haberleşme yalnızca 127.0.0.1 üzerinden ve veri klasöründeki
anahtarla yapılır. Boşta iken 2 sn'de bir hafif bir istek atar.
"""
import base64
import io
import json
import secrets
import threading
import time
import uuid

from .paths import DIRS

AGENT_TTL = 15          # sn: bu süre bildirim gelmezse aracı çevrimdışı sayılır
_agents: dict[str, dict] = {}
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
UPDATE_PENDING = {"on": False}


def key() -> str:
    p = DIRS.data / "printagent.key"
    if not p.exists():
        p.write_text(secrets.token_urlsafe(24), encoding="utf-8")
    return p.read_text(encoding="utf-8").strip()


# ---------------- sunucu tarafı ----------------
def hello(agent_id: str, user: str, printers: list[str]) -> dict:
    with _lock:
        _agents[agent_id] = {"id": agent_id, "user": user, "printers": printers, "seen": time.time()}
        job = next((j for j in _jobs.values() if j["agent"] == agent_id and j["state"] == "queued"), None)
        if job:
            job["state"] = "taken"
    return {"job": {k: job[k] for k in ("id", "printer", "width_mm", "height_mm", "count", "copies", "profile")} if job else None,
            "update_pending": UPDATE_PENDING["on"]}


def online() -> list[dict]:
    now = time.time()
    return [a for a in _agents.values() if now - a["seen"] < AGENT_TTL]


def printers() -> list[dict]:
    out = []
    for a in online():
        out += [{"name": p, "adapter": "agent", "agent": a["id"], "user": a["user"]} for p in a["printers"]]
    return out


def agent_for(printer: str) -> str | None:
    return next((a["id"] for a in online() if printer in a["printers"]), None)


def submit(printer, render, width_mm, height_mm, count, copies, profile, timeout=120):
    """İşi aracıya ver ve bitmesini bekle (render(i, dpi) aracı istedikçe çağrılır)."""
    aid = agent_for(printer)
    if not aid:
        raise RuntimeError("Bu yazıcıyı gören kullanıcı oturumu çevrimdışı (NexEnvanter tepsi simgesi açık olmalı)")
    jid = uuid.uuid4().hex
    ev = threading.Event()
    with _lock:
        _jobs[jid] = {"id": jid, "agent": aid, "printer": printer, "width_mm": width_mm, "height_mm": height_mm, "count": count,
                      "copies": copies, "profile": profile, "render": render, "state": "queued", "event": ev, "error": None,
                      "at": time.time()}
    try:
        if not ev.wait(timeout):
            raise RuntimeError("Yazdırma aracısı yanıt vermedi")
        j = _jobs[jid]
        if j["error"]:
            raise RuntimeError(j["error"])
    finally:
        with _lock:
            _jobs.pop(jid, None)


def page(jid: str, i: int, dpi: int) -> bytes:
    j = _jobs.get(jid)
    if not j or not 0 <= i < j["count"]:
        raise KeyError(jid)
    img = j["render"](i, dpi)
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def done(jid: str, error: str | None):
    j = _jobs.get(jid)
    if j:
        j["error"] = error
        j["state"] = "done"
        j["event"].set()


# ---------------- tepsi (kullanıcı) tarafı ----------------
def run_client(base: str, stop: threading.Event, on_update=None):
    """Tepsi sürecinde arka planda çalışır."""
    import getpass
    import urllib.request
    from PIL import Image
    from . import printing
    k = key()
    aid = uuid.uuid4().hex[:12]
    adapter = printing.WindowsSpoolerAdapter()
    if not adapter.available():
        return

    def call(path, data=None, raw=False):
        req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"X-Agent-Key": k, "Content-Type": "application/json", "x-nx": "1"},
                                     method="POST" if data is not None else "GET")
        import ssl
        ctx = ssl._create_unverified_context() if base.startswith("https://127.0.0.1") else None  # yalnızca yerel bağlantı
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            body = r.read()
            return body if raw else json.loads(body)

    names, last_list = [], 0
    while not stop.is_set():
        try:
            if time.time() - last_list > 30:
                names = [p["name"] for p in adapter.list_printers()]
                last_list = time.time()
            r = call("/api/printagent/hello", {"id": aid, "user": getpass.getuser(), "printers": names})
            if r.get("update_pending") and on_update:
                on_update()
                return
            j = r.get("job")
            if j:
                err = None
                try:
                    def render(i, dpi, jid=j["id"]):
                        png = call(f"/api/printagent/page?job={jid}&i={i}&dpi={dpi}", raw=True)
                        return Image.open(io.BytesIO(png)).convert("L")
                    adapter.print_labels(j["printer"], render, j["width_mm"], j["height_mm"], j["count"], j["copies"], j["profile"])
                except Exception as e:
                    err = str(e)
                call("/api/printagent/done", {"job": j["id"], "error": err})
                continue
        except Exception:
            pass
        stop.wait(2)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
