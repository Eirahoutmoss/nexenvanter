"""NexEnvanter giriş noktası: veri klasörü, veritabanı, yedek döngüsü, web sunucusu."""
import argparse
import logging
import os
import subprocess
import sys
import threading
import webbrowser

if sys.stdout is None:  # --noconsole derlemede
    sys.stdout = sys.stderr = open(os.devnull, "w")


def main():
    from . import APP_NAME, AUTHOR, VERSION
    from .paths import DIRS

    p = argparse.ArgumentParser(prog=APP_NAME)
    p.add_argument("--host", default="0.0.0.0", help="Dinlenecek adres (varsayılan: tüm ağ arayüzleri)")
    p.add_argument("--port", type=int, default=8750)
    p.add_argument("--data", help="Veri klasörü")
    p.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    p.add_argument("--firewall", action="store_true", help="Windows güvenlik duvarında portu aç (yönetici gerekir)")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    args = p.parse_args()

    DIRS.init(args.data)
    from . import api, db
    db.init()
    db.backup_loop()
    api.app.state.port = args.port

    if args.firewall and sys.platform == "win32":
        r = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={APP_NAME}", "dir=in",
                            "action=allow", "protocol=TCP", f"localport={args.port}"], capture_output=True, text=True)
        print("Güvenlik duvarı kuralı:", "eklendi" if r.returncode == 0 else "eklenemedi (yönetici olarak çalıştırın)")

    import uvicorn
    cfg = uvicorn.Config(api.app, host=args.host, port=args.port, log_level="warning", access_log=False,
                         log_config=None)
    server = uvicorn.Server(cfg)

    def shutdown():
        server.should_exit = True
    api.app.state.shutdown = shutdown

    url_local = f"http://127.0.0.1:{args.port}"
    print("=" * 60)
    print(f"  {APP_NAME} {VERSION}  —  {AUTHOR}")
    print(f"  Bu bilgisayar : {url_local}")
    print(f"  Ağdaki adres  : {api.base_url()}")
    print(f"  Veri klasörü  : {DIRS.data}")
    print("  Kapatmak için bu pencereyi kapatın veya Ctrl+C")
    print("=" * 60)
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url_local)).start()
    logging.basicConfig(level=logging.WARNING)
    try:
        server.run()
    except OSError as e:
        print(f"Sunucu başlatılamadı ({e}). Port {args.port} kullanımda olabilir: --port ile başka port seçin.")
        input("Çıkmak için Enter...")


if __name__ == "__main__":
    main()
