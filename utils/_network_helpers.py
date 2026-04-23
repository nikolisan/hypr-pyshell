def _freq_to_band(freq_mhz: int) -> str:
    return "5G" if freq_mhz >= 5000 else "2.4G"


def _strength_to_icon(strength: int) -> str:
    if strength >= 80:
        return "network-wireless-signal-excellent-symbolic"
    if strength >= 55:
        return "network-wireless-signal-good-symbolic"
    if strength >= 30:
        return "network-wireless-signal-ok-symbolic"
    if strength > 0:
        return "network-wireless-signal-weak-symbolic"
    return "network-wireless-signal-none-symbolic"


def _truncate_ssid(ssid: str, max_len: int = 12) -> str:
    if len(ssid) <= max_len:
        return ssid
    side = (max_len - 3) // 2
    return f"{ssid[:side]}...{ssid[-(max_len - 3 - side):]}"
