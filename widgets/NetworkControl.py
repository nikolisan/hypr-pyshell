from __future__ import annotations
import sys

import gi

gi.require_version("Gtk", "4.0")

from pathlib import Path

from gi.repository import Gio, GLib, GObject, Gtk, Gdk

from utils._network_helpers import _freq_to_band, _strength_to_icon, _truncate_ssid

_NM_BUS = "org.freedesktop.NetworkManager"
_NM_PATH = "/org/freedesktop/NetworkManager"
_NM_IFACE = "org.freedesktop.NetworkManager"
_NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
_NM_WIRELESS_IFACE = "org.freedesktop.NetworkManager.Device.Wireless"
_NM_AP_IFACE = "org.freedesktop.NetworkManager.AccessPoint"
_NM_SETTINGS_PATH = "/org/freedesktop/NetworkManager/Settings"
_NM_SETTINGS_IFACE = "org.freedesktop.NetworkManager.Settings"
_NM_SETTINGS_CONN_IFACE = "org.freedesktop.NetworkManager.Settings.Connection"
_DEVICE_TYPE_WIFI = 2


class NetworkManagerBackend(GObject.Object):
    __gsignals__ = {
        "wifi-enabled-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "active-connection-changed": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "access-points-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (object, object),
        ),
        "connection-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._nm_proxy: Gio.DBusProxy | None = None
        self._wireless_proxy: Gio.DBusProxy | None = None
        self._settings_proxy: Gio.DBusProxy | None = None
        self._device_path: str | None = None
        self._ap_proxies: dict[str, Gio.DBusProxy] = {}
        self._saved_ssids: dict[str, str] = {}
        self._init_proxies()

    def _init_proxies(self) -> None:
        try:
            self._nm_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                _NM_BUS,
                _NM_PATH,
                _NM_IFACE,
                None,
            )
            self._nm_proxy.connect("g-properties-changed", self._on_nm_props_changed)
            self._settings_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                _NM_BUS,
                _NM_SETTINGS_PATH,
                _NM_SETTINGS_IFACE,
                None,
            )
            self._settings_proxy.connect("g-signal", self._on_settings_signal)
            self._device_path = self._find_wifi_device()
            if not self._device_path:
                print("NetworkManager: no Wi-Fi device found", file=sys.stderr)
                return
            self._wireless_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                _NM_BUS,
                self._device_path,
                _NM_WIRELESS_IFACE,
                None,
            )
            self._wireless_proxy.connect(
                "g-properties-changed", self._on_wireless_props_changed
            )
            self._wireless_proxy.connect("g-signal", self._on_wireless_signal)
            self._refresh_saved_connections()
            self._refresh_access_points()
            self._emit_active_connection()
        except GLib.Error as e:
            print(f"NetworkManager DBus init failed: {e}", file=sys.stderr)

    def _find_wifi_device(self) -> str | None:
        assert self._nm_proxy
        devices_variant = self._nm_proxy.get_cached_property("Devices")
        if devices_variant is None:
            return None
        for dev_path in devices_variant.unpack():
            try:
                dev = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SYSTEM,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    _NM_BUS,
                    dev_path,
                    _NM_DEVICE_IFACE,
                    None,
                )
                dev_type = dev.get_cached_property("DeviceType")
                if dev_type and dev_type.unpack() == _DEVICE_TYPE_WIFI:
                    return dev_path
            except GLib.Error:
                continue
        return None

    def _refresh_saved_connections(self) -> None:
        try:
            settings = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                _NM_BUS,
                _NM_SETTINGS_PATH,
                _NM_SETTINGS_IFACE,
                None,
            )
            result = settings.call_sync(
                "ListConnections", None, Gio.DBusCallFlags.NONE, -1, None
            )
            conn_paths: list[str] = result.unpack()[0]
            self._saved_ssids = {}
            for conn_path in conn_paths:
                try:
                    conn = Gio.DBusProxy.new_for_bus_sync(
                        Gio.BusType.SYSTEM,
                        Gio.DBusProxyFlags.NONE,
                        None,
                        _NM_BUS,
                        conn_path,
                        _NM_SETTINGS_CONN_IFACE,
                        None,
                    )
                    result2 = conn.call_sync(
                        "GetSettings", None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    conn_settings: dict = result2.unpack()[0]
                    wifi_section = conn_settings.get("802-11-wireless", {})
                    ssid_raw = wifi_section.get("ssid")
                    if ssid_raw is not None:
                        ssid = bytes(ssid_raw).decode("utf-8", errors="replace")
                        self._saved_ssids[ssid] = conn_path
                except GLib.Error:
                    continue
        except GLib.Error as e:
            print(
                f"NetworkManager: failed to list saved connections: {e}",
                file=sys.stderr,
            )

    def _get_ap_proxy(self, ap_path: str) -> Gio.DBusProxy:
        if ap_path not in self._ap_proxies:
            self._ap_proxies[ap_path] = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                _NM_BUS,
                ap_path,
                _NM_AP_IFACE,
                None,
            )
        return self._ap_proxies[ap_path]

    def _ap_info(self, ap_path: str) -> dict:
        proxy = self._get_ap_proxy(ap_path)
        ssid_v = proxy.get_cached_property("Ssid")
        ssid = (
            bytes(ssid_v.unpack()).decode("utf-8", errors="replace") if ssid_v else ""
        )
        strength = (
            proxy.get_cached_property("Strength") or GLib.Variant("y", 0)
        ).unpack()
        freq = (
            proxy.get_cached_property("Frequency") or GLib.Variant("u", 2412)
        ).unpack()
        flags = (proxy.get_cached_property("Flags") or GLib.Variant("u", 0)).unpack()
        wpa = (proxy.get_cached_property("WpaFlags") or GLib.Variant("u", 0)).unpack()
        rsn = (proxy.get_cached_property("RsnFlags") or GLib.Variant("u", 0)).unpack()
        secured = bool(flags & 0x1) or bool(wpa) or bool(rsn)
        return {
            "ssid": ssid,
            "strength": int(strength),
            "band": _freq_to_band(int(freq)),
            "secured": secured,
            "object_path": ap_path,
            "saved": ssid in self._saved_ssids,
            "connection_path": self._saved_ssids.get(ssid),
        }

    def _refresh_access_points(self) -> None:
        if not self._wireless_proxy:
            return
        try:
            result = self._wireless_proxy.call_sync(
                "GetAccessPoints", None, Gio.DBusCallFlags.NONE, -1, None
            )
            ap_paths: list[str] = result.unpack()[0]
        except GLib.Error:
            return

        seen: dict[str, dict] = {}
        for path in ap_paths:
            if path in ("/", ""):
                continue
            try:
                info = self._ap_info(path)
            except GLib.Error:
                continue
            ssid = info["ssid"]
            if not ssid:
                continue
            if ssid not in seen or info["strength"] > seen[ssid]["strength"]:
                seen[ssid] = info

        unique = list(seen.values())
        saved = [a for a in unique if a["saved"]]
        available = [a for a in unique if not a["saved"]]
        self.emit("access-points-changed", saved, available)

    def _emit_active_connection(self) -> None:
        if not self._wireless_proxy:
            self.emit("active-connection-changed", None)
            return
        active_v = self._wireless_proxy.get_cached_property("ActiveAccessPoint")
        if active_v is None:
            self.emit("active-connection-changed", None)
            return
        ap_path: str = active_v.unpack()
        if ap_path in ("/", ""):
            self.emit("active-connection-changed", None)
            return
        try:
            self.emit("active-connection-changed", self._ap_info(ap_path))
        except GLib.Error:
            self.emit("active-connection-changed", None)

    def _on_nm_props_changed(
        self, proxy: Gio.DBusProxy, changed: GLib.Variant, invalidated: list[str]
    ) -> None:
        props: dict = changed.unpack()
        if "WirelessEnabled" in props:
            self.emit("wifi-enabled-changed", bool(props["WirelessEnabled"]))
        if "ActiveConnections" in props:
            self._emit_active_connection()

    def _on_wireless_props_changed(
        self, proxy: Gio.DBusProxy, changed: GLib.Variant, invalidated: list[str]
    ) -> None:
        if "ActiveAccessPoint" in changed.unpack():
            self._emit_active_connection()

    def _on_wireless_signal(
        self, proxy: Gio.DBusProxy, sender: str, signal_name: str, params: GLib.Variant
    ) -> None:
        if signal_name == "AccessPointRemoved":
            ap_path: str = params.unpack()[0]
            self._ap_proxies.pop(ap_path, None)
        if signal_name in ("AccessPointAdded", "AccessPointRemoved"):
            self._refresh_access_points()

    def _on_settings_signal(
        self, proxy: Gio.DBusProxy, sender: str, signal_name: str, params: GLib.Variant
    ) -> None:
        if signal_name in ("NewConnection", "ConnectionRemoved"):
            self._refresh_saved_connections()
            self._refresh_access_points()

    def forget_connection(self, connection_path: str) -> None:
        try:
            conn = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                _NM_BUS,
                connection_path,
                _NM_SETTINGS_CONN_IFACE,
                None,
            )
            conn.call_sync("Delete", None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error as e:
            print(f"forget_connection failed: {e}", file=sys.stderr)

    def refresh(self) -> None:
        self.emit("wifi-enabled-changed", self.get_wifi_enabled())
        self._emit_active_connection()
        self._refresh_access_points()

    def get_wifi_enabled(self) -> bool:
        if not self._nm_proxy:
            return False
        v = self._nm_proxy.get_cached_property("WirelessEnabled")
        return bool(v.unpack()) if v else False

    def set_wifi_enabled(self, enabled: bool) -> None:
        if not self._nm_proxy:
            return
        self._nm_proxy.call(
            "org.freedesktop.DBus.Properties.Set",
            GLib.Variant(
                "(ssv)", (_NM_IFACE, "WirelessEnabled", GLib.Variant("b", enabled))
            ),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
            None,
        )

    def connect_saved(self, connection_path: str) -> None:
        if not self._nm_proxy or not self._device_path:
            return
        self._nm_proxy.call(
            "ActivateConnection",
            GLib.Variant("(ooo)", (connection_path, self._device_path, "/")),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_activate_done,
            None,
        )

    def connect_new(self, ap_path: str, password: str) -> None:
        if not self._nm_proxy or not self._device_path:
            return
        info = self._ap_info(ap_path)
        ssid_bytes = info["ssid"].encode("utf-8")
        connection: dict = {
            "connection": {"type": GLib.Variant("s", "802-11-wireless")},
            "802-11-wireless": {
                "ssid": GLib.Variant("ay", ssid_bytes),
                "mode": GLib.Variant("s", "infrastructure"),
            },
        }
        if password:
            connection["802-11-wireless-security"] = {
                "key-mgmt": GLib.Variant("s", "wpa-psk"),
                "psk": GLib.Variant("s", password),
            }
        self._nm_proxy.call(
            "AddAndActivateConnection",
            GLib.Variant("(a{sa{sv}}oo)", (connection, self._device_path, ap_path)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._on_add_activate_done,
            None,
        )

    def request_scan(self) -> None:
        if not self._wireless_proxy:
            return
        self._wireless_proxy.call(
            "RequestScan",
            GLib.Variant("(a{sv})", ({},)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
            None,
        )

    def _on_activate_done(
        self, proxy: Gio.DBusProxy, result: Gio.AsyncResult, _: None
    ) -> None:
        try:
            proxy.call_finish(result)
        except GLib.Error as e:
            print(f"ActivateConnection failed: {e}", file=sys.stderr)
            self.emit("connection-failed", str(e))

    def _on_add_activate_done(
        self, proxy: Gio.DBusProxy, result: Gio.AsyncResult, _: None
    ) -> None:
        try:
            proxy.call_finish(result)
        except GLib.Error as e:
            print(f"AddAndActivateConnection failed: {e}", file=sys.stderr)
            self.emit("connection-failed", str(e))


_CSS = Path(__file__).parent.parent / "assets" / "css" / "network.css"


class NetworkRow(Gtk.Box):
    def __init__(
        self,
        ap_info: dict,
        backend: NetworkManagerBackend,
        saved: bool,
        section: "CollapsibleSection",
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("network-row")
        self._ap_info = ap_info
        self._backend = backend
        self._saved = saved
        self._section = section
        self._expanded = False
        self._error_timeout_id: int | None = None
        self._revealer: Gtk.Revealer | None = None
        self._pw_entry: Gtk.PasswordEntry | None = None
        self._error_label: Gtk.Label | None = None

        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = Gtk.Image(icon_name=_strength_to_icon(ap_info["strength"]))
        ssid_label = Gtk.Label(label=ap_info["ssid"])
        ssid_label.set_hexpand(True)
        ssid_label.set_xalign(0)
        band_label = Gtk.Label(label=f"({ap_info['band']})")
        header.append(icon)
        header.append(ssid_label)
        header.append(band_label)
        if ap_info["secured"]:
            header.append(Gtk.Image(icon_name="network-wireless-encrypted-symbolic"))

        gesture = Gtk.GestureClick()
        gesture.connect("released", self._on_header_clicked)
        header.add_controller(gesture)

        if saved:
            rclick = Gtk.GestureClick()
            rclick.set_button(3)
            rclick.connect("released", self._on_right_click)
            header.add_controller(rclick)

        self.append(header)

        if not saved and ap_info["secured"]:
            self._build_password_revealer()
            backend.connect("connection-failed", self._on_connection_failed)

    def _build_password_revealer(self) -> None:
        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_reveal_child(False)

        pw_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pw_box.set_margin_start(12)
        pw_box.set_margin_top(4)
        pw_box.set_margin_bottom(4)

        self._pw_entry = Gtk.PasswordEntry()
        self._pw_entry.set_property("placeholder-text", "Password")
        self._pw_entry.set_show_peek_icon(True)

        self._error_label = Gtk.Label(label="Wrong password")
        self._error_label.add_css_class("password-error-label")
        self._error_label.set_visible(False)
        self._error_label.set_xalign(0)

        connect_btn = Gtk.Button(label="Connect")
        connect_btn.connect("clicked", self._on_connect_clicked)
        self._pw_entry.connect(
            "activate", lambda _: self._on_connect_clicked(connect_btn)
        )

        pw_box.append(self._pw_entry)
        pw_box.append(self._error_label)
        pw_box.append(connect_btn)
        self._revealer.set_child(pw_box)
        self.append(self._revealer)

    def _on_header_clicked(
        self, _gesture: Gtk.GestureClick, _n: int, _x: float, _y: float
    ) -> None:
        if self._saved:
            conn_path = self._ap_info.get("connection_path")
            if conn_path:
                self._backend.connect_saved(conn_path)
        elif not self._ap_info["secured"]:
            self._backend.connect_new(self._ap_info["object_path"], "")
        else:
            if self._expanded:
                self.collapse()
            else:
                self._section.collapse_all_rows()
                self._expanded = True
                if self._revealer:
                    self._revealer.set_reveal_child(True)

    def _on_right_click(
        self, gesture: Gtk.GestureClick, _n: int, x: float, y: float
    ) -> None:
        conn_path = self._ap_info.get("connection_path")
        if not conn_path:
            return

        forget_btn = Gtk.Button(label="Forget")
        forget_btn.add_css_class("flat")
        forget_btn.add_css_class("forget-btn")

        popover = Gtk.Popover()
        popover.set_child(forget_btn)
        popover.set_parent(self)

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.set_autohide(True)
        popover.popup()

        def _forget(_btn: Gtk.Button) -> None:
            popover.popdown()
            self._backend.forget_connection(conn_path)

        forget_btn.connect("clicked", _forget)

    def collapse(self) -> None:
        self._expanded = False
        if self._revealer:
            self._revealer.set_reveal_child(False)

    def _on_connect_clicked(self, _btn: Gtk.Button) -> None:
        password = self._pw_entry.get_text() if self._pw_entry else ""
        self._backend.connect_new(self._ap_info["object_path"], password)

    def _on_connection_failed(self, _backend: NetworkManagerBackend, _msg: str) -> None:
        if not self._expanded or not self._pw_entry or not self._error_label:
            return
        self._pw_entry.add_css_class("password-error")
        self._error_label.set_visible(True)
        if self._error_timeout_id:
            GLib.source_remove(self._error_timeout_id)
        self._error_timeout_id = GLib.timeout_add(2000, self._clear_error)

    def _clear_error(self) -> bool:
        if self._pw_entry:
            self._pw_entry.remove_css_class("password-error")
        if self._error_label:
            self._error_label.set_visible(False)
        self._error_timeout_id = None
        return GLib.SOURCE_REMOVE


class CollapsibleSection(Gtk.Box):
    def __init__(self, title: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._rows: list[NetworkRow] = []

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.add_css_class("section-header")
        self._arrow = Gtk.Image(icon_name="pan-down-symbolic")
        title_label = Gtk.Label(label=title)
        title_label.set_hexpand(True)
        title_label.set_xalign(0)
        self._count_label = Gtk.Label(label="(0)")
        header.append(self._arrow)
        header.append(title_label)
        header.append(self._count_label)

        gesture = Gtk.GestureClick()
        gesture.connect("released", self._toggle)
        header.add_controller(gesture)

        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_reveal_child(False)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._revealer.set_child(self._list_box)

        self.append(header)
        self.append(self._revealer)

    def _toggle(self, _g: Gtk.GestureClick, _n: int, _x: float, _y: float) -> None:
        expanded = self._revealer.get_reveal_child()
        self._revealer.set_reveal_child(not expanded)
        self._arrow.set_from_icon_name(
            "pan-down-symbolic" if not expanded else "pan-end-symbolic"
        )

    def update_rows(
        self, ap_list: list[dict], backend: NetworkManagerBackend, saved: bool
    ) -> None:
        child = self._list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt
        self._rows.clear()
        self._count_label.set_text(f"({len(ap_list)})")
        for ap_info in ap_list:
            row = NetworkRow(ap_info, backend, saved=saved, section=self)
            self._rows.append(row)
            self._list_box.append(row)
        if ap_list:
            self._revealer.set_reveal_child(True)
            self._arrow.set_from_icon_name("pan-down-symbolic")

    def collapse_all_rows(self) -> None:
        for row in self._rows:
            row.collapse()


class WifiHeader(Gtk.Box):
    def __init__(self, backend: NetworkManagerBackend) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class("section-header")
        self._backend = backend

        label = Gtk.Label(label="Wi-Fi")
        label.set_hexpand(True)
        label.set_xalign(0)

        self._switch = Gtk.Switch()
        self._switch.set_active(backend.get_wifi_enabled())
        self._switch.connect("state-set", self._on_toggled)
        backend.connect("wifi-enabled-changed", self._on_enabled_changed)

        self.append(label)
        self.append(self._switch)

    def _on_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        self._backend.set_wifi_enabled(state)
        return False

    def _on_enabled_changed(
        self, _backend: NetworkManagerBackend, enabled: bool
    ) -> None:
        self._switch.handler_block_by_func(self._on_toggled)
        self._switch.set_active(enabled)
        self._switch.handler_unblock_by_func(self._on_toggled)


class ActiveConnectionRow(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class("network-row-active")

        self._icon = Gtk.Image(icon_name="network-wireless-offline-symbolic")
        self._ssid = Gtk.Label()
        self._ssid.set_hexpand(True)
        self._ssid.set_xalign(0)
        self._band = Gtk.Label()
        dot = Gtk.Label(label="●")
        dot.add_css_class("connected-dot")

        self.append(self._icon)
        self.append(self._ssid)
        self.append(self._band)
        self.append(dot)
        self.set_visible(False)

    def update(self, ap_info: dict) -> None:
        self._icon.set_from_icon_name(_strength_to_icon(ap_info["strength"]))
        self._ssid.set_text(ap_info["ssid"])
        self._band.set_text(f"({ap_info['band']})")


class NetworkControl(Gtk.MenuButton):
    def __init__(self) -> None:
        super().__init__()
        self._backend = NetworkManagerBackend()

        # Bar label
        bar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._bar_icon = Gtk.Image(icon_name="network-wireless-offline-symbolic")
        self._bar_label = Gtk.Label(label="Disconnected")
        bar_box.append(self._bar_icon)
        bar_box.append(self._bar_label)
        self.set_child(bar_box)

        # Popover content
        self._popover_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._popover_content.add_css_class("network-panel")

        self._wifi_header = WifiHeader(self._backend)
        self._active_row = ActiveConnectionRow()
        self._saved_section = CollapsibleSection("Saved")
        self._available_section = CollapsibleSection("Available")

        self._popover_content.append(self._wifi_header)
        self._popover_content.append(self._active_row)
        self._popover_content.append(self._saved_section)
        self._popover_content.append(self._available_section)

        popover = Gtk.Popover()
        popover.add_css_class("network-popover")
        popover.set_child(self._popover_content)
        self.set_popover(popover)
        popover.connect("show", self._on_popover_show)

        # CSS
        provider = Gtk.CssProvider()
        provider.load_from_path(str(_CSS))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Signals
        self._backend.connect("active-connection-changed", self._on_active_changed)
        self._backend.connect("wifi-enabled-changed", self._on_wifi_enabled)
        self._backend.connect("access-points-changed", self._on_aps_changed)

        GLib.idle_add(self._backend.refresh)

    def _on_popover_show(self, _popover: Gtk.Popover) -> None:
        self._backend.request_scan()

    def _on_active_changed(
        self, _backend: NetworkManagerBackend, ap_info: dict | None
    ) -> None:
        if ap_info is None:
            self._bar_icon.set_from_icon_name("network-wireless-offline-symbolic")
            self._bar_label.set_text("Disconnected")
            self._active_row.set_visible(False)
        else:
            self._bar_icon.set_from_icon_name(_strength_to_icon(ap_info["strength"]))
            self._bar_label.set_text(
                f"{_truncate_ssid(ap_info['ssid'])} ({ap_info['band']})"
            )
            self._active_row.update(ap_info)
            self._active_row.set_visible(True)

    def _on_wifi_enabled(self, _backend: NetworkManagerBackend, enabled: bool) -> None:
        if not enabled:
            self._bar_icon.set_from_icon_name("network-wireless-offline-symbolic")
            self._bar_label.set_text("Disabled")

    def _on_aps_changed(
        self,
        _backend: NetworkManagerBackend,
        saved: list[dict],
        available: list[dict],
    ) -> None:
        self._saved_section.update_rows(saved, self._backend, saved=True)
        self._available_section.update_rows(available, self._backend, saved=False)
