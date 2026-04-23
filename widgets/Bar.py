import gi
from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")  # pyright: ignore[reportUnusedCallResult]


gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnusedImport]  # noqa: E402


class Bar(Gtk.Window):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.TOP)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, True)
        LayerShell.auto_exclusive_zone_enable(self)
        LayerShell.set_namespace(self, "pybar-bar")

        self._layout: Gtk.Box = Gtk.Box(spacing=13)
        self.set_child(self._layout)

    def add_widget(self, widget: Gtk.Widget) -> None:
        self._layout.append(widget)
