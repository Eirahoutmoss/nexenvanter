"""Etiket çizici: milimetre tabanlı şablon → yazıcı DPI'ında görüntü (önizleme, PDF ve yazıcı için ortak)."""
import copy
import io
import os
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from . import db
from .paths import DIRS
from .textnorm import tr_upper

# Brother PT-P900WC: 360 dpi, TZe şerit en fazla 36 mm. Ölçüler sahada doğrulanmalı.
DEFAULT_TEMPLATE = {
    "name": "Varsayılan 70×36 mm",
    "width_mm": 70, "height_mm": 36, "dpi": 360, "margin_mm": 1.2,
    "border": True, "uppercase": True,
    "header": {"enabled": True, "text": "{org_name}", "height_pct": 24, "inverted": True},
    "subheader": {"enabled": True, "lines": ["{unit_name}", "{system_title}"], "height_pct": 22},
    "rows": [
        {"label": "ÜRÜN MARKA MODEL", "field": "brand_model"},
        {"label": "BİRİM ADI", "field": "location_name"},
        {"label": "SERİ NO", "field": "serial_number"},
    ],
    "qr": {"enabled": True, "show_code": True, "quiet_modules": 2},
    "logo_left": False, "logo_right": False,
}

_FONT_CANDIDATES = {
    True: ["arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    False: ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"],
}
_FONT_DIRS = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu"),
              Path("/usr/share/fonts/truetype/liberation"), Path("/usr/share/fonts/TTF")]


@lru_cache(maxsize=4)
def _font_path(bold: bool):
    for name in _FONT_CANDIDATES[bold]:
        for d in _FONT_DIRS:
            if (d / name).exists():
                return str(d / name)
    return None


@lru_cache(maxsize=256)
def font(size: int, bold=False):
    p = _font_path(bold)
    return ImageFont.truetype(p, size) if p else ImageFont.load_default(size)


def get_template() -> dict:
    t = db.get_setting("label_template")
    base = copy.deepcopy(DEFAULT_TEMPLATE)
    if isinstance(t, dict):
        base.update(t)
    return base


def logo_path(side: str) -> Path:
    return DIRS.uploads / f"logo_{side}.png"


def _fit(draw, text, max_w, max_h, bold=True, min_size=8):
    """Kutuya sığan en büyük yazı boyutu; en küçükte de sığmazsa '…' ile kısalt."""
    size = max(min_size, int(max_h * 0.82))
    while size > min_size:
        f = font(size, bold)
        if draw.textlength(text, font=f) <= max_w:
            return text, f
        size -= 1
    f = font(min_size, bold)
    while text and draw.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return (text + "…") if text else "", f


def _center(draw, box, text, bold=True, fill=0):
    x0, y0, x1, y1 = box
    text, f = _fit(draw, text, x1 - x0, y1 - y0, bold)
    draw.text(((x0 + x1) / 2, (y0 + y1) / 2), text, font=f, fill=fill, anchor="mm")


