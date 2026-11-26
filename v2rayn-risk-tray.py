#!/usr/bin/python3
"""Small GTK tray companion for v2rayN exit-IP and Scamalytics checks."""

import html
import ipaddress
import argparse
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import ctypes
import ctypes.util

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GdkPixbuf


def _gtk_pointer(widget):
    """Get the underlying GtkWidget pointer for the C AppIndicator API."""
    capsule = getattr(widget, "__gpointer__", None)
    if capsule is None:
        return None
    get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    get_pointer.restype = ctypes.c_void_p
    return get_pointer(capsule, None)


def _new_appindicator(menu):
    """Create a visible Ubuntu tray indicator without requiring GI bindings."""
    library = ctypes.util.find_library("ayatana-appindicator3")
    if not library:
        return None
    try:
        api = ctypes.CDLL(library)
        api.app_indicator_new.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        api.app_indicator_new.restype = ctypes.c_void_p
        api.app_indicator_set_status.argtypes = [ctypes.c_void_p, ctypes.c_int]
        api.app_indicator_set_menu.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        indicator = api.app_indicator_new(b"v2rayn-risk", b"network-transmit-receive", 0)
        menu_ptr = _gtk_pointer(menu)
        if not indicator or not menu_ptr:
            return None
        api.app_indicator_set_menu(indicator, menu_ptr)
        api.app_indicator_set_status(indicator, 1)  # ACTIVE
        return api, indicator
    except Exception:
        return None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROXY = os.environ.get("V2RAYN_PROXY", "http://127.0.0.1:10809")
IP_URL = "https://api.ipify.org"


def bool_value(value):
    return value.strip().lower() in {"yes", "true", "1"}


def parse_scamalytics(page):
    score = re.search(r"Fraud Score:\s*(\d+)", page, re.I)
    values = {}
    for label, cell in re.findall(
        r"<th(?:\s[^>]*)?>\s*([^<]+?)\s*</th>\s*<td[^>]*>(.*?)</td>", page, re.I | re.S
    ):
        text = re.sub(r"<[^>]+>", " ", cell)
        values[re.sub(r"\s+", " ", html.unescape(label)).strip()] = re.sub(r"\s+", " ", text).strip()
    for label, value in re.findall(
        r"<th(?:\s[^>]*)?>\s*([^<]+?)\s*</th>\s*<td[^>]*>.*?<div[^>]*>\s*([^<]+?)\s*</div>",
        page,
        re.I | re.S,
    ):
        values[re.sub(r"\s+", " ", html.unescape(label)).strip()] = value.strip()
    return {
        "score": int(score.group(1)) if score else None,
        "vpn": bool_value(values.get("Anonymizing VPN", "")),
        "residential_proxy": bool_value(values.get("Residential Proxy", "")),
        "datacenter": bool_value(values.get("Datacenter", values.get("Server", ""))),
        "country": values.get("Country Name", values.get("Country", "")),
        "isp": values.get("ISP Name", values.get("Organization Name", values.get("ISP", ""))),
    }


