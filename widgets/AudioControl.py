import gi
from pathlib import Path

gi.require_version("Gtk", "4.0")
gi.require_version("AstalWp", "0.1")

from gi.repository import Gtk, Gdk, AstalWp
from gi.repository import Gtk4LayerShell as LayerShell  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType, reportUnusedImport]  # noqa: E402

_CSS = Path(__file__).parent.parent / "assets" / "css" / "audio.css"


class DeviceRoutes(Gtk.Box):
    def __init__(self, endpoint: AstalWp.Endpoint):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add_css_class("audio-routes")
        self._endpoint = endpoint
        self._route_btns: list[Gtk.CheckButton] = []

        self._rebuild()
        endpoint.connect("notify::routes", lambda *_: self._rebuild())
        endpoint.connect("notify::route", lambda *_: self._refresh_active())

    def _rebuild(self):
        child = self.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.remove(child)
            child = nxt
        self._route_btns.clear()

        group = None
        for route in self._endpoint.get_routes() or []:
            btn = Gtk.CheckButton(label=route.get_description(), group=group)
            if group is None:
                group = btn
            btn.connect(
                "toggled",
                lambda b, r=route: (
                    self._endpoint.set_route(r) if b.get_active() else None
                ),
            )
            self._route_btns.append(btn)
            self.append(btn)

        self._refresh_active()

    def _refresh_active(self):
        active = self._endpoint.get_route()
        for route, btn in zip(self._endpoint.get_routes() or [], self._route_btns):
            btn.set_active(bool(active and active.get_index() == route.get_index()))


class ActiveDeviceRow(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("audio-active-device")
        self._expanded = False

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("audio-active-header")

        self._label = Gtk.Label()
        self._label.set_hexpand(True)
        self._label.set_xalign(0)

        self._arrow = Gtk.Image(icon_name="pan-end-symbolic")
        self._expand_btn = Gtk.Button()
        self._expand_btn.set_child(self._arrow)
        self._expand_btn.add_css_class("flat")
        self._expand_btn.add_css_class("audio-expand-btn")
        self._expand_btn.connect("clicked", self._toggle_routes)

        header.append(self._label)
        header.append(self._expand_btn)
        self.append(header)

        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_reveal_child(False)
        self.append(self._revealer)
        self.set_visible(False)

    def update(self, endpoint: AstalWp.Endpoint | None) -> None:
        if endpoint is None:
            self.set_visible(False)
            return
        self.set_visible(True)
        self._label.set_text(
            endpoint.get_description() or endpoint.get_name() or "Unknown"
        )
        self._revealer.set_child(DeviceRoutes(endpoint))
        self._expanded = False
        self._revealer.set_reveal_child(False)
        self._arrow.set_from_icon_name("pan-end-symbolic")

    def _toggle_routes(self, _btn) -> None:
        self._expanded = not self._expanded
        self._revealer.set_reveal_child(self._expanded)
        self._arrow.set_from_icon_name(
            "pan-down-symbolic" if self._expanded else "pan-end-symbolic"
        )


class AudioControl(Gtk.MenuButton):
    def __init__(self):
        super().__init__()
        wp = AstalWp.get_default()
        self._audio = wp.get_audio()
        self._speaker = wp.get_default_speaker()

        self._icon = Gtk.Image(icon_name=self._speaker.get_volume_icon())
        self.set_child(self._icon)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.add_css_class("audio-panel")

        content.append(self._build_volume_row())

        self._active_device = ActiveDeviceRow()
        content.append(self._active_device)

        self._other_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._other_list.add_css_class("audio-other-list")
        self._other_list.set_visible(False)
        content.append(self._other_list)

        popover = Gtk.Popover()
        popover.add_css_class("audio-popover")
        popover.set_child(content)
        self.set_popover(popover)

        provider = Gtk.CssProvider()
        provider.load_from_path(str(_CSS))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._speaker.connect("notify::volume", lambda *_: self._sync_volume())
        self._speaker.connect("notify::mute", lambda *_: self._sync_volume())
        self._speaker.connect("notify::volume-icon", lambda *_: self._sync_icon())
        self._sync_volume()

        for speaker in self._audio.get_speakers():
            self._on_speaker_added(speaker)
        self._audio.connect("speaker-added", lambda _, ep: self._on_speaker_added(ep))
        self._audio.connect("speaker-removed", lambda _, ep: self._rebuild_devices())

    def _on_speaker_added(self, speaker: AstalWp.Endpoint) -> None:
        speaker.connect(
            "notify::is-default", lambda *_: self._on_default_changed(speaker)
        )
        self._rebuild_devices()

    def _on_default_changed(self, new_default: AstalWp.Endpoint) -> None:
        if new_default.get_is_default() and new_default is not self._speaker:
            self._speaker = new_default
            self._speaker.connect("notify::volume", lambda *_: self._sync_volume())
            self._speaker.connect("notify::mute", lambda *_: self._sync_volume())
            self._speaker.connect("notify::volume-icon", lambda *_: self._sync_icon())
            self._sync_volume()
        self._rebuild_devices()

    def _rebuild_devices(self) -> None:
        speakers = self._audio.get_speakers()
        default = next((s for s in speakers if s.get_is_default()), None)
        others = [s for s in speakers if not s.get_is_default()]

        self._active_device.update(default)

        child = self._other_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._other_list.remove(child)
            child = nxt

        self._other_list.set_visible(bool(others))
        for sp in others:
            self._other_list.append(self._make_other_row(sp))

    def _make_other_row(self, endpoint: AstalWp.Endpoint) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("audio-other-device")
        label = Gtk.Label(
            label=endpoint.get_description() or endpoint.get_name() or "Unknown"
        )
        label.set_hexpand(True)
        label.set_xalign(0)
        row.append(label)
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda *_: endpoint.set_is_default(True))
        row.add_controller(gesture)
        return row

    def _build_volume_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("audio-volume-row")
        row.set_size_request(280, -1)

        self._vol_label: Gtk.Label = Gtk.Label(label="--")
        self._vol_label.set_width_chars(3)
        self._vol_label.set_xalign(1)

        self._slider: Gtk.Scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01
        )
        self._slider.set_hexpand(True)
        self._slider.set_draw_value(False)
        self._slider.connect("value-changed", self._on_slider_changed)

        self._mute_btn: Gtk.Button = Gtk.Button()
        self._mute_btn.connect("clicked", self._on_mute_clicked)

        row.append(self._vol_label)
        row.append(self._slider)
        row.append(self._mute_btn)
        return row

    def _sync_volume(self):
        vol = self._speaker.get_volume()
        self._vol_label.set_text(str(int(vol * 100)))
        self._slider.handler_block_by_func(self._on_slider_changed)
        self._slider.set_value(vol)
        self._slider.handler_unblock_by_func(self._on_slider_changed)
        self._sync_icon()

    def _sync_icon(self):
        icon = self._speaker.get_volume_icon()
        self._icon.set_from_icon_name(icon)
        self._mute_btn.set_icon_name(icon)

    def _on_slider_changed(self, slider: Gtk.Scale):
        self._speaker.set_volume(slider.get_value())

    def _on_mute_clicked(self, _btn):
        self._speaker.set_mute(not self._speaker.get_mute())
