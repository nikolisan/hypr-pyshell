from subprocess import run


def change_brightness(brightness: int, bus: int, capture: bool = True):
    result = run(
        [
            "ddcutil",
            "setvcp",
            "10",
            f"{brightness}",
            "--bus",
            f"{bus}",
            "--skip-ddc-checks",
            "--enable-dynamic-sleep",
            "--noverify",
        ],
        capture_output=capture,
        text=True,
    )
    return result.returncode


if __name__ == "__main__":
    a = change_brightness(65, 8)
