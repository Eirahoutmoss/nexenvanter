"""Etiket çizici: milimetre tabanlı şablon → yazıcı DPI'ında görüntü (önizleme, PDF ve yazıcı için ortak).

Baskı kalitesi: termal/termal transfer yazıcılarda gri tonlar (kenar yumuşatma) silik çıkar. Bu yüzden
varsayılan olarak görüntü yazıcının kendi DPI'ında çizilir ve saf siyah-beyaza eşiklenir; ince yazı
tipleri için isteğe bağlı kalınlaştırma (kontur) uygulanır. Yazıcıya ölçeklemeden, piksel piksel gönderilir.
"""
import copy
import io
import os
import sys
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from . import db
from .paths import DIRS
from .textnorm import tr_upper

_BASE_STYLE = {"family": "Arial", "size": 0, "bold": True, "align": "left"}

# Brother PT-P900Wc: 360 dpi, en geniş şerit 36 mm (basılabilir ~32 mm). 80×40 için başka yazıcı ya da "sığdır" gerekir.
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
    "row_layout": {"label_col_pct": 0, "separator": " : ", "row_boxes": True, "wrap_values": True, "line_spacing": 1.0},
    "qr": {"enabled": True, "show_code": True, "quiet_modules": 2},
    "barcode": {"enabled": False, "field": "asset_code", "height_pct": 20, "show_text": False},
    "logo_left": False, "logo_right": False,
    "styles": {
        "header": {**_BASE_STYLE, "align": "center"},
        "subheader": {**_BASE_STYLE, "align": "center"},
        "label": {**_BASE_STYLE},
        "value": {**_BASE_STYLE},
        "code": {**_BASE_STYLE, "align": "center"},
    },
    # mono: saf siyah-beyaz; threshold: eşik (0-255, büyüdükçe daha koyu); boost: ek kalınlaştırma (piksel, 360 dpi'da)
    "quality": {"mono": True, "threshold": 150, "boost": 0, "min_pt": 5},
}

PRESETS = [
    {"name": "80 × 40 mm etiket", "width_mm": 80, "height_mm": 40},
    {"name": "80 × 36 mm (36 mm şerit)", "width_mm": 80, "height_mm": 36},
    {"name": "70 × 36 mm (36 mm şerit)", "width_mm": 70, "height_mm": 36},
    {"name": "60 × 24 mm (24 mm şerit)", "width_mm": 60, "height_mm": 24},
    {"name": "62 × 29 mm", "width_mm": 62, "height_mm": 29},
    {"name": "100 × 50 mm", "width_mm": 100, "height_mm": 50},
]

# Görünen ad → (normal dosya, kalın dosya). Yalnızca bilgisayarda bulunanlar listelenir.
FAMILIES = {
    "Arial": ("arial.ttf", "arialbd.ttf"),
    "Arial Narrow": ("arialn.ttf", "arialnb.ttf"),
    "Arial Black": ("ariblk.ttf", "ariblk.ttf"),
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf"),
    "Segoe UI Semibold": ("seguisb.ttf", "segoeuib.ttf"),
    "Tahoma": ("tahoma.ttf", "tahomabd.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf"),
    "Trebuchet MS": ("trebuc.ttf", "trebucbd.ttf"),
    "Consolas": ("consola.ttf", "consolab.ttf"),
    "Bahnschrift": ("bahnschrift.ttf", "bahnschrift.ttf"),
    "Franklin Gothic": ("framd.ttf", "framd.ttf"),
    "DejaVu Sans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    "DejaVu Sans Condensed": ("DejaVuSansCondensed.ttf", "DejaVuSansCondensed-Bold.ttf"),
    "DejaVu Sans Mono": ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf"),
    "Liberation Sans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    "Liberation Sans Narrow": ("LiberationSansNarrow-Regular.ttf", "LiberationSansNarrow-Bold.ttf"),
    "Carlito": ("Carlito-Regular.ttf", "Carlito-Bold.ttf"),
}
_FALLBACK = ["Arial", "Segoe UI", "DejaVu Sans", "Liberation Sans", "Carlito"]


def _font_dirs():
    dirs = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        dirs.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts")
    dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    return dirs


@lru_cache(maxsize=1)
def _font_index() -> dict:
    """küçük harfli dosya adı → tam yol (Linux'ta alt klasörler dahil)."""
    idx = {}
    for d in _font_dirs():
        if not d.is_dir():
            continue
        it = d.rglob("*") if not str(d).lower().endswith("fonts") or sys.platform != "win32" else d.iterdir()
        try:
            for p in it:
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    idx.setdefault(p.name.lower(), str(p))
        except OSError:
            continue
    return idx


def available_families() -> list[str]:
    idx = _font_index()
    return [n for n, (r, _) in FAMILIES.items() if r.lower() in idx]


