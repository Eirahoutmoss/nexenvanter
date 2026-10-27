"""Derleme öncesi: exe simgesi (.ico) ve Windows sürüm bilgisi dosyasını üretir."""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "out"
OUT.mkdir(parents=True, exist_ok=True)

version = re.search(r'VERSION = "([^"]+)"', (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")).group(1)
if len(sys.argv) > 1:  # CI: etiketten gelen sürüm
    version = sys.argv[1].lstrip("v")
    p = ROOT / "app" / "__init__.py"
    p.write_text(re.sub(r'VERSION = "[^"]+"', f'VERSION = "{version}"', p.read_text(encoding="utf-8")), encoding="utf-8")

# Simge: logo.svg ile aynı geometri (64 birimlik ızgara)
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=48, fill=(10, 20, 48, 255))
k = S / 64
pts = [(8, 56), (8, 8), (20, 8), (44, 38), (44, 8), (56, 8), (56, 56), (44, 56), (20, 26), (20, 56)]
d.polygon([(x * k, y * k) for x, y in pts], fill=(47, 123, 255, 255))
img.save(OUT / "nexenvanter.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

nums = (list(map(int, re.findall(r"\d+", version))) + [0, 0, 0, 0])[:4]
(OUT / "version.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(nums)}, prodvers={tuple(nums)}, mask=0x3f, flags=0x0, OS=0x40004,
    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('041F04B0', [
    StringStruct('CompanyName', 'Hasan Güler'),
    StringStruct('FileDescription', 'NexEnvanter - Hastane Envanter Yönetim Sistemi'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'NexEnvanter'),
    StringStruct('LegalCopyright', '© Hasan Güler'),
    StringStruct('OriginalFilename', 'NexEnvanter.exe'),
    StringStruct('ProductName', 'NexEnvanter'),
    StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [0x041F, 1200])])])
""", encoding="utf-8")
print("Sürüm:", version)
