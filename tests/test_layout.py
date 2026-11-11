"""Keep text positions and the active cursor stable across terminal sizes."""

import unittest

from stuk.keyboard import KEYBOARD_HEIGHT, KEYBOARD_WIDTH
from stuk.layout import arrange, wrap_text


class WrappingTests(unittest.TestCase):
    def test_wrapping_preserves_spaces_unicode_and_long_words(self) -> None:
        text = "тихий  дом оченьдлинноеслово свет и воздух "
        for width in (1, 4, 8, 24, 68):
            with self.subTest(width=width):
                lines = wrap_text(text, width)
                self.assertEqual("".join(line.text for line in lines), text)
                offset = 0
                for line in lines:
                    self.assertEqual(line.start, offset)
                    self.assertLessEqual(len(line.text), width)
                    self.assertTrue(line.text)
                    offset += len(line.text)

    def test_empty_text_has_no_lines(self) -> None:
        self.assertEqual(wrap_text("", 24), [])

    def test_nonpositive_width_is_rejected(self) -> None:
        for width in (0, -1):
            with self.subTest(width=width), self.assertRaises(ValueError):
                wrap_text("some text", width)


class ViewportTests(unittest.TestCase):
    TEXT = " ".join(["воздух", "тихий", "лето", "дом", "свет"] * 15)

    def test_active_character_remains_visible_throughout_long_exercise(self) -> None:
        for rows, columns in ((12, 32), (14, 40), (20, 80), (30, 100)):
            lines = wrap_text(self.TEXT, min(68, columns - 8))
            for position in range(len(self.TEXT)):
                with self.subTest(size=(rows, columns), position=position):
                    layout = arrange(rows, columns, lines, position)
                    visible = lines[
                        layout.first_line : layout.first_line + layout.visible_lines
                    ]
                    self.assertTrue(
                        any(
                            line.start <= position < line.start + len(line.text)
                            for line in visible
                        )
                    )
                    self.assertGreaterEqual(layout.header_y, 0)
                    self.assertLess(layout.header_y, layout.text_y)
                    last_text_row = layout.text_y + (len(visible) - 1) * layout.spacing
                    self.assertLess(last_text_row, layout.progress_y)
                    self.assertLess(layout.progress_y, layout.status_y)
                    self.assertLess(layout.status_y, layout.footer_y)
                    self.assertLess(layout.footer_y, rows)
                    self.assertGreaterEqual(layout.left, 0)
                    self.assertLessEqual(layout.left + layout.width, columns)

    def test_resizing_preserves_exact_cursor_character(self) -> None:
        position = self.TEXT.index("лето", 100) + 2
        for rows, columns in ((30, 100), (12, 32), (24, 80), (30, 100)):
            with self.subTest(size=(rows, columns)):
                lines = wrap_text(self.TEXT, min(68, columns - 8))
                layout = arrange(rows, columns, lines, position)
                visible = lines[
                    layout.first_line : layout.first_line + layout.visible_lines
                ]
                active = next(
                    line
                    for line in visible
                    if line.start <= position < line.start + len(line.text)
                )
                self.assertEqual(
                    active.text[position - active.start], self.TEXT[position]
                )

    def test_completed_exercise_keeps_final_line_visible(self) -> None:
        lines = wrap_text(self.TEXT, 24)
        layout = arrange(12, 32, lines, len(self.TEXT))
        self.assertEqual(layout.first_line + layout.visible_lines, len(lines))


class KeyboardViewportTests(unittest.TestCase):
    TEXT = " ".join(["воздух", "тишина", "тёплый", "вечер", "письмо"] * 12)

    def test_keyboard_and_frame_fit_without_hiding_active_text(self) -> None:
        for rows, columns in ((22, 46), (24, 80), (32, 110)):
            lines = wrap_text(self.TEXT, min(68, columns - 8))
            for position in range(len(self.TEXT) + 1):
                with self.subTest(size=(rows, columns), position=position):
                    layout = arrange(rows, columns, lines, position, show_keyboard=True)
                    visible = lines[
                        layout.first_line : layout.first_line + layout.visible_lines
                    ]
                    character = min(position, len(self.TEXT) - 1)
                    self.assertTrue(
                        any(
                            line.start <= character < line.start + len(line.text)
                            for line in visible
                        )
                    )
                    first_text_row = layout.text_y
                    last_text_row = first_text_row + (len(visible) - 1) * layout.spacing
                    self.assertGreater(first_text_row, layout.header_y + 1)
                    self.assertLess(last_text_row, layout.frame_bottom - 1)
                    self.assertLess(layout.frame_bottom, layout.progress_y)
                    self.assertLess(layout.progress_y, layout.status_y)
                    self.assertIsNotNone(layout.keyboard_y)
                    self.assertGreater(layout.keyboard_y, layout.status_y + 1)
                    self.assertLess(
                        layout.keyboard_y + KEYBOARD_HEIGHT - 1,
                        layout.footer_y,
                    )
                    self.assertLess(layout.footer_y, rows)
                    keyboard_left = (columns - KEYBOARD_WIDTH) // 2
                    self.assertGreaterEqual(keyboard_left, 0)
                    self.assertLessEqual(keyboard_left + KEYBOARD_WIDTH, columns)
                    # The TUI adds three cells of frame padding on both sides.
                    self.assertGreaterEqual(layout.left - 3, 0)
                    self.assertLess(layout.left + layout.width + 2, columns)

    def test_keyboard_is_absent_unless_requested(self) -> None:
        lines = wrap_text(self.TEXT, 68)
        layout = arrange(32, 110, lines, 0)
        self.assertIsNone(layout.keyboard_y)

    def test_toggling_keyboard_preserves_cursor_and_frame_padding(self) -> None:
        position = self.TEXT.index("письмо", 100) + 3
        lines = wrap_text(self.TEXT, 68)
        for show_keyboard in (False, True, False):
            with self.subTest(show_keyboard=show_keyboard):
                layout = arrange(24, 80, lines, position, show_keyboard)
                visible = lines[
                    layout.first_line : layout.first_line + layout.visible_lines
                ]
                active = next(
                    line
                    for line in visible
                    if line.start <= position < line.start + len(line.text)
                )
                self.assertEqual(
                    active.text[position - active.start], self.TEXT[position]
                )
                self.assertGreater(layout.text_y, layout.header_y)
                self.assertLess(
                    layout.text_y + (len(visible) - 1) * layout.spacing,
                    layout.frame_bottom,
                )


if __name__ == "__main__":
    unittest.main()
