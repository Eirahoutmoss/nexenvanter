# PyInstaller: tek dosya exe — tüm Python bağımlılıkları ve web arayüzü exe içinde.
# Derleme: python build/make_assets.py && pyinstaller NexEnvanter.spec --noconfirm
from PyInstaller.utils.hooks import collect_submodules

hidden = (collect_submodules("uvicorn") + collect_submodules("ldap3") +
          ["multipart", "python_multipart", "win32timezone", "pystray._win32"])

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
    console=False,         # tepsi simgesiyle çalışır; günlükler data\\logs altında
    upx=False,             # UPX antivirüs yanlış alarmlarını artırır
    icon="build/out/nexenvanter.ico",
    version="build/out/version.txt",
)
