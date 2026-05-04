import gi
from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")  # pyright: ignore[reportUnusedCallResult]


gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnusedImport]  # noqa: E402


from utils.config_helper import get_auto_hide


TRIGGER_HEIGHT = 10
PANEL_HEIGHT = 40


class Bar(Gtk.Window):
    def __init__(self, config, **kwargs) -> None:
        super().__init__(**kwargs)

        enabled, delay = get_auto_hide(config)
        self.auto_hide = enabled
        self.hide_delay = delay
        self.hide_timeout = None
        self.is_expanded = not self.auto_hide

        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.TOP)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
        LayerShell.auto_exclusive_zone_enable(self)
        LayerShell.set_namespace(self, "pybar-bar")

        self.set_default_size(200, TRIGGER_HEIGHT)

        self._layout: Gtk.Box = Gtk.Box(spacing=13)
        self.set_child(self._layout)

        if self.auto_hide:
            self.layout_motion_controller = Gtk.EventControllerMotion()
            self.layout_motion_controller.connect("enter", lambda *_: self.show_panel())
            self.layout_motion_controller.connect(
                "leave", lambda *_: self.schedule_hide()
            )
            self._layout.set_visible(not self.auto_hide)
            self._layout.add_controller(self.layout_motion_controller)

            self.window_motion_controller = Gtk.EventControllerMotion()
            self.window_motion_controller.connect("enter", lambda *_: self.show_panel())
            self.window_motion_controller.connect(
                "leave", lambda *_: self.schedule_hide()
            )
            self.add_controller(self.window_motion_controller)

    def add_widget(self, widget: Gtk.Widget) -> None:
        self._layout.append(widget)

    def hide_panel(self):
        self.hide_timeout = None
        if self.is_expanded:
            self.is_expanded = False
            self.set_default_size(200, TRIGGER_HEIGHT)
            self._layout.set_visible(False)

    def show_panel(self):
        if self.hide_timeout:
            GLib.source_remove(self.hide_timeout)
            self.hide_timeout = None
        if not self.is_expanded:
            self.is_expanded = True
            self._layout.set_visible(True)
            self.set_default_size(200, PANEL_HEIGHT)

    def schedule_hide(self):
        if self.hide_timeout:
            GLib.source_remove(self.hide_timeout)
        self.hide_timeout = GLib.timeout_add(self.hide_delay, self.hide_panel)
