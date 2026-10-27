"""NexEnvanter giriş noktası: veri klasörü, veritabanı, arka plan işleri, web sunucusu, tepsi simgesi, Windows hizmeti."""
import argparse
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

if sys.stdout is None:  # pencereli (--noconsole) derlemede
    sys.stdout = sys.stderr = open(os.devnull, "w")

log = logging.getLogger("nexenvanter")
TASK_NAME = "NexEnvanter"


def msgbox(text, title="NexEnvanter", error=False):
    print(text)
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)


def _setup_logging(data_dir):
    d = data_dir / "logs"
    d.mkdir(exist_ok=True)
    h = logging.handlers.RotatingFileHandler(d / "nexenvanter.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)
    if sys.stdout and sys.stdout.name != os.devnull:
        root.addHandler(logging.StreamHandler(sys.stdout))


def _port_busy(port) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _schtasks(*args):
    r = subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=0x08000000)
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()


def install_service(port, data_dir):
    exe = sys.executable
    tr = f'"{exe}" --headless --port {port} --data "{data_dir}"'
    ok, out = _schtasks("/Create", "/F", "/TN", TASK_NAME, "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/TR", tr)
    if not ok:
        msgbox(f"Hizmet kurulamadı. Programı 'Yönetici olarak çalıştır' ile açıp tekrar deneyin.\n\n{out}", error=True)
        return
    subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={TASK_NAME}", "dir=in", "action=allow",
                    "protocol=TCP", f"localport={port}"], capture_output=True, creationflags=0x08000000)
    _schtasks("/Run", "/TN", TASK_NAME)
    msgbox(f"NexEnvanter arka plan hizmeti olarak kuruldu.\nBilgisayar açıldığında oturum açılmasa da çalışır.\n"
           f"Port: {port}\nVeri: {data_dir}")


def uninstall_service():
    _schtasks("/End", "/TN", TASK_NAME)
    ok, out = _schtasks("/Delete", "/F", "/TN", TASK_NAME)
    msgbox("Hizmet kaldırıldı." if ok else f"Hizmet kaldırılamadı (yönetici gerekir):\n{out}", error=not ok)


def service_installed() -> bool:
    return sys.platform == "win32" and _schtasks("/Query", "/TN", TASK_NAME)[0]


def _tray_image():
    from PIL import Image, ImageDraw
    s = 64
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=12, fill=(10, 20, 48, 255))
    pts = [(8, 56), (8, 8), (20, 8), (44, 38), (44, 8), (56, 8), (56, 56), (44, 56), (20, 26), (20, 56)]
    d.polygon(pts, fill=(47, 123, 255, 255))
    return img


