"""Terminal-independent palettes and conservative terminal color conversion."""

from __future__ import annotations

import re

COLOR_KEYS = (
    "background",
    "foreground",
    "muted",
    "border",
    "pending",
    "accent",
    "error",
    "cursor_text",
)

THEMES: dict[str, dict[str, str | int]] = {
    "lavender": {
        "background": "#16161e",
        "foreground": "#e1dbea",
        "muted": "#8d859e",
        "border": "#38303f",
        "pending": "#746c83",
        "accent": "#c4b5fd",
        "error": "#ed9aaa",
        "cursor_text": "#16161e",
    },
    "terminal": {
        "background": "default",
        "foreground": "default",
        "muted": 8,
        "border": 0,
        "pending": 8,
        "accent": 5,
        "error": 1,
        "cursor_text": 0,
    },
    "warm": {
        "background": "#1c1c1c",
        "foreground": "#d0d0d0",
        "muted": "#808080",
        "border": "#444444",
        "pending": "#626262",
        "accent": "#d7af87",
        "error": "#d78787",
        "cursor_text": "#1c1c1c",
    },
}

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_ANSI_RGB = (
    (0, 0, 0),
    (128, 0, 0),
    (0, 128, 0),
    (128, 128, 0),
    (0, 0, 128),
    (128, 0, 128),
    (0, 128, 128),
    (192, 192, 192),
    (128, 128, 128),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (0, 0, 255),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
)
_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)
_XTERM_RGB = tuple(
    (16 + red * 36 + green * 6 + blue, (red_value, green_value, blue_value))
    for red, red_value in enumerate(_CUBE_LEVELS)
    for green, green_value in enumerate(_CUBE_LEVELS)
    for blue, blue_value in enumerate(_CUBE_LEVELS)
) + tuple((232 + level, (8 + level * 10,) * 3) for level in range(24))


def valid_color(value: object) -> bool:
    """Accept RGB hex, an ANSI/xterm index, or the terminal's default color."""
    if type(value) is int:
        return 0 <= value <= 255
    return isinstance(value, str) and (
        value == "default" or _HEX_COLOR.fullmatch(value) is not None
    )


def resolve_colors(
    theme: str = "lavender", overrides: dict | None = None
) -> dict[str, str | int]:
    """Return a fresh complete palette with valid, known overrides applied."""
    name = theme if isinstance(theme, str) and theme in THEMES else "lavender"
    colors = THEMES[name].copy()
    if isinstance(overrides, dict):
        for key in COLOR_KEYS:
            if key in overrides and valid_color(overrides[key]):
                colors[key] = overrides[key]
    return colors


def rgb(color: str) -> tuple[int, int, int]:
    """Convert a six-digit hex color to 8-bit RGB channels."""
    if not isinstance(color, str) or _HEX_COLOR.fullmatch(color) is None:
        raise ValueError("Use a color in #RRGGBB format.")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def indexed_rgb(index: int) -> tuple[int, int, int]:
    """Return canonical xterm RGB for an index, independent of terminal settings."""
    if type(index) is not int or not 0 <= index <= 255:
        raise ValueError("A terminal color index must be an integer from 0 to 255.")
    if index < 16:
        return _ANSI_RGB[index]
    if index < 232:
        offset = index - 16
        return (
            _CUBE_LEVELS[offset // 36],
            _CUBE_LEVELS[(offset // 6) % 6],
            _CUBE_LEVELS[offset % 6],
        )
    return (8 + (index - 232) * 10,) * 3


def nearest_color(hexcolor: str, color_count: int = 256) -> int:
    """Find the closest fixed terminal color by squared RGB distance.

    The 256-color search excludes ANSI indices 0–15 because terminals can redefine
    those. Eight- and sixteen-color terminals use the standard ANSI approximation.
    """
    if type(color_count) is not int or color_count not in (8, 16, 256):
        raise ValueError("Terminal color count must be 8, 16, or 256.")
    source = rgb(hexcolor)
    candidates = (
        _XTERM_RGB if color_count == 256 else tuple(enumerate(_ANSI_RGB[:color_count]))
    )
    return min(
        candidates,
        key=lambda candidate: sum(
            (channel - target) ** 2 for channel, target in zip(source, candidate[1])
        ),
    )[0]
