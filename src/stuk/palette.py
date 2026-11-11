"""Map configurable colors to curses, restoring temporary RGB slots on exit."""

from __future__ import annotations

import curses

from .theme import indexed_rgb, nearest_color, resolve_colors, rgb


class Palette:
    def __init__(self, theme: str = "lavender", overrides: dict | None = None) -> None:
        self._original_colors: dict[int, tuple[int, int, int]] = {}
        self._colored = curses.has_colors()
        self._mutable = False
        self._default_colors = False
        self.background = curses.A_NORMAL
        self.ink = curses.A_NORMAL
        self.muted = curses.A_DIM
        self.faint = curses.A_DIM
        self.future = curses.A_DIM
        self.accent = curses.A_BOLD
        self.error = curses.A_UNDERLINE
        self.cursor = curses.A_REVERSE
        if not self._colored:
            return
        try:
            curses.start_color()
            try:
                curses.use_default_colors()
                self._default_colors = True
            except curses.error:
                pass
            self._mutable = curses.COLORS >= 256 and curses.can_change_color()
            self.apply(theme, overrides)
        except BaseException:
            self.close()
            raise

    def _restore_colors(self) -> None:
        for slot, color in self._original_colors.items():
            try:
                curses.init_color(slot, *color)
            except curses.error:
                pass

    def close(self) -> None:
        self._restore_colors()
        self._original_colors.clear()

    def _color(
        self, value: str | int, slots: list[int], *, background: bool = False
    ) -> int:
        if value == "default":
            return -1 if self._default_colors else (0 if background else 7)
        if type(value) is int:
            if value < min(curses.COLORS, 256):
                # Direct-color terminfo reserves only ANSI 0–7 as named colors.
                if curses.COLORS < 1 << 24 or value < 8:
                    return value
            channels = indexed_rgb(value)
        else:
            channels = rgb(value)
        if curses.COLORS >= 1 << 24:
            red, green, blue = channels
            # xterm-direct uses 0–7 as ANSI aliases, even for packed RGB.
            return max(8, red << 16 | green << 8 | blue)
        if self._mutable:
            slot = slots.pop(0)
            if slot not in self._original_colors:
                self._original_colors[slot] = curses.color_content(slot)
            # OSC 4 terminfo truncates back to 8-bit RGB, so round upward here.
            curses.init_color(
                slot, *((channel * 1000 + 254) // 255 for channel in channels)
            )
            return slot
        count = 256 if curses.COLORS >= 256 else (16 if curses.COLORS >= 16 else 8)
        color = "#" + "".join(f"{channel:02x}" for channel in channels)
        return nearest_color(color, count)

    def apply(self, theme: str, overrides: dict | None = None) -> None:
        if not self._colored:
            return
        self._restore_colors()
        colors = resolve_colors(theme, overrides)
        # Explicit numeric overrides must never be reused as temporary RGB slots.
        fixed = {value for value in colors.values() if type(value) is int}
        slots = [
            slot for slot in range(16, min(curses.COLORS, 256)) if slot not in fixed
        ]
        try:
            mapped = {
                key: self._color(value, slots, background=key == "background")
                for key, value in colors.items()
            }
        except curses.error:
            if not self._mutable:
                self._restore_colors()
                raise
            self._restore_colors()
            self._mutable = False
            self.apply(theme, overrides)
            return
        except BaseException:
            self._restore_colors()
            raise
        background = mapped["background"]
        try:
            for pair, key in enumerate(
                (
                    "foreground",
                    "muted",
                    "border",
                    "accent",
                    "error",
                    "cursor_text",
                    "pending",
                ),
                1,
            ):
                curses.init_pair(
                    pair, mapped[key], mapped["accent"] if pair == 6 else background
                )
        except BaseException:
            self._restore_colors()
            raise
        self.ink = curses.color_pair(1)
        self.muted = curses.color_pair(2)
        self.faint = curses.color_pair(3)
        self.accent = curses.color_pair(4)
        self.error = curses.color_pair(5) | curses.A_UNDERLINE
        self.cursor = curses.color_pair(6)
        self.future = curses.color_pair(7)
        self.background = self.ink
        if curses.COLORS < 16:
            self.muted |= curses.A_DIM
            self.faint |= curses.A_DIM
            self.future |= curses.A_DIM
