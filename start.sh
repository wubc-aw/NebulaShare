#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# activate venv if exists
if [ -d "$DIR/venv" ]; then
    source "$DIR/venv/bin/activate"
fi

# ensure dependencies
pip install -q flask 'qrcode[pil]' netifaces speedtest-cli 2>/dev/null || pip3 install -q flask 'qrcode[pil]' netifaces speedtest-cli

echo "Starting NebulaShare Server..."
exec python3 "$DIR/app.py"
