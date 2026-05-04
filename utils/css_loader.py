import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gdk


def load_css(css_path: str) -> None:
    provider = Gtk.CssProvider()
    provider.load_from_path(css_path)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
