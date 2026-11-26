# v2rayN Risk Tray

Persistent Linux tray companion for v2rayN. It checks the exit IP through the local v2rayN HTTP proxy and reads Scamalytics fields for fraud score, VPN, datacenter/server, and residential proxy status. Right-click the tray icon to refresh or check another IP.

The app is independent of the v2rayN installation, so v2rayN upgrades do not remove it. Set `V2RAYN_PROXY` if your HTTP proxy is not `http://127.0.0.1:10809`.

## Install on Ubuntu or Debian

Install and start it with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/mteen1/v2rayn-risk-tray/main/install.sh | bash
```

The installer places the app in `~/.local/share/v2rayn-risk-tray`, creates a user systemd service, and starts it automatically on future logins. It installs the GTK and AppIndicator packages when `apt` is available. Ubuntu GNOME needs the **AppIndicator and KStatusNotifierItem Support** extension enabled to display the icon.

The default v2rayN HTTP proxy is `http://127.0.0.1:10809`. For another proxy, set it with:

```bash
systemctl --user edit v2rayn-risk-tray.service
```

Add:

```ini
[Service]
Environment=V2RAYN_PROXY=http://127.0.0.1:10809
```

The tray menu shows the current exit IP, Scamalytics fraud score, VPN, datacenter, and residential proxy fields. `Check an IP...` performs a manual lookup.

## Command-line checks

```bash
/usr/bin/python3 v2rayn-risk-tray.py --exit-ip
/usr/bin/python3 v2rayn-risk-tray.py --check 1.1.1.1
```
