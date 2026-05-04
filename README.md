# Another Python Shell for Hyprland

Custom UI shell for Hyprland, using gtk4-shell for Python.

## Background
I started this project as a personal experiment to learn how to use `gtk4-shell` for building custom desktop shell components targeting Hyprland.

## Features
- **AudioControl Widget**: Volume control with icon and percentage label, device switching, route selection for speakers.
- **Network Interface Widget**: WiFi network manager 
- **PowerMenu Standalone**: Lock, suspend, logout, reboot, and shutdown actions with a pixel art background, username display, and uptime info.
- **More widgets and features will be added**

## Prerequisites
- Python 3.8+
- GTK 4
- gtk4-layer-shell
- AstalWp (for audio control)
- PyGObject (GI bindings for GTK)
- Hyprland (window manager)

## System dependencies
- Install system dependencies (Arch Linux example):
   ```bash
   sudo pacman -S gtk4 gtk4-layer-shell python-gobject astal-wp hyprland
   ```
   ```
```