def _qr(data: str, size: int, quiet: int) -> Image.Image:
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=quiet)
    q.add_data(data)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("L")
    mod = max(1, size // img.size[0])  # tam sayı modül ölçeği: keskin kenar
    return img.resize((img.size[0] * mod, img.size[1] * mod), Image.NEAREST)


def render(asset: dict, url: str, tpl: dict | None = None, settings: dict | None = None) -> Image.Image:
    tpl = tpl or get_template()
    s = settings or db.all_settings()
    dpi = int(tpl["dpi"])
    px = lambda mm: int(round(mm * dpi / 25.4))  # noqa: E731
    W, H, m = px(tpl["width_mm"]), px(tpl["height_mm"]), px(tpl["margin_mm"])
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    up = tr_upper if tpl.get("uppercase") else (lambda x: x)
    sub = lambda t: t.format_map({k: (v if isinstance(v, str) else "") for k, v in s.items()})  # noqa: E731
    lw = max(1, px(0.25))
    x0, y, x1, y1 = m, m, W - m, H - m
    inner = x1 - x0

    hd = tpl.get("header", {})
    if hd.get("enabled"):
        hh = int((y1 - y) * hd.get("height_pct", 24) / 100)
        inv = hd.get("inverted", True)
        if inv:
            d.rectangle([x0, y, x1, y + hh], fill=0)
        pad = hh // 8
        lx0, lx1 = x0 + pad, x1 - pad
        for side in ("left", "right"):
            lp = logo_path(side)
            if tpl.get(f"logo_{side}") and lp.exists():
                lg = Image.open(lp).convert("L")
                lg.thumbnail((hh - 2 * pad, hh - 2 * pad))
                lx = lx0 if side == "left" else lx1 - lg.size[0]
                img.paste(lg, (lx, y + (hh - lg.size[1]) // 2))
                if side == "left":
                    lx0 += lg.size[0] + pad
                else:
                    lx1 -= lg.size[0] + pad
        _center(d, (lx0, y + pad, lx1, y + hh - pad), up(sub(hd.get("text", ""))), True, 255 if inv else 0)
        y += hh + lw

    sh = tpl.get("subheader", {})
    if sh.get("enabled") and sh.get("lines"):
        hh = int((y1 - m) * sh.get("height_pct", 22) / 100)
        d.rectangle([x0, y, x1, y + hh], outline=0, width=lw)
        n = len(sh["lines"])
        for i, line in enumerate(sh["lines"]):
            _center(d, (x0 + lw * 3, y + i * hh / n + lw, x1 - lw * 3, y + (i + 1) * hh / n), up(sub(line)), True)
        y += hh + lw * 2

    body_h = y1 - y
    rows = tpl.get("rows", [])
    qrc = tpl.get("qr", {})
    tx1 = x1
    if qrc.get("enabled"):
        code_h = int(body_h * 0.16) if qrc.get("show_code") else 0
        qs = min(body_h - code_h, int(inner * 0.4))
        q = _qr(url, qs, int(qrc.get("quiet_modules", 2)))
        qx = x1 - q.size[0]
        img.paste(q, (qx, y + (body_h - code_h - q.size[1]) // 2))
        if code_h:
            _center(d, (qx, y1 - code_h, x1, y1), str(asset.get("asset_code", "")), True)
        tx1 = qx - px(0.8)
    if rows:
        rh = body_h / len(rows)
        tw = tx1 - x0 - lw * 6
        texts = []
        for r in rows:
            key = r.get("field")
            val = asset.get(key) if key in ("asset_code", "status") else asset.get("data", {}).get(key)
            texts.append(up(f"{r.get('label', '')} : {val or ''}" if r.get("label") else str(val or "")))
        # Tüm satırlarda ortak yazı boyutu: en uzun satırın sığdığı boyut (çok kısalırsa satır kendi içinde kısaltılır)
        cap = int(rh * 0.6)
        common = min(_fit(d, t, tw, cap, False)[1].size for t in texts)
        common = max(common, int(cap * 0.55))
        for i, text in enumerate(texts):
            ry0, ry1 = int(y + i * rh + lw), int(y + (i + 1) * rh - lw)
            d.rectangle([x0, ry0, tx1, ry1], outline=0, width=lw)
            text, f = _fit(d, text, tw, common / 0.82, False)
            d.text((x0 + lw * 3, (ry0 + ry1) / 2), text, font=f, fill=0, anchor="lm")
    if tpl.get("border"):
        d.rectangle([0, 0, W - 1, H - 1], outline=0, width=lw)
    return img


def png(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def pdf(images: list[Image.Image], dpi: int) -> bytes:
    """Her etiket bir sayfa; sayfa ölçüsü etiket ölçüsü (mm) ile birebir."""
    b = io.BytesIO()
    first, rest = images[0].convert("RGB"), [i.convert("RGB") for i in images[1:]]
    first.save(b, "PDF", resolution=dpi, save_all=True, append_images=rest)
    return b.getvalue()
