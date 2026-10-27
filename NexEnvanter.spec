# PyInstaller: tek dosya exe — tüm Python bağımlılıkları ve web arayüzü exe içinde.
# Derleme: python build/make_assets.py && pyinstaller NexEnvanter.spec --noconfirm
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("uvicorn") + ["multipart", "python_multipart", "win32timezone"]

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
    console=True,          # sunucu penceresi: adres ve durum burada görünür
    upx=False,             # UPX antivirüs yanlış alarmlarını artırır
    icon="build/out/nexenvanter.ico",
    version="build/out/version.txt",
)
