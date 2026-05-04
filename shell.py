from widgets.Bar import Bar
from widgets.AudioControl import AudioControl
from widgets.NetworkControl import NetworkControl
from widgets.PowerMenu import PowerMenuWindow
from utils.config_helper import load_config


import datetime
import gi
from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")  # pyright: ignore[reportUnusedCallResult]


gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gtk, GLib  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnusedImport]  # noqa: E402


class PyShell(Gtk.Application):
    def __init__(self, **kwargs) -> None:
        super().__init__(application_id="com.my_application.id")
        self.config = load_config()
        self.connect("activate", self.on_activate)
        self.power_btn = Gtk.Button(label="Power Menu")
        self.power_btn.connect("clicked", self._init_power_menu)
        self.clock = Gtk.Label()

    def _init_power_menu(self, args) -> None:
        menu: PowerMenuWindow = PowerMenuWindow()
        menu.present()

    def _update_interval(self):
        now = datetime.datetime.now().astimezone().strftime("%d %b %Y | %H:%M:%S")
        self.clock.set_label(now)
        return True

    def on_activate(self, app) -> None:
        self._update_interval()

        bar: Bar = Bar(config=self.config, application=app)
        bar.add_widget(AudioControl())
        bar.add_widget(NetworkControl())
        bar.add_widget(self.power_btn)
        bar.add_widget(self.clock)

        GLib.timeout_add_seconds(1, self._update_interval)

        bar.present()


PyShell().run(None)