def run_tray(url_local, server=None, controller=False):
    """Tepsi simgesi. controller=True: sunucu zaten (hizmet olarak) çalışıyor, bu süreç yalnızca kısayol sunar."""
    import pystray
    from .paths import DIRS

    def open_ui(*_):
        webbrowser.open(url_local)

    def backup(*_):
        try:
            if controller:
                raise RuntimeError("Hizmet modunda yedeği arayüzden alın")
            from . import db
            msgbox("Yedek alındı: " + db.backup("manual"))
        except Exception as e:
            msgbox(str(e), error=True)

    def open_data(*_):
        os.startfile(str(DIRS.data)) if sys.platform == "win32" else None

    def svc(*_):
        if service_installed():
            uninstall_service()
        else:
            from .api import app
            install_service(app.state.port, DIRS.data)

    def quit_(icon, *_):
        icon.stop()
        if server:
            server.should_exit = True

    menu = pystray.Menu(
        pystray.MenuItem("NexEnvanter'i aç", open_ui, default=True),
        pystray.MenuItem("Şimdi yedekle", backup, enabled=not controller),
        pystray.MenuItem("Veri klasörü", open_data),
        pystray.MenuItem(lambda _: "Hizmeti kaldır" if service_installed() else "Arka plan hizmeti olarak kur", svc,
                         enabled=not controller or service_installed()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Çıkış" if not controller else "Simgeyi kapat", quit_),
    )
    pystray.Icon("NexEnvanter", _tray_image(), "NexEnvanter", menu).run()


def main():
    from . import APP_NAME, AUTHOR, VERSION
    from .paths import DIRS, FROZEN

    p = argparse.ArgumentParser(prog=APP_NAME)
    p.add_argument("--host", default="0.0.0.0", help="Dinlenecek adres (varsayılan: tüm ağ arayüzleri)")
    p.add_argument("--port", type=int, default=8750)
    p.add_argument("--data", help="Veri klasörü")
    p.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    p.add_argument("--headless", action="store_true", help="Tepsi simgesi ve tarayıcı olmadan çalış (hizmet modu)")
    p.add_argument("--tray", action="store_true", help="Tepsi simgesiyle çalış")
    p.add_argument("--firewall", action="store_true", help="Windows güvenlik duvarında portu aç (yönetici gerekir)")
    p.add_argument("--install-service", action="store_true", help="Açılışta oturumsuz çalışan arka plan hizmeti kur (yönetici)")
    p.add_argument("--uninstall-service", action="store_true", help="Arka plan hizmetini kaldır (yönetici)")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    args = p.parse_args()

    DIRS.init(args.data)
    _setup_logging(DIRS.data)
    if args.install_service:
        return install_service(args.port, DIRS.data)
    if args.uninstall_service:
        return uninstall_service()

    want_tray = (args.tray or (FROZEN and sys.platform == "win32")) and not args.headless
    try:
        import pystray  # noqa: F401
    except Exception:
        want_tray = False
    scheme_guess = "http"
    url_local = f"{scheme_guess}://127.0.0.1:{args.port}"

    if _port_busy(args.port):
        # Büyük olasılıkla hizmet olarak zaten çalışıyor: yeni sunucu açma, arayüzü göster
        for sch in ("https", "http"):
            try:
                import ssl
                ctx = ssl._create_unverified_context()
                urllib.request.urlopen(f"{sch}://127.0.0.1:{args.port}/api/state", timeout=2, context=ctx)
                url_local = f"{sch}://127.0.0.1:{args.port}"
                break
            except Exception:
                continue
        else:
            return msgbox(f"Port {args.port} başka bir program tarafından kullanılıyor. --port ile başka port seçin.", error=True)
        if not args.headless:
            webbrowser.open(url_local)
            if want_tray:
                run_tray(url_local, controller=True)
        return

    from . import api, db, network, tls
    db.init()
    db.backup_loop()
    network.scheduler()
    api.app.state.port = args.port

    ssl_kw = {}
    if (db.get_setting("tls") or {}).get("enabled") and tls.available():
        c, k = tls.paths()
        ssl_kw = {"ssl_certfile": str(c), "ssl_keyfile": str(k)}
        api.app.state.scheme = "https"
        url_local = f"https://127.0.0.1:{args.port}"

    if args.firewall and sys.platform == "win32":
        r = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={APP_NAME}", "dir=in",
                            "action=allow", "protocol=TCP", f"localport={args.port}"], capture_output=True, text=True,
                           creationflags=0x08000000)
        msgbox("Güvenlik duvarı kuralı " + ("eklendi" if r.returncode == 0 else "eklenemedi (yönetici olarak çalıştırın)"))

    import uvicorn
    cfg = uvicorn.Config(api.app, host=args.host, port=args.port, log_level="warning", access_log=False, log_config=None, **ssl_kw)
    server = uvicorn.Server(cfg)
    api.app.state.shutdown = lambda: setattr(server, "should_exit", True)

    log.info("%s %s (%s) başlıyor — yerel %s, ağ %s, veri %s", APP_NAME, VERSION, AUTHOR, url_local, api.base_url(), DIRS.data)
    print("=" * 60)
    print(f"  {APP_NAME} {VERSION}  —  {AUTHOR}")
    print(f"  Bu bilgisayar : {url_local}")
    print(f"  Ağdaki adres  : {api.base_url()}")
    print(f"  Veri klasörü  : {DIRS.data}")
    print("=" * 60)
    if not args.no_browser and not args.headless:
        threading.Timer(1.5, lambda: webbrowser.open(url_local)).start()

    if want_tray:
        th = threading.Thread(target=server.run, daemon=True, name="server")
        th.start()
        time.sleep(0.5)
        run_tray(url_local, server)
        server.should_exit = True
        th.join(timeout=10)
    else:
        try:
            server.run()
        except OSError as e:
            msgbox(f"Sunucu başlatılamadı ({e}). Port {args.port} kullanımda olabilir.", error=True)


if __name__ == "__main__":
    main()
