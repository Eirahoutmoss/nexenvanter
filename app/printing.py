"""Yazıcı adaptörleri ve yazıcı profilleri.

Etiket, yazıcının gerçek çözünürlüğünde (DPI) yeniden çizilir ve piksel piksel gönderilir: ölçekleme yoktur,
bu yüzden ince çizgiler/yazılar kaybolmaz. Profil (yazıcı başına) kağıt boyutunu, döndürmeyi, sığdırmayı ve
ofseti belirler; sürücünün listesinde etiket boyutu yoksa özel boyut veya "sığdır" kullanılır.
Yeni marka/model eklemek için PrinterAdapter alt sınıfı yazıp ADAPTERS'a kaydetmek yeterli."""
import sys

from . import db

DEFAULT_PROFILE = {
    "paper": "custom",      # custom: etiket ölçüsünü sürücüye özel kağıt olarak gönder | driver: sürücüdeki mevcut kağıt | form:<ad>
    "rotate": "auto",       # auto | 0 | 90 | 180 | 270
    "fit": "fit",           # fit: yazdırılabilir alana orantılı sığdır | actual: birebir (taşarsa kırpılır)
    "offset_x_mm": 0.0, "offset_y_mm": 0.0,
    "tape_mm": 0,           # şerit yazıcı (Brother PT): şerit genişliği; 0 = kullanılmıyor
}


class PrinterError(Exception):
    pass


def get_profile(printer: str) -> dict:
    p = dict(DEFAULT_PROFILE)
    p.update((db.get_setting("printer_profiles") or {}).get(printer) or {})
    return p


def save_profile(printer: str, data: dict) -> dict:
    allp = db.get_setting("printer_profiles") or {}
    p = get_profile(printer)
    for k in DEFAULT_PROFILE:
        if k in data:
            p[k] = data[k]
    if str(p["rotate"]) not in ("auto", "0", "90", "180", "270"):
        raise ValueError("Geçersiz döndürme")
    if p["fit"] not in ("fit", "actual"):
        raise ValueError("Geçersiz sığdırma")
    for k in ("offset_x_mm", "offset_y_mm", "tape_mm"):
        p[k] = float(p[k] or 0)
    allp[printer] = p
    db.set_setting("printer_profiles", allp)
    return p


class PrinterAdapter:
    id = "base"
    name = "Temel"

    def available(self) -> bool:
        return False

    def list_printers(self) -> list[dict]:
        return []

    def status(self, printer: str) -> dict:
        return {"ok": True, "message": "Bilinmiyor"}

    def info(self, printer: str) -> dict:
        return {}

    def print_labels(self, printer: str, render, width_mm: float, height_mm: float, count: int, copies: int = 1,
                     profile: dict | None = None) -> None:
        """render(index, dpi) → PIL görüntüsü. Adaptör DPI'ı yazıcıdan öğrenip çizdirir."""
        raise NotImplementedError


def _plan(img_w_mm, img_h_mm, area_w_mm, area_h_mm, profile):
    """Döndürme ve ölçeği belirle → (rotate_deg, scale)."""
    rot = str(profile.get("rotate", "auto"))
    if rot == "auto":
        fits0 = min(area_w_mm / img_w_mm, area_h_mm / img_h_mm)
        fits90 = min(area_w_mm / img_h_mm, area_h_mm / img_w_mm)
        rot = "90" if fits90 > fits0 * 1.05 else "0"
    r = int(rot)
    w, h = (img_h_mm, img_w_mm) if r in (90, 270) else (img_w_mm, img_h_mm)
    scale = 1.0
    if profile.get("fit", "fit") == "fit":
        scale = min(1.0, area_w_mm / w, area_h_mm / h) if area_w_mm > 0 and area_h_mm > 0 else 1.0
    return r, scale


