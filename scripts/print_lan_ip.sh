#!/usr/bin/env bash
set -euo pipefail
if command -v ipconfig >/dev/null 2>&1; then
  ipconfig getifaddr en0 || true
elif command -v hostname >/dev/null 2>&1; then
  hostname -I | awk '{print $1}'
else
  echo "Please check your LAN IP manually."
fi
