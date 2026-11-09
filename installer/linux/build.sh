#!/usr/bin/env bash
# Linux paketi: NexEnvanter-<sürüm>-linux-x64.tar.gz  (Linux'ta çalıştırın; Python 3.12+ gerekir)
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m venv .venv-linux && . .venv-linux/bin/activate
pip install -q -r requirements-dev.txt
python -m pytest -q
pyinstaller NexEnvanter.spec --noconfirm --clean
V=$(python -c "import re;print(re.search(r'VERSION = \"([^\"]+)\"', open('app/__init__.py',encoding='utf-8').read()).group(1))")
D="dist/NexEnvanter-$V-linux-x64"; rm -rf "$D"; mkdir -p "$D"
cp dist/NexEnvanter "$D/nexenvanter"; cp installer/linux/install.sh "$D/install.sh"; cp README.md "$D/"
tar -C dist -czf "dist/NexEnvanter-$V-linux-x64.tar.gz" "NexEnvanter-$V-linux-x64"
echo "Hazır: dist/NexEnvanter-$V-linux-x64.tar.gz"