class WindowsSpoolerAdapter(PrinterAdapter):
    """Windows yazdırma kuyruğu (GDI). Brother PT-P900Wc dahil üretici sürücüsü olan her yazıcı."""
    id = "windows"
    name = "Windows yazıcı sürücüsü"

    def available(self):
        if sys.platform != "win32":
            return False
        try:
            import win32print  # noqa: F401
            return True
        except ImportError:
            return False

    def list_printers(self):
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        default = ""
        try:
            default = win32print.GetDefaultPrinter()
        except Exception:
            pass
        return [{"name": p[2], "default": p[2] == default} for p in win32print.EnumPrinters(flags, None, 1)]

    def status(self, printer):
        import win32print
        try:
            h = win32print.OpenPrinter(printer)
            try:
                info = win32print.GetPrinter(h, 2)
            finally:
                win32print.ClosePrinter(h)
        except Exception as e:
            return {"ok": False, "message": f"Yazıcı açılamadı: {e}"}
        offline = bool(info["Attributes"] & 0x400) or bool(info["Status"] & 0x80)
        return {"ok": not offline and info["Status"] == 0, "status_code": info["Status"], "jobs": info["cJobs"],
                "message": "Çevrimdışı" if offline else ("Hazır" if info["Status"] == 0 else f"Durum kodu {info['Status']}")}

    def _devmode(self, printer, width_mm, height_mm, profile):
        import win32con
        import win32print
        h = win32print.OpenPrinter(printer)
        try:
            pinfo = win32print.GetPrinter(h, 2)
        finally:
            win32print.ClosePrinter(h)
        dm = pinfo["pDevMode"]
        paper = profile.get("paper", "custom")
        if paper == "custom":
            w, l = width_mm, height_mm
            if profile.get("tape_mm"):
                # Şerit yazıcı: kağıt genişliği = şerit, uzunluk = etiketin uzun kenarı
                w, l = float(profile["tape_mm"]), max(width_mm, height_mm)
            short, long_ = sorted((w, l))
            dm.PaperSize = 256  # DMPAPER_USER
            dm.PaperWidth = int(round(short * 10))
            dm.PaperLength = int(round(long_ * 10))
            dm.Orientation = 2 if width_mm > height_mm else 1  # yatay etiket: sürücü uzun kenarı yatay alır
            dm.Fields |= win32con.DM_PAPERSIZE | win32con.DM_PAPERWIDTH | win32con.DM_PAPERLENGTH | win32con.DM_ORIENTATION
        elif paper.startswith("form:"):
            name = paper[5:]
            for nm in self._papers(printer, pinfo["pPortName"]):
                if nm["name"] == name:
                    dm.PaperSize = nm["id"]
                    dm.Fields |= win32con.DM_PAPERSIZE
                    try:
                        dm.FormName = name
                        dm.Fields |= win32con.DM_FORMNAME
                    except Exception:
                        pass
                    break
        return dm, pinfo

    def _papers(self, printer, port):
        import win32print
        DC_PAPERS, DC_PAPERNAMES, DC_PAPERSIZE = 2, 16, 3
        try:
            ids = win32print.DeviceCapabilities(printer, port, DC_PAPERS)
            names = win32print.DeviceCapabilities(printer, port, DC_PAPERNAMES)
            sizes = win32print.DeviceCapabilities(printer, port, DC_PAPERSIZE)
        except Exception:
            return []
        out = []
        for i, pid in enumerate(ids):
            sz = sizes[i] if i < len(sizes) else {"x": 0, "y": 0}
            sx, sy = (sz["x"], sz["y"]) if isinstance(sz, dict) else (sz[0], sz[1])
            out.append({"id": int(pid), "name": str(names[i]).strip("\x00 ") if i < len(names) else str(pid),
                        "w_mm": round(sx / 10, 1), "h_mm": round(sy / 10, 1)})
        return out

    def _open_dc(self, printer, dm):
        import win32gui
        import win32ui
        hdc = win32gui.CreateDC("WINSPOOL", printer, dm)
        return win32ui.CreateDCFromHandle(hdc)

    @staticmethod
    def _caps(dc):
        import win32con
        g = dc.GetDeviceCaps
        dx, dy = g(win32con.LOGPIXELSX), g(win32con.LOGPIXELSY)
        return {"dpi_x": dx, "dpi_y": dy, "printable_px": (g(win32con.HORZRES), g(win32con.VERTRES)),
                "physical_px": (g(win32con.PHYSICALWIDTH), g(win32con.PHYSICALHEIGHT)),
                "offset_px": (g(win32con.PHYSICALOFFSETX), g(win32con.PHYSICALOFFSETY)),
                "printable_mm": (round(g(win32con.HORZRES) * 25.4 / dx, 1), round(g(win32con.VERTRES) * 25.4 / dy, 1)),
                "physical_mm": (round(g(win32con.PHYSICALWIDTH) * 25.4 / dx, 1), round(g(win32con.PHYSICALHEIGHT) * 25.4 / dy, 1))}

    def info(self, printer, width_mm=None, height_mm=None, profile=None):
        """Sürücü raporu: kağıt listesi, mevcut ve profil uygulanmış yazdırılabilir alan, DPI."""
        import win32print
        try:
            h = win32print.OpenPrinter(printer)
            try:
                pinfo = win32print.GetPrinter(h, 2)
            finally:
                win32print.ClosePrinter(h)
            out = {"driver": pinfo.get("pDriverName"), "port": pinfo.get("pPortName"),
                   "papers": self._papers(printer, pinfo["pPortName"])}
            dc = self._open_dc(printer, pinfo["pDevMode"])
            try:
                out["current"] = self._caps(dc)
                dmc = pinfo["pDevMode"]
                out["current"]["paper_name"] = getattr(dmc, "FormName", "") or ""
            finally:
                dc.DeleteDC()
            if width_mm and profile:
                dm, _ = self._devmode(printer, width_mm, height_mm, profile)
                dc = self._open_dc(printer, dm)
                try:
                    c = self._caps(dc)
                finally:
                    dc.DeleteDC()
                rot, scale = _plan(width_mm, height_mm, *c["printable_mm"], profile)
                out["with_profile"] = {**c, "rotate": rot, "scale": round(scale, 3),
                                       "accepted_custom": abs(c["physical_mm"][0] - min(width_mm, height_mm)) < 2
                                       or abs(c["physical_mm"][1] - max(width_mm, height_mm)) < 2}
            return out
        except Exception as e:
            raise PrinterError(f"Sürücü bilgisi alınamadı: {e}")

    def add_form(self, name, width_mm, height_mm):
        """Windows'a özel kağıt formu ekle (Yazdırma sunucusu özellikleri). Yönetici yetkisi gerekebilir."""
        import win32print
        form = {"Flags": 0, "Name": name, "Size": {"cx": int(width_mm * 1000), "cy": int(height_mm * 1000)},
                "ImageableArea": {"left": 0, "top": 0, "right": int(width_mm * 1000), "bottom": int(height_mm * 1000)}}
        try:
            h = win32print.OpenPrinter(None, {"DesiredAccess": win32print.SERVER_ACCESS_ADMINISTER})
        except Exception as e:
            raise PrinterError(f"Yazdırma sunucusu açılamadı (programı yönetici olarak ya da hizmet olarak çalıştırın): {e}")
        try:
            try:
                win32print.AddForm(h, form)
            except Exception:
                win32print.SetForm(h, name, form)
        except Exception as e:
            raise PrinterError(f"Form eklenemedi: {e}")
        finally:
            win32print.ClosePrinter(h)

    def print_labels(self, printer, render, width_mm, height_mm, count, copies=1, profile=None):
        from PIL import Image, ImageWin
        profile = profile or DEFAULT_PROFILE
        try:
            dm, _ = self._devmode(printer, width_mm, height_mm, profile)
            dc = self._open_dc(printer, dm)
        except Exception as e:
            raise PrinterError(f"Yazıcıya bağlanılamadı: {e}")
        try:
            c = self._caps(dc)
            pw, ph = c["printable_px"]
            rot, scale = _plan(width_mm, height_mm, *c["printable_mm"], profile)
            dpi = c["dpi_x"]
            ox = int(float(profile.get("offset_x_mm") or 0) * dpi / 25.4)
            oy = int(float(profile.get("offset_y_mm") or 0) * c["dpi_y"] / 25.4)
            dc.StartDoc("NexEnvanter etiket")
            for i in range(count):
                # Ölçek etiketi küçültmeyle değil, daha düşük DPI'da yeniden çizerek uygulanır (keskinlik korunur)
                img = render(i, max(72, int(round(dpi * scale))))
                if rot:
                    img = img.rotate(-rot, expand=True)  # saat yönünde
                if c["dpi_y"] != c["dpi_x"]:  # ör. 360×720 yüksek çözünürlük
                    img = img.resize((img.size[0], int(img.size[1] * c["dpi_y"] / c["dpi_x"])), Image.NEAREST)
                rgb = img.convert("RGB")
                w, h = rgb.size
                x = max(0, (pw - w) // 2) + ox
                y = max(0, (ph - h) // 2) + oy
                for _ in range(max(1, copies)):
                    dc.StartPage()
                    ImageWin.Dib(rgb).draw(dc.GetHandleOutput(), (x, y, x + w, y + h))  # 1:1, ölçeksiz
                    dc.EndPage()
            dc.EndDoc()
        except Exception as e:
            try:
                dc.AbortDoc()
            except Exception:
                pass
            raise PrinterError(f"Yazdırma hatası: {e}")
        finally:
            dc.DeleteDC()


# Sıra önemli: ilk uygun adaptör varsayılan olur. PDF çıktısı her zaman API üzerinden ayrıca mevcuttur.
ADAPTERS: dict[str, PrinterAdapter] = {a.id: a for a in (WindowsSpoolerAdapter(),)}


def available_adapters():
    return [a for a in ADAPTERS.values() if a.available()]


def all_printers() -> list[dict]:
    out = []
    for a in available_adapters():
        try:
            out += [{**p, "adapter": a.id} for p in a.list_printers()]
        except Exception as e:
            out.append({"name": f"({a.name} hatası: {e})", "adapter": a.id, "error": True})
    return out
