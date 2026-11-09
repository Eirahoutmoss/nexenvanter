#!/usr/bin/env bash
# NexEnvanter Linux kurulumu (systemd). Kullanım:
#   sudo ./install.sh [--port 8750] [--no-firewall]      kur / güncelle (veriler korunur)
#   sudo ./install.sh --uninstall [--purge]              kaldır (--purge: veri klasörünü de sil)
set -euo pipefail

APP=nexenvanter
BIN_DIR=/opt/nexenvanter
DATA_DIR=/var/lib/nexenvanter
UNIT=/etc/systemd/system/nexenvanter.service
PORT=8750; FW=1; UNINSTALL=0; PURGE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift ;;
    --no-firewall) FW=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --purge) PURGE=1 ;;
    -h|--help) sed -n 2,5p "$0"; exit 0 ;;
    *) echo "Bilinmeyen seçenek: $1" >&2; exit 2 ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || { echo "Root yetkisi gerekli: sudo ./install.sh" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd bulunamadı; elle çalıştırın: ./nexenvanter --headless --port $PORT --data DIZIN" >&2; exit 1; }

fw_open()  { if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow "$PORT"/tcp >/dev/null && echo "ufw: $PORT/tcp açıldı";
             elif command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then firewall-cmd --permanent --add-port="$PORT"/tcp >/dev/null && firewall-cmd --reload >/dev/null && echo "firewalld: $PORT/tcp açıldı"; fi; }
fw_close() { local p="$1"; if command -v ufw >/dev/null && ufw status | grep -q active; then ufw delete allow "$p"/tcp >/dev/null 2>&1 || true;
             elif command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then firewall-cmd --permanent --remove-port="$p"/tcp >/dev/null 2>&1 || true; firewall-cmd --reload >/dev/null 2>&1 || true; fi; }

if [ "$UNINSTALL" -eq 1 ]; then
  OLD=$(grep -oP '(?<=--port )\d+' "$UNIT" 2>/dev/null || echo "$PORT")
  systemctl disable --now nexenvanter 2>/dev/null || true
  rm -f "$UNIT"; systemctl daemon-reload
  fw_close "$OLD"
  rm -rf "$BIN_DIR"
  if [ "$PURGE" -eq 1 ]; then rm -rf "$DATA_DIR"; userdel "$APP" 2>/dev/null || true; echo "NexEnvanter ve verileri silindi."
  else echo "NexEnvanter kaldırıldı. Veriler korundu: $DATA_DIR (silmek için --purge)"; fi
  exit 0
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/nexenvanter" ] || { echo "nexenvanter dosyası bu klasörde yok." >&2; exit 1; }
case "$PORT" in ''|*[!0-9]*) echo "Geçersiz port." >&2; exit 2;; esac
[ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || { echo "Port 1024-65535 olmalı." >&2; exit 2; }

# Güncellemede eski hizmet durur; yeni kurulumda port başka programda mı?
systemctl stop nexenvanter 2>/dev/null || true
if (command -v ss >/dev/null) && ss -ltn "sport = :$PORT" | grep -q LISTEN; then
  echo "HATA: $PORT/tcp portu başka bir program tarafından kullanılıyor. --port ile başka bir port seçin. Kurulum yapılmadı." >&2; exit 3
fi

id "$APP" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP"
install -d -m 0755 "$BIN_DIR"
install -m 0755 "$HERE/nexenvanter" "$BIN_DIR/nexenvanter"
install -d -m 0750 -o "$APP" -g "$APP" "$DATA_DIR"

cat > "$UNIT" <<UNITEOF
[Unit]
Description=NexEnvanter envanter yönetimi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP
Group=$APP
ExecStart=$BIN_DIR/nexenvanter --headless --port $PORT --data $DATA_DIR
Restart=on-failure
RestartSec=10
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable --now nexenvanter
[ "$FW" -eq 1 ] && fw_open || true

sleep 2
if systemctl is-active --quiet nexenvanter; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo "NexEnvanter çalışıyor → http://${IP:-SUNUCU}:$PORT   (veri: $DATA_DIR)"
  echo "Günlük: journalctl -u nexenvanter -f   ·   Kaldır: sudo ./install.sh --uninstall"
else
  echo "Hizmet başlamadı. Ayrıntı: journalctl -u nexenvanter -n 50" >&2; exit 4
fi
