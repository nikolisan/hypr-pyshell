import gi
from ctypes import CDLL

CDLL("libgtk4-layer-shell.so")  # pyright: ignore[reportUnusedCallResult]


gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnusedImport]  # noqa: E402

from widgets.Bar import Bar
from widgets.AudioControl import AudioControl


class PyShell(Gtk.Application):
    def __init__(self, **kwargs) -> None:
        super().__init__(application_id="com.my_application.id")
        self.connect("activate", self.on_activate)

    def on_activate(self, app) -> None:
        bar: Bar = Bar(application=app)
        bar.add_widget(Gtk.Label(label="Test"))
        bar.add_widget(AudioControl())
        bar.present()


PyShell().run(None)
