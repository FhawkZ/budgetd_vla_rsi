#!/usr/bin/env bash
# Ubuntu 22.04 x86_64 user-space libraries; no sudo and no driver replacement.
set -euo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p "$RSI_SOFTWARE_ROOT/system-packages" "$RSI_SOFTWARE_ROOT/system"
cd "$RSI_SOFTWARE_ROOT/system-packages"
apt-get download libvulkan1=1.3.204.1-2 vulkan-tools=1.3.204.0+dfsg1-1 libegl1=1.4.0-1 libglvnd0=1.4.0-1 libglx0=1.4.0-1 libgl1=1.4.0-1
"$RSI_SOFTWARE_ROOT/python/cpython-3.12.15-linux-x86_64-gnu/bin/python" - <<'CHECK'
import json,hashlib,os
from pathlib import Path
root=Path(os.environ['RSI_CODE_ROOT'])
for row in json.loads((root/'configs/system-packages.json').read_text()):
 p=Path(row['file']);assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],p
CHECK
for package in *.deb; do dpkg-deb -x "$package" "$RSI_SOFTWARE_ROOT/system"; done
