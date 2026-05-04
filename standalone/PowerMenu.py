from pathlib import Path
import os
import pwd
from datetime import timedelta
import gi
from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")  # pyright: ignore[reportUnusedCallResult]
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import GLib, Gtk, Gio, Gdk
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnusedImport]  # noqa: E402

try:
    from pyshell.utils.css_loader import load_css
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.css_loader import load_css

BASE_DIR = Path(__file__).parent.parent
PICTURE = BASE_DIR / "assets" / "images" / "pixel_art.png"
CSS = BASE_DIR / "assets" / "css" / "powermenu.css"

ACTIONS = [
    ("Lock", "system-lock-screen-symbolic"),
    ("Suspend", "system-suspend-symbolic"),
    ("Logout", "system-log-out-symbolic"),
    ("Reboot", "system-reboot-symbolic"),
    ("Shutdown", "system-shutdown-symbolic"),
]


def _username() -> str:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        return os.environ.get("USER", "user")


def _uptime() -> str:
    try:
        seconds = float(open("/proc/uptime").read().split()[0])
        td = timedelta(seconds=int(seconds))
        h, rem = divmod(td.seconds, 3600)
        m = rem // 60
        if td.days:
            return f"{td.days} days, {h} hours"
        if h:
            return f"{h} hours, {m} minutes"
        return f"{m} minutes"
    except Exception:
        return ""


class PowerMenuWindow(Gtk.Window):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.TOP)
        LayerShell.set_namespace(self, "powermenu")
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

        self.add_css_class("power-menu")

        monitor = Gdk.Display.get_default().get_monitors().get_item(0)
        geo = monitor.get_geometry()
        win_w = geo.width // 4
        win_h = int(geo.height * 0.3)
        self.set_default_size(win_w, win_h)
        self.set_size_request(win_w, win_h)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(main)

        # picture + info overlay
        pic_overlay = Gtk.Overlay()
        pic_overlay.set_vexpand(True)

        picture = Gtk.Picture.new_for_file(
            Gio.File.new_for_path(str(PICTURE.resolve()))
        )
        picture.set_content_fit(Gtk.ContentFit.FILL)
        pic_overlay.set_child(picture)

        # username + uptime — overlaid at bottom of picture
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info.add_css_class("info-box")
        info.set_halign(Gtk.Align.FILL)
        info.set_valign(Gtk.Align.END)
        info.append(Gtk.Label(label=f"@{_username()}"))
        info.append(Gtk.Label(label=_uptime()))
        pic_overlay.add_overlay(info)

        main.append(pic_overlay)

        # buttons
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        buttons.add_css_class("buttons-box")
        buttons.set_halign(Gtk.Align.CENTER)
        buttons.set_margin_bottom(12)
        for label, icon in ACTIONS:
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            inner.set_halign(Gtk.Align.CENTER)
            inner.set_valign(Gtk.Align.CENTER)
            inner.append(Gtk.Image.new_from_icon_name(icon))
            inner.append(Gtk.Label(label=label))
            btn = Gtk.Button()
            btn.set_child(inner)
            btn.connect("clicked", lambda _, a=label: self._on_action(a))
            buttons.append(btn)
        main.append(buttons)

    def _on_key_pressed(self, ctrl, keyval, keycode, state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _on_action(self, action: str):
        user = _username()
        commands = {
            "Lock": ["loginctl", "lock-session"],
            "Suspend": ["systemctl", "suspend"],
            "Logout": ["loginctl", "terminate-user", user],
            "Reboot": ["systemctl", "reboot"],
            "Shutdown": ["systemctl", "poweroff"],
        }
        cmd = commands.get(action)
        if cmd:
            Gio.Subprocess.new(cmd, Gio.SubprocessFlags.NONE)


class PowerMenuOSD(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.my_application.id")
        self.connect("activate", self.on_activate)

    def _init_css(self) -> None:
        load_css(str(CSS))

    def on_activate(self, app) -> None:
        self._init_css()
        power_menu: PowerMenuWindow = PowerMenuWindow(application=app)
        power_menu.present()


if __name__ == "__main__":
    import sys

    try:
        PowerMenuOSD().run(None)
    except KeyboardInterrupt:
        sys.exit(0)
