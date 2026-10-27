"""Çalışma dizinleri: exe içindeki kaynaklar (salt okunur) ve veri klasörü (yazılabilir)."""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Paket içi kaynaklar (web/, assets/). PyInstaller onefile'da _MEIPASS altına açılır.
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = RES_DIR / "web"

EXE_PATH = Path(sys.executable).resolve() if FROZEN else None


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        t = p / ".w"
        t.write_text("1")
        t.unlink()
        return True
    except OSError:
        return False


def resolve_data_dir(override: str | None = None) -> Path:
    """Öncelik: --data > NEXENVANTER_DATA > exe yanındaki data/ (taşınabilir) > %LOCALAPPDATA%."""
    cands = []
    if override:
        cands.append(Path(override))
    if os.environ.get("NEXENVANTER_DATA"):
        cands.append(Path(os.environ["NEXENVANTER_DATA"]))
    base = EXE_PATH.parent if FROZEN else Path(__file__).resolve().parent.parent
    cands.append(base / "data")
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    cands.append(Path(local) / "NexEnvanter")
    for c in cands:
        if _writable(c):
            return c.resolve()
    raise RuntimeError("Yazılabilir veri klasörü bulunamadı")


class _Dirs:
    data: Path
    backups: Path
    tmp: Path
    uploads: Path

    def init(self, override=None):
        self.data = resolve_data_dir(override)
        for name in ("backups", "tmp", "uploads"):
            d = self.data / name
            d.mkdir(exist_ok=True)
            setattr(self, name, d)
        self.db = self.data / "nexenvanter.db"
        return self


DIRS = _Dirs()
