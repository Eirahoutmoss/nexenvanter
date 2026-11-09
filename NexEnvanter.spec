# PyInstaller: tek dosya exe — tüm Python bağımlılıkları ve web arayüzü exe içinde.
# Derleme: python build/make_assets.py && pyinstaller NexEnvanter.spec --noconfirm
import sys
from PyInstaller.utils.hooks import collect_submodules

WIN = sys.platform == "win32"
hidden = (collect_submodules("uvicorn") + collect_submodules("ldap3") + ["multipart", "python_multipart"] +
          (["win32timezone", "pystray._win32"] if WIN else []))

a = Analysis(
    ["run.py"],
    pathex=[],
    datas=[("web", "web")],
    hiddenimports=hidden,
    excludes=["tkinter", "unittest", "pytest", "numpy", "pandas", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="NexEnvanter",
    console=not WIN,       # Windows: tepsi simgesiyle çalışır; Linux: konsol/systemd. Günlükler data/logs altında
    upx=False,             # UPX antivirüs yanlış alarmlarını artırır
    icon="build/out/nexenvanter.ico" if WIN else None,
    version="build/out/version.txt" if WIN else None,
)