def _resolve(family: str, bold: bool) -> tuple[str | None, bool]:
    """→ (yol, sentetik_kalın). Kalın dosyası yoksa normal dosya + kontur ile kalınlaştırılır."""
    idx = _font_index()
    for fam in [family] + _FALLBACK:
        pair = FAMILIES.get(fam)
        if not pair:
            continue
        reg, bld = (idx.get(pair[0].lower()), idx.get(pair[1].lower()))
        if bold and bld:
            return bld, False
        if reg:
            return reg, bold
    return None, bold


@lru_cache(maxsize=512)
def _font(family: str, bold: bool, size: int):
    path, synth = _resolve(family, bold)
    f = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    return f, synth


def font(size: int, bold=False, family="Arial"):
    """Geriye uyumluluk."""
    return _font(family, bold, int(size))[0]


def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def normalize(t: dict | None) -> dict:
    return _deep_merge(copy.deepcopy(DEFAULT_TEMPLATE), t if isinstance(t, dict) else {})


def get_template() -> dict:
    return normalize(db.get_setting("label_template"))


def logo_path(side: str) -> Path:
    return DIRS.uploads / f"logo_{side}.png"


class _Ctx:
    def __init__(self, draw, dpi, quality):
        self.d, self.dpi, self.q = draw, dpi, quality
        self.boost = int(round(float(quality.get("boost", 0)) * dpi / 360))
        self.min_px = max(6, int(float(quality.get("min_pt", 5)) * dpi / 72))

    def pt(self, pt):
        return int(round(float(pt) * self.dpi / 72))

    def width(self, text, f, stroke):
        return self.d.textlength(text, font=f) + 2 * stroke

    def fit(self, text, style, max_w, max_h):
        """Stile göre yazı tipi; boyut 0 ise kutuya sığan en büyük, verilmişse o boyut (taşarsa küçültülür)."""
        fam, bold = style.get("family", "Arial"), bool(style.get("bold", True))
        want = int(style["_px"]) if style.get("_px") else (
            self.pt(style["size"]) if float(style.get("size") or 0) > 0 else int(max_h * 0.82))
        size = max(self.min_px, min(want, int(max_h * 0.95)))
        while True:
            f, synth = _font(fam, bold, size)
            stroke = self.boost + (max(1, size // 22) if synth else 0)
            if self.width(text, f, stroke) <= max_w or size <= self.min_px:
                break
            size -= 1
        while text and self.width(text, f, stroke) > max_w:
            text = text[:-2] + "…" if len(text) > 2 else ""
        return text, f, stroke

    def draw(self, box, text, style, fill=0, valign="m"):
        x0, y0, x1, y1 = box
        text, f, stroke = self.fit(text, style, x1 - x0, y1 - y0)
        al = style.get("align", "left")
        x = {"center": (x0 + x1) / 2, "right": x1 - stroke}.get(al, x0 + stroke)
        anchor = {"center": "m", "right": "r"}.get(al, "l") + valign
        y = (y0 + y1) / 2
        self.d.text((x, y), text, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=fill)
        return self.width(text, f, stroke)

    def wrap2(self, text, style, max_w, max_h, spacing):
        """Değeri en fazla 2 satıra böl; tek satırda okunaklı sığmıyorsa kullanılır."""
        words = text.split()
        if len(words) < 2:
            return None
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            line_h = max_h / (2 * spacing)
            _, fa, sa = self.fit(a, style, max_w, line_h)
            _, fb, sb = self.fit(b, style, max_w, line_h)
            size = min(fa.size, fb.size)
            if best is None or size > best[0]:
                best = (size, a, b)
        return best


def _qr(data: str, size: int, quiet: int) -> Image.Image:
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=quiet)
    q.add_data(data)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("L")
    mod = max(1, size // img.size[0])  # tam sayı modül ölçeği: keskin kenar
    return img.resize((img.size[0] * mod, img.size[1] * mod), Image.NEAREST)


def _code128(data: str, width: int, height: int) -> Image.Image | None:
    import barcode
    try:
        mods = barcode.get("code128", str(data)).build()[0]
    except Exception:
        return None
    quiet = 10
    total = len(mods) + 2 * quiet
    mw = max(1, width // total)  # tam sayı modül genişliği: okuyucu dostu
    img = Image.new("L", (total * mw, height), 255)
    d = ImageDraw.Draw(img)
    for i, bit in enumerate(mods):
        if bit == "1":
            x = (quiet + i) * mw
            d.rectangle([x, 0, x + mw - 1, height - 1], fill=0)
    return img


def _value(asset, key):
    return asset.get(key) if key in ("asset_code", "status") else asset.get("data", {}).get(key)


def render(asset: dict, url: str, tpl: dict | None = None, settings: dict | None = None, dpi: int | None = None) -> Image.Image:
    tpl = normalize(tpl) if tpl is not None else get_template()
    s = settings or db.all_settings()
    dpi = int(dpi or tpl["dpi"])
    px = lambda mm: int(round(float(mm) * dpi / 25.4))  # noqa: E731
    W, H, m = px(tpl["width_mm"]), px(tpl["height_mm"]), px(tpl["margin_mm"])
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    q = tpl.get("quality", {})
    cx = _Ctx(d, dpi, q)
    st = tpl["styles"]
    up = tr_upper if tpl.get("uppercase") else (lambda x: x)
    sub = lambda t: t.format_map({k: (v if isinstance(v, str) else "") for k, v in s.items()})  # noqa: E731
    lw = max(1, px(0.3))
    x0, y, x1, y1 = m, m, W - m, H - m
    inner = x1 - x0

    hd = tpl.get("header", {})
    if hd.get("enabled"):
        hh = int((y1 - y) * hd.get("height_pct", 24) / 100)
        inv = hd.get("inverted", True)
        if inv:
            d.rectangle([x0, y, x1, y + hh], fill=0)
        pad = max(1, hh // 9)
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
        cx.draw((lx0, y + pad, lx1, y + hh - pad), up(sub(hd.get("text", ""))), st["header"], 255 if inv else 0)
        y += hh + lw

    sh = tpl.get("subheader", {})
    if sh.get("enabled") and sh.get("lines"):
        hh = int((y1 - m) * sh.get("height_pct", 22) / 100)
        d.rectangle([x0, y, x1, y + hh], outline=0, width=lw)
        n = len(sh["lines"])
        for i, line in enumerate(sh["lines"]):
            cx.draw((x0 + lw * 3, y + i * hh / n + lw, x1 - lw * 3, y + (i + 1) * hh / n - lw), up(sub(line)), st["subheader"])
        y += hh + lw * 2

    # Barkod şeridi (isteğe bağlı) gövdenin altında
    bc = tpl.get("barcode", {})
    bc_h = int((y1 - y) * bc.get("height_pct", 20) / 100) if bc.get("enabled") else 0
    body_y1 = y1 - (bc_h + lw if bc_h else 0)

    body_h = body_y1 - y
    rows = tpl.get("rows", [])
    qrc = tpl.get("qr", {})
    tx1 = x1
    if qrc.get("enabled"):
        code_h = int(body_h * 0.17) if qrc.get("show_code") else 0
        qs = min(body_h - code_h, int(inner * 0.4))
        qimg = _qr(url, qs, int(qrc.get("quiet_modules", 2)))
        qx = x1 - qimg.size[0]
        img.paste(qimg, (qx, y + (body_h - code_h - qimg.size[1]) // 2))
        if code_h:
            cx.draw((qx, body_y1 - code_h, x1, body_y1), str(asset.get("asset_code", "")), st["code"])
        tx1 = qx - px(0.8)

    rl = tpl.get("row_layout", {})
    if rows:
        rh = body_h / len(rows)
        pad = lw * 3
        boxes = rl.get("row_boxes", True)
        col = float(rl.get("label_col_pct") or 0)
        sep = rl.get("separator", " : ")
        spacing = max(0.8, float(rl.get("line_spacing") or 1.0))
        tw = (tx1 - pad) - (x0 + pad)
        h_txt = (rh - 4 * lw) * 0.92
        items = [(up(r.get("label") or ""), up(str(_value(asset, r.get("field")) or ""))) for r in rows]
        has_label = any(lab for lab, _ in items)
        sep_txt = sep if not col else ""
        # 1) başlıklar: tüm satırlarda ortak boyut
        lab_w = tw * col / 100 if col else tw * 0.5
        colon_w = cx.pt(5) if col and sep.strip() else 0
        lsz = min([cx.fit(lab + sep_txt, st["label"], lab_w - colon_w, h_txt)[1].size for lab, _ in items if lab] or [0])
        lst = {**st["label"], "_px": lsz, "align": "left"}
        # 2) değerler: ortak boyut (en uzun değer çok küçültürse o satır 2 satıra bölünür)
        starts = []
        for lab, _ in items:
            if not lab:
                starts.append(x0 + pad)
            elif col:
                starts.append(x0 + pad + lab_w + cx.pt(1))
            else:
                f, _sy = _font(lst["family"], bool(lst.get("bold", True)), lsz)
                starts.append(x0 + pad + cx.width(lab + sep_txt, f, cx.boost) + cx.pt(1))
        want = cx.pt(st["value"]["size"]) if float(st["value"].get("size") or 0) > 0 else int(h_txt * 0.82)
        fits = [cx.fit(v, st["value"], (tx1 - pad) - sx, h_txt)[1].size if v else want for (_, v), sx in zip(items, starts)]
        floor = int(want * 0.62)
        vsz = max(min(fits), min(floor, max(fits)))
        vst = {**st["value"], "_px": vsz}
        for i, ((lab, val), sx) in enumerate(zip(items, starts)):
            ry0, ry1 = int(y + i * rh + lw), int(y + (i + 1) * rh - lw)
            if boxes:
                d.rectangle([x0, ry0, tx1, ry1], outline=0, width=lw)
            tb = (x0 + pad, ry0 + lw, tx1 - pad, ry1 - lw)
            if lab:
                if col:
                    cx.draw((tb[0], tb[1], tb[0] + lab_w - colon_w, tb[3]), lab, lst)
                    if colon_w:
                        cx.draw((tb[0] + lab_w - colon_w, tb[1], tb[0] + lab_w, tb[3]), sep.strip(), {**lst, "align": "center"})
                else:
                    cx.draw((tb[0], tb[1], sx, tb[3]), lab + sep_txt, lst)
            if not val or tb[2] - sx < 4:
                continue
            vbox = (sx, tb[1], tb[2], tb[3])
            if fits[i] < vsz and rl.get("wrap_values", True):
                w2 = cx.wrap2(val, {**st["value"], "_px": vsz}, tb[2] - sx, tb[3] - tb[1], spacing)
                if w2 and w2[0] > fits[i]:
                    mid = (vbox[1] + vbox[3]) / 2
                    gap = (vbox[3] - vbox[1]) * (spacing - 1) / 4
                    cx.draw((vbox[0], vbox[1], vbox[2], mid - gap), w2[1], vst)
                    cx.draw((vbox[0], mid + gap, vbox[2], vbox[3]), w2[2], vst)
                    continue
            cx.draw(vbox, val, vst)

    if bc_h:
        code = str(_value(asset, bc.get("field") or "asset_code") or "")
        txt_h = int(bc_h * 0.3) if bc.get("show_text") else 0
        bimg = _code128(code, x1 - x0, bc_h - txt_h)
        if bimg:
            img.paste(bimg, (x0 + (inner - bimg.size[0]) // 2, body_y1 + lw))
        if txt_h:
            cx.draw((x0, y1 - txt_h, x1, y1), code, st["code"])

    if tpl.get("border"):
        d.rectangle([0, 0, W - 1, H - 1], outline=0, width=lw)
    if q.get("mono", True):
        t = int(q.get("threshold", 150))
        img = img.point(lambda v: 0 if v < t else 255)
    return img


def calibration(tpl: dict | None = None, dpi: int | None = None) -> Image.Image:
    """Ölçü/kenar boşluğu ayarı için: çerçeve, mm cetveli, merkez artısı ve ölçü yazısı."""
    tpl = normalize(tpl) if tpl is not None else get_template()
    dpi = int(dpi or tpl["dpi"])
    px = lambda mm: int(round(mm * dpi / 25.4))  # noqa: E731
    W, H = px(tpl["width_mm"]), px(tpl["height_mm"])
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    lw = max(1, px(0.3))
    d.rectangle([0, 0, W - 1, H - 1], outline=0, width=lw)
    for mm in range(0, int(tpl["width_mm"]) + 1):
        ln = px(3 if mm % 10 == 0 else 2 if mm % 5 == 0 else 1)
        d.line([px(mm), 0, px(mm), ln], fill=0, width=lw)
        d.line([px(mm), H - ln, px(mm), H], fill=0, width=lw)
    for mm in range(0, int(tpl["height_mm"]) + 1):
        ln = px(3 if mm % 10 == 0 else 2 if mm % 5 == 0 else 1)
        d.line([0, px(mm), ln, px(mm)], fill=0, width=lw)
        d.line([W - ln, px(mm), W, px(mm)], fill=0, width=lw)
    d.line([W // 2 - px(4), H // 2, W // 2 + px(4), H // 2], fill=0, width=lw)
    d.line([W // 2, H // 2 - px(4), W // 2, H // 2 + px(4)], fill=0, width=lw)
    cx = _Ctx(d, dpi, {"boost": 0})
    cx.draw((px(5), px(5), W - px(5), H // 2 - px(5)), f"{tpl['width_mm']:g} × {tpl['height_mm']:g} mm · {dpi} dpi",
            {**_BASE_STYLE, "align": "center"})
    cx.draw((px(5), H // 2 + px(5), W - px(5), H - px(5)), "Çerçeve kenara tam oturmalı · cetvel 1 mm",
            {**_BASE_STYLE, "bold": False, "align": "center"})
    return img.point(lambda v: 0 if v < 150 else 255)


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
