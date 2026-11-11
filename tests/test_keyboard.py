"""Verify physical layouts and unambiguous cells for key highlighting."""

import string
import unicodedata
import unittest

from stuk.keyboard import (
    KEYBOARD_HEIGHT,
    KEYBOARD_WIDTH,
    key_positions,
    keyboard_rows,
)


class KeyboardTests(unittest.TestCase):
    def test_layouts_have_matching_compact_geometry(self) -> None:
        for language in ("ru", "en"):
            with self.subTest(language=language):
                rows = keyboard_rows(language)
                self.assertIsInstance(rows, tuple)
                self.assertEqual(len(rows), KEYBOARD_HEIGHT)
                self.assertLessEqual(KEYBOARD_WIDTH, 54)
                self.assertEqual({len(row) for row in rows}, {KEYBOARD_WIDTH})
                self.assertTrue(
                    all(
                        unicodedata.east_asian_width(character) not in ("W", "F")
                        and not unicodedata.combining(character)
                        for row in rows
                        for character in row
                    )
                )

    def test_english_rows_follow_qwerty(self) -> None:
        rows = keyboard_rows("en")
        self.assertEqual(rows[1].replace(" ", ""), "qwertyuiop[]\\")
        self.assertEqual(rows[2].replace(" ", ""), "asdfghjkl;'")
        self.assertEqual(rows[3].replace(" ", ""), "zxcvbnm,./")

    def test_russian_rows_follow_jcuken_and_include_yo(self) -> None:
        rows = keyboard_rows("ru")
        self.assertTrue(rows[0].startswith("ё  1"))
        self.assertEqual(rows[1].replace(" ", ""), "йцукенгшщзхъ\\")
        self.assertEqual(rows[2].replace(" ", ""), "фывапролджэ")
        self.assertEqual(rows[3].replace(" ", ""), "ячсмитьбю.")

    def test_every_letter_has_its_own_exact_cell(self) -> None:
        alphabets = {
            "en": string.ascii_lowercase,
            "ru": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        }
        for language, alphabet in alphabets.items():
            with self.subTest(language=language):
                rows = keyboard_rows(language)
                positions = key_positions(language)
                self.assertEqual(
                    len({positions[letter] for letter in alphabet}), len(alphabet)
                )
                self.assertTrue(set(alphabet) <= positions.keys())
                for key, (row, column) in positions.items():
                    if key != " ":
                        self.assertEqual(rows[row][column], key)

    def test_both_layouts_include_digits_and_visible_punctuation(self) -> None:
        for language in ("ru", "en"):
            with self.subTest(language=language):
                positions = key_positions(language)
                for key in string.digits + "-=\\.":
                    self.assertIn(key, positions)
        for key in "`[];',/":
            self.assertIn(key, key_positions("en"))

    def test_spacebar_mapping_is_not_confused_with_decorative_brackets(self) -> None:
        for language in ("ru", "en"):
            with self.subTest(language=language):
                rows = keyboard_rows(language)
                row, column = key_positions(language)[" "]
                self.assertEqual(row, KEYBOARD_HEIGHT - 1)
                self.assertEqual(rows[row][column], " ")
                self.assertGreater(column, rows[row].index("["))
                self.assertLess(column, rows[row].index("]"))
        self.assertEqual(key_positions("en")["["], (1, 31))
        self.assertEqual(key_positions("en")["]"], (1, 34))

    def test_callers_cannot_mutate_future_position_maps(self) -> None:
        positions = key_positions("en")
        positions["a"] = (99, 99)
        self.assertNotEqual(key_positions("en")["a"], (99, 99))

    def test_invalid_language_is_rejected(self) -> None:
        for language in ("de", "", "RU"):
            for function in (keyboard_rows, key_positions):
                with self.subTest(language=language, function=function.__name__):
                    with self.assertRaises(ValueError):
                        function(language)


if __name__ == "__main__":
    unittest.main()
