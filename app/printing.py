"""Yazıcı adaptörleri. Etiket görüntüsü labels.render ile üretilir; adaptör yalnızca gönderir.
Yeni marka/model eklemek için PrinterAdapter alt sınıfı yazıp ADAPTERS'a kaydetmek yeterli."""
import sys


class PrinterError(Exception):
    pass


class PrinterAdapter:
    id = "base"
    name = "Temel"

    def available(self) -> bool:
        return False

    def list_printers(self) -> list[dict]:
        return []

    def status(self, printer: str) -> dict:
        return {"ok": True, "message": "Bilinmiyor"}

    def print_images(self, printer: str, images, width_mm: float, height_mm: float, copies: int = 1) -> None:
        raise NotImplementedError


class WindowsSpoolerAdapter(PrinterAdapter):
    """Windows yazdırma kuyruğu (GDI). Brother PT-P900WC üretici sürücüsüyle çalışır."""
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

    def print_images(self, printer, images, width_mm, height_mm, copies=1):
        import win32con
        import win32gui
        import win32print
        import win32ui
        from PIL import ImageWin

        try:
            h = win32print.OpenPrinter(printer)
            try:
                dm = win32print.GetPrinter(h, 2)["pDevMode"]
            finally:
                win32print.ClosePrinter(h)
            # Özel kağıt: şerit genişliği × etiket uzunluğu (0,1 mm birimi). Sürücü desteklemezse yok sayar.
            short, long_ = sorted((width_mm, height_mm))
            dm.PaperSize = 256  # DMPAPER_USER
            dm.PaperWidth = int(short * 10)
            dm.PaperLength = int(long_ * 10)
            dm.Orientation = 2 if width_mm > height_mm else 1
            dm.Fields |= win32con.DM_PAPERSIZE | win32con.DM_PAPERWIDTH | win32con.DM_PAPERLENGTH | win32con.DM_ORIENTATION
            hdc = win32gui.CreateDC("WINSPOOL", printer, dm)
            dc = win32ui.CreateDCFromHandle(hdc)
        except Exception as e:
            raise PrinterError(f"Yazıcıya bağlanılamadı: {e}")
        try:
            pw, ph = dc.GetDeviceCaps(win32con.HORZRES), dc.GetDeviceCaps(win32con.VERTRES)
            dc.StartDoc("NexEnvanter etiket")
            for img in images:
                for _ in range(max(1, copies)):
                    dc.StartPage()
                    rgb = img.convert("RGB")
                    sc = min(pw / rgb.size[0], ph / rgb.size[1])
                    w, hh = int(rgb.size[0] * sc), int(rgb.size[1] * sc)
                    x, y = (pw - w) // 2, (ph - hh) // 2
                    ImageWin.Dib(rgb).draw(dc.GetHandleOutput(), (x, y, x + w, y + hh))
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
