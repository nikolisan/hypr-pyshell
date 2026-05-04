import os
import tomllib

DEFAULT_CONFIG = {"auto_hide": {"enabled": "false", "hide_delay": "500"}}


def load_config(path="../config/pyshell.toml"):
    if not os.path.exists(path):
        return DEFAULT_CONFIG
    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
        return config
    except Exception as err:
        print(f"Error {err}")
        return DEFAULT_CONFIG


def get_auto_hide(config: dict) -> tuple[bool, int]:
    """Helper function to grab the enabled and delay from the conf file.
    returns:
        tuple(enabled: bool, delay: int)
    """
    autohide = config.get("auto_hide", None)
    if not autohide:
        return (False, 0)
    enabled = autohide.get("enabled", "false").lower() == "true"
    delay = autohide.get("hide_delay", 500)
    try:
        hide_delay = int(delay)
    except ValueError:
        hide_delay = 500
    return (enabled, hide_delay)
