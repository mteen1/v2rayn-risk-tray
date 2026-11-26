#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${V2RAYN_RISK_TRAY_URL:-https://raw.githubusercontent.com/mteen1/v2rayn-risk-tray/main}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/v2rayn-risk-tray"
SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required. Install it with: sudo apt install curl" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR" "$SERVICE_DIR"
curl -fsSL "$REPO_URL/v2rayn-risk-tray.py" -o "$INSTALL_DIR/v2rayn-risk-tray.py"
curl -fsSL "$REPO_URL/systemd/v2rayn-risk-tray.service" \
  | sed "s|@INSTALL_DIR@|$INSTALL_DIR|g" > "$SERVICE_DIR/v2rayn-risk-tray.service"

if command -v apt-get >/dev/null 2>&1; then
  missing=()
  for package in python3-gi gir1.2-gtk-3.0 libayatana-appindicator3-1; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing+=("$package")
  done
  if ((${#missing[@]})); then
    sudo apt-get install -y "${missing[@]}"
  fi
fi

chmod 755 "$INSTALL_DIR/v2rayn-risk-tray.py"
systemctl --user daemon-reload
systemctl --user enable --now v2rayn-risk-tray.service
echo "v2rayN Risk Tray installed and started."
