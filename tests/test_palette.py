"""Exercise curses color capabilities without requiring an attached terminal."""

import unittest
from unittest.mock import Mock, patch

from stuk.palette import Palette
from stuk.theme import nearest_color


class TerminalError(Exception):
    pass


class FakeCurses:
    error = TerminalError
    A_NORMAL = 0
    A_DIM = 1 << 20
    A_BOLD = 1 << 21
    A_UNDERLINE = 1 << 22
    A_REVERSE = 1 << 23

    def __init__(self, *, colors=256, colored=True, mutable=True, default_colors=True):
        self.COLORS = colors
        self.original_colors = {
            index: (index, 500, 1000 - index) for index in range(min(colors, 256))
        }
        self.colors = self.original_colors.copy()
        self.pairs = {}
        self.color_changes = 0
        self.pair_changes = 0
        self.fail_color_on = None
        self.fail_pair_on = None
        self.has_colors = Mock(return_value=colored)
        self.start_color = Mock()
        self.use_default_colors = Mock(
            side_effect=None if default_colors else TerminalError("no defaults")
        )
        self.can_change_color = Mock(return_value=mutable)
        self.color_content = Mock(side_effect=lambda index: self.colors[index])
        self.init_color = Mock(side_effect=self._set_color)
        self.init_pair = Mock(side_effect=self._set_pair)
        self.color_pair = Mock(side_effect=lambda pair: pair << 8)

    def _set_color(self, index, red, green, blue):
        self.color_changes += 1
        if self.color_changes == self.fail_color_on:
            raise TerminalError("color allocation failed")
        self.colors[index] = (red, green, blue)

    def _set_pair(self, pair, foreground, background):
        self.pair_changes += 1
        if self.pair_changes == self.fail_pair_on:
            raise TerminalError("pair allocation failed")
        self.pairs[pair] = (foreground, background)