def fetch(url, proxy=None):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": "v2rayn-risk-tray/1.0"})
    with opener.open(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def check_ip(ip, proxy=None):
    ipaddress.ip_address(ip)
    page = fetch("https://scamalytics.com/ip/" + urllib.parse.quote(ip), proxy)
    return parse_scamalytics(page)


def _score_color(score):
    if score is None:
        return "#9aa0a6"
    if score <= 20:
        return "#34a853"
    if score <= 50:
        return "#f9ab00"
    return "#ea4335"


def _bool_badge(label, value):
    state = "Yes" if value else "No"
    marker = "🔴" if value else "🟢"
    return f"{marker} {label}: {state}"


def _score_badge(score):
    if score is None:
        return "⚪ Fraud score: ?"
    marker = "🟢" if score <= 20 else "🟠" if score <= 50 else "🔴"
    return f"{marker} Fraud score: {score}"


def _menu_label_item(markup):
    item = Gtk.MenuItem()
    label = Gtk.Label()
    label.set_markup(markup)
    label.set_xalign(0.0)
    item.add(label)
    item._risk_label = label
    return item


class RiskTray:
    def __init__(self):
        self.current_ip = None
        self.status = "Starting..."
        self.menu = Gtk.Menu()
        self.build_menu()
        # AppIndicator is rendered by GNOME's AppIndicators extension; StatusIcon
        # is retained as a fallback for desktops that still support legacy trays.
        self.appindicator = _new_appindicator(self.menu)
        if self.appindicator:
            self.indicator = None
        else:
            self.indicator = Gtk.StatusIcon.new_from_icon_name("network-transmit-receive")
            self.indicator.set_title("v2rayN Risk")
            self.indicator.set_tooltip_text("v2rayN Risk: checking exit IP")
            self.indicator.connect("popup-menu", self.on_popup)
            self.indicator.connect("activate", self.on_activate)
        GLib.idle_add(self.refresh_exit_ip)

    def build_menu(self):
        self.menu = Gtk.Menu()
        self.ip_item = _menu_label_item("Exit IP: checking...")
        self.menu.append(self.ip_item)
        self.risk_item = _menu_label_item("Risk: not checked")
        self.menu.append(self.risk_item)
        self.menu.append(Gtk.SeparatorMenuItem())
        refresh = Gtk.MenuItem(label="Refresh exit IP")
        refresh.connect("activate", lambda *_: self.refresh_exit_ip())
        self.menu.append(refresh)
        lookup = Gtk.MenuItem(label="Check an IP...")
        lookup.connect("activate", lambda *_: self.show_lookup())
        self.menu.append(lookup)
        self.menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        self.menu.append(quit_item)
        self.menu.show_all()

    def on_popup(self, _icon, button, activate_time):
        self.menu.popup(None, None, Gtk.StatusIcon.position_menu, self.indicator, button, activate_time)

    def on_activate(self, *_):
        self.show_lookup()

    def refresh_exit_ip(self):
        self.status = "Checking exit IP..."
        self.ip_item._risk_label.set_markup("<b>Exit IP:</b> checking...")
        threading.Thread(target=self._refresh_worker, daemon=True).start()
        return False

    def _refresh_worker(self):
        try:
            ip = fetch(IP_URL, DEFAULT_PROXY).strip()
            result = check_ip(ip)
            GLib.idle_add(self.show_result, ip, result)
        except Exception as exc:
            GLib.idle_add(self.show_error, str(exc))

    def show_result(self, ip, result):
        self.current_ip = ip
        score = result.get("score")
        self.ip_item._risk_label.set_text(f"Exit IP: {ip}")
        self.risk_item._risk_label.set_text(
            " | ".join(
                [
                    _score_badge(score),
                    _bool_badge("VPN", result["vpn"]),
                    _bool_badge("Datacenter", result["datacenter"]),
                    _bool_badge("Residential proxy", result["residential_proxy"]),
                ]
            )
        )
        if self.indicator:
            self.indicator.set_tooltip_text(f"Exit IP: {ip} | Fraud score: {score if score is not None else '?'}")
        return False

    def show_error(self, message):
        self.ip_item._risk_label.set_markup("<b>Exit IP:</b> unavailable")
        self.risk_item._risk_label.set_markup(
            f'<span foreground="#ea4335"><b>Error:</b> {html.escape(message[:90])}</span>'
        )
        if self.indicator:
            self.indicator.set_tooltip_text("v2rayN Risk: check failed")
        return False

    def show_lookup(self):
        dialog = Gtk.Dialog(title="Check Scamalytics IP", flags=Gtk.DialogFlags.MODAL)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Check", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        box.add(Gtk.Label(label="IP address (leave blank to use the current exit IP):"))
        entry = Gtk.Entry()
        entry.set_text(self.current_ip or "")
        box.add(entry)
        dialog.show_all()
        response = dialog.run()
        ip = entry.get_text().strip()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and ip:
            threading.Thread(target=self._lookup_worker, args=(ip,), daemon=True).start()

    def _lookup_worker(self, ip):
        try:
            result = check_ip(ip)
            GLib.idle_add(self.show_lookup_result, ip, result)
        except Exception as exc:
            GLib.idle_add(self.show_error, str(exc))

    def show_lookup_result(self, ip, result):
        score = result.get("score")
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"Scamalytics: {ip}",
        )
        dialog.format_secondary_text(
            f"Fraud score: {score if score is not None else 'unknown'}\n"
            f"Datacenter (Server): {'Yes' if result['datacenter'] else 'No'}\n"
            f"Residential proxy: {'Yes' if result['residential_proxy'] else 'No'}\n"
            f"VPN: {'Yes' if result['vpn'] else 'No'}\n"
            f"Country: {result['country'] or 'unknown'}\n"
            f"ISP/Organization: {result['isp'] or 'unknown'}"
        )
        dialog.run()
        dialog.destroy()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit-ip", action="store_true")
    parser.add_argument("--check")
    args = parser.parse_args()
    if args.exit_ip or args.check:
        try:
            ip = args.check or fetch(IP_URL, DEFAULT_PROXY).strip()
            result = check_ip(ip)
            print(json.dumps({"ip": ip, **result}))
        except Exception as exc:
            print(json.dumps({"error": str(exc)}))
        raise SystemExit(0)
    RiskTray()
    Gtk.main()
