import gi

gi.require_version("Gtk", "4.0")
gi.require_version("AstalWp", "0.1")

from gi.repository import Gtk, AstalWp


class DeviceRoutes(Gtk.Box):
    def __init__(self, endpoint: AstalWp.Endpoint):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
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


class DeviceRow(Gtk.Box):
    def __init__(self, endpoint: AstalWp.Endpoint, group: Gtk.CheckButton):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._endpoint = endpoint
        self._expanded = False

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._default_btn = Gtk.CheckButton()
        self._default_btn.set_group(group)
        self._default_btn.set_active(endpoint.get_is_default())
        self._default_btn.connect("toggled", self._on_default_toggled)
        endpoint.connect("notify::is-default", lambda *_: self._refresh_default())

        label = Gtk.Label(
            label=endpoint.get_description() or endpoint.get_name() or "Unknown"
        )
        label.set_hexpand(True)
        label.set_xalign(0)

        self._expand_btn = Gtk.Button(label="")
        self._expand_btn.connect("clicked", self._toggle_routes)

        header.append(self._default_btn)
        header.append(label)
        header.append(self._expand_btn)
        self.append(header)

        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_reveal_child(False)
        self._revealer.set_child(DeviceRoutes(endpoint))
        self.append(self._revealer)

    def _refresh_default(self):
        self._default_btn.handler_block_by_func(self._on_default_toggled)
        self._default_btn.set_active(self._endpoint.get_is_default())
        self._default_btn.handler_unblock_by_func(self._on_default_toggled)

    def _on_default_toggled(self, btn: Gtk.CheckButton):
        if btn.get_active():
            self._endpoint.set_is_default(True)

    def _toggle_routes(self, _btn):
        self._expanded = not self._expanded
        self._revealer.set_reveal_child(self._expanded)


class PlaybackDevicesMenu(Gtk.Box):
    def __init__(self, audio: AstalWp.Audio):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._rows: dict[int, DeviceRow] = {}
        self._checkbox_group: Gtk.CheckButton = Gtk.CheckButton()

        header = Gtk.Label(label="Playback Devices")
        header.set_xalign(0)
        self.append(header)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self._list)

        for speaker in audio.get_speakers():
            self._add_speaker(speaker)

        audio.connect("speaker-added", lambda _, ep: self._add_speaker(ep))
        audio.connect("speaker-removed", lambda _, ep: self._remove_speaker(ep))

    def _add_speaker(self, endpoint: AstalWp.Endpoint):
        row = DeviceRow(endpoint, group=self._checkbox_group)
        self._rows[endpoint.get_id()] = row
        self._list.append(row)

    def _remove_speaker(self, endpoint: AstalWp.Endpoint):
        row = self._rows.pop(endpoint.get_id(), None)
        if row:
            self._list.remove(row)


class AudioControl(Gtk.MenuButton):
    def __init__(self):
        super().__init__()

        wp = AstalWp.get_default()
        self._audio = wp.get_audio()
        self._speaker = wp.get_default_speaker()

        self._icon = Gtk.Image(icon_name=self._speaker.get_volume_icon())
        self.set_child(self._icon)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        # content.set_margin_top(8)
        # content.set_margin_bottom(8)
        # content.set_margin_start(8)
        # content.set_margin_end(8)

        content.append(self._build_volume_row())
        content.append(PlaybackDevicesMenu(self._audio))

        popover = Gtk.Popover()
        popover.set_child(content)
        self.set_popover(popover)

        self._speaker.connect("notify::volume", lambda *_: self._sync_volume())
        self._speaker.connect("notify::mute", lambda *_: self._sync_volume())
        self._speaker.connect("notify::volume-icon", lambda *_: self._sync_icon())
        self._sync_volume()

    def _build_volume_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.set_size_request(260, -1)

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