class PaletteTests(unittest.TestCase):
    def test_monochrome_terminal_never_initializes_or_changes_colors(self):
        terminal = FakeCurses(colored=False)
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            palette.apply("warm")
            palette.close()
        terminal.start_color.assert_not_called()
        terminal.use_default_colors.assert_not_called()
        terminal.init_color.assert_not_called()
        terminal.init_pair.assert_not_called()
        self.assertEqual(palette.cursor, terminal.A_REVERSE)

    def test_mutable_terminal_uses_exact_rgb_and_restores_on_switch_and_close(self):
        terminal = FakeCurses()
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            changed_slots = {
                index
                for index, *_ in (
                    call.args for call in terminal.init_color.call_args_list
                )
            }
            self.assertEqual(changed_slots, set(range(16, 24)))
            self.assertEqual(terminal.init_color.call_count, 8)
            background = terminal.pairs[1][1]
            accent = terminal.pairs[4][0]
            self.assertEqual(terminal.colors[background], (87, 87, 118))
            self.assertEqual(terminal.colors[accent], (769, 710, 993))
            self.assertEqual(terminal.pairs[6][1], accent)

            palette.apply("terminal")
            self.assertEqual(terminal.colors, terminal.original_colors)
            palette.apply("warm")
            self.assertNotEqual(terminal.colors, terminal.original_colors)
            palette.close()
            self.assertEqual(terminal.colors, terminal.original_colors)

    def test_repeated_application_keeps_the_original_terminal_palette(self):
        terminal = FakeCurses()
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            palette.apply("warm")
            palette.apply("lavender")
            palette.close()
            palette.close()
        self.assertEqual(terminal.colors, terminal.original_colors)
        self.assertEqual(terminal.color_content.call_count, 8)

    def test_every_rgb_channel_survives_terminfo_integer_round_trip(self):
        terminal = FakeCurses()
        with patch("stuk.palette.curses", terminal):
            palette = Palette("terminal")
            for channel in range(256):
                with self.subTest(channel=channel):
                    color = f"#{channel:02x}{channel:02x}{channel:02x}"
                    palette.apply("terminal", {"accent": color})
                    slot = terminal.pairs[4][0]
                    # OSC 4 terminfo converts its 0–1000 inputs using truncation.
                    displayed = tuple(
                        component * 255 // 1000 for component in terminal.colors[slot]
                    )
                    self.assertEqual(displayed, (channel,) * 3)
            palette.close()
        self.assertEqual(terminal.colors, terminal.original_colors)

    def test_numeric_override_is_never_reused_as_an_rgb_slot(self):
        terminal = FakeCurses()
        with patch("stuk.palette.curses", terminal):
            palette = Palette(overrides={"accent": 16})
            self.assertEqual(terminal.pairs[4][0], 16)
            self.assertEqual(terminal.pairs[6][1], 16)
            self.assertEqual(terminal.colors[16], terminal.original_colors[16])
            self.assertTrue(
                all(call.args[0] != 16 for call in terminal.init_color.call_args_list)
            )
            palette.close()
        self.assertEqual(terminal.colors, terminal.original_colors)

    def test_partial_rgb_failure_restores_colors_and_uses_nearest_fallback(self):
        terminal = FakeCurses()
        terminal.fail_color_on = 3
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            self.assertEqual(terminal.colors, terminal.original_colors)
            self.assertEqual(terminal.pairs[1][1], nearest_color("#16161e"))
            self.assertEqual(terminal.pairs[4][0], nearest_color("#c4b5fd"))
            palette.apply("warm")
            self.assertEqual(terminal.colors, terminal.original_colors)
            palette.close()
        self.assertEqual(terminal.colors, terminal.original_colors)

    def test_constructor_pair_failure_restores_any_allocated_rgb_slots(self):
        terminal = FakeCurses()
        terminal.fail_pair_on = 3
        with patch("stuk.palette.curses", terminal):
            with self.assertRaises(TerminalError):
                Palette()
        self.assertEqual(terminal.colors, terminal.original_colors)

    def test_theme_switch_pair_failure_restores_any_allocated_rgb_slots(self):
        terminal = FakeCurses()
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            terminal.fail_pair_on = terminal.pair_changes + 3
            with self.assertRaises(TerminalError):
                palette.apply("warm")
            self.assertEqual(terminal.colors, terminal.original_colors)
            palette.close()

    def test_terminal_theme_uses_default_and_ansi_colors_without_mutation(self):
        terminal = FakeCurses()
        with patch("stuk.palette.curses", terminal):
            palette = Palette("terminal")
            self.assertEqual(terminal.pairs[1], (-1, -1))
            self.assertEqual(terminal.pairs[4], (5, -1))
            self.assertEqual(terminal.pairs[6], (0, 5))
            self.assertEqual(terminal.pairs[7], (8, -1))
            palette.close()
        terminal.init_color.assert_not_called()
        terminal.color_content.assert_not_called()

    def test_terminal_without_default_color_support_uses_black_and_white(self):
        terminal = FakeCurses(default_colors=False)
        with patch("stuk.palette.curses", terminal):
            palette = Palette("terminal")
            self.assertEqual(terminal.pairs[1], (7, 0))
            self.assertEqual(terminal.pairs[4], (5, 0))
            self.assertEqual(terminal.pairs[6], (0, 5))
            palette.close()
        terminal.init_color.assert_not_called()

    def test_fixed_256_color_terminal_uses_nearest_colors_without_mutation(self):
        terminal = FakeCurses(mutable=False)
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            self.assertEqual(terminal.pairs[1][1], nearest_color("#16161e"))
            self.assertEqual(terminal.pairs[4][0], nearest_color("#c4b5fd"))
            palette.close()
        terminal.init_color.assert_not_called()
        terminal.color_content.assert_not_called()

    def test_direct_color_terminal_uses_packed_rgb_without_slot_mutation(self):
        terminal = FakeCurses(colors=1 << 24)
        with patch("stuk.palette.curses", terminal):
            palette = Palette()
            self.assertEqual(terminal.pairs[1], (0xE1DBEA, 0x16161E))
            self.assertEqual(terminal.pairs[4], (0xC4B5FD, 0x16161E))
            self.assertEqual(terminal.pairs[6], (0x16161E, 0xC4B5FD))
            palette.apply("terminal")
            self.assertEqual(terminal.pairs[7], (0x808080, -1))
            self.assertEqual(terminal.pairs[4], (5, -1))
            palette.apply("terminal", {"accent": 196})
            self.assertEqual(terminal.pairs[4], (0xFF0000, -1))
            palette.close()
        terminal.init_color.assert_not_called()
        terminal.color_content.assert_not_called()

    def test_direct_color_near_black_hex_does_not_become_an_ansi_alias(self):
        terminal = FakeCurses(colors=1 << 24)
        with patch("stuk.palette.curses", terminal):
            palette = Palette("terminal", {"accent": "#000001"})
            self.assertEqual(terminal.pairs[4][0], 8)
            palette.apply("terminal", {"accent": 1})
            self.assertEqual(terminal.pairs[4][0], 1)
            palette.close()
        terminal.init_color.assert_not_called()


if __name__ == "__main__":
    unittest.main()
