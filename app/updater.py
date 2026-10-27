"""GitHub son sürüm kontrolü ve uygulama içinden güncelleme (yalnızca derlenmiş exe'de uygulanır)."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

from . import APP_NAME, GITHUB_REPO, VERSION
from .paths import DIRS, EXE_PATH, FROZEN

API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = f"{APP_NAME}.exe"


def _ver(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s or "0")[:3]) or (0,)


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def check() -> dict:
    try:
        with _get(API) as r:
            rel = json.load(r)
    except Exception as e:
        return {"ok": False, "current": VERSION, "message": f"GitHub'a ulaşılamadı: {e}"}
    latest = rel.get("tag_name", "")
    asset = next((a for a in rel.get("assets", []) if a["name"].lower() == ASSET_NAME.lower()), None)
    return {
        "ok": True, "current": VERSION, "latest": latest.lstrip("v"), "name": rel.get("name"),
        "notes": rel.get("body") or "", "url": rel.get("html_url"),
        "update_available": _ver(latest) > _ver(VERSION),
        "download_url": asset["browser_download_url"] if asset else None,
        "size": asset["size"] if asset else None, "can_apply": FROZEN and sys.platform == "win32" and bool(asset),
    }


def apply(shutdown) -> dict:
    """Yeni exe'yi indir, çalışan exe'nin yerine koyacak betiği başlat, sunucuyu kapat."""
    info = check()
    if not info.get("update_available"):
        raise RuntimeError("Güncelleme yok")
    if not info.get("can_apply"):
        raise RuntimeError("Otomatik kurulum yalnızca Windows exe sürümünde yapılabilir")
    new = DIRS.tmp / f"{APP_NAME}-{info['latest']}.exe"
    with _get(info["download_url"], timeout=120) as r, open(new, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
    if info.get("size") and new.stat().st_size != info["size"]:
        new.unlink(missing_ok=True)
        raise RuntimeError("İndirme eksik; tekrar deneyin")
    bat = DIRS.tmp / "nexenvanter_update.cmd"
    args = subprocess.list2cmdline(sys.argv[1:])
    bat.write_text(
        "@echo off\r\n"
        f"set PID={os.getpid()}\r\n"
        ":wait\r\n"
        'tasklist /FI "PID eq %PID%" | find "%PID%" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
        f'copy /y "{EXE_PATH}" "{EXE_PATH}.bak" >nul\r\n'
        f'move /y "{new}" "{EXE_PATH}" >nul || (copy /y "{EXE_PATH}.bak" "{EXE_PATH}" >nul)\r\n'
        f'start "" "{EXE_PATH}" {args}\r\n'
        'del "%~f0"\r\n', encoding="cp1254", errors="replace")
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x00000008 | 0x00000200, close_fds=True)  # DETACHED

    def stop():
        time.sleep(1.0)
        shutdown()
    threading.Thread(target=stop, daemon=True).start()
    return {"ok": True, "message": f"{info['latest']} kuruluyor; program yeniden başlatılacak."}
