"""Normalize physical keys without correcting spelling or changing native input."""

import string
import unittest

from stuk.keyboard import normalize_input


def translated(text, language):
    return "".join(normalize_input(character, language) for character in text)


class InputLayoutTests(unittest.TestCase):
    def test_opposite_layout_words_follow_physical_keys_in_both_directions(self):
        self.assertEqual(translated("ghbdtn", "ru"), "привет")
        self.assertEqual(translated("руддщ", "en"), "hello")
        self.assertEqual(translated("gривет", "ru"), "привет")
        self.assertEqual(translated("рello", "en"), "hello")

    def test_all_us_letter_keys_map_to_their_russian_physical_positions(self):
        english = "qwertyuiopasdfghjklzxcvbnm"
        russian = "йцукенгшщзфывапролдячсмить"
        self.assertEqual(translated(english, "ru"), russian)
        self.assertEqual(translated(russian, "en"), english)
        self.assertEqual(translated(english.upper(), "ru"), russian.upper())
        self.assertEqual(translated(russian.upper(), "en"), english.upper())

    def test_shift_and_caps_are_preserved_instead_of_masking_case_errors(self):
        self.assertEqual(translated("Ghbdtn", "ru"), "Привет")
        self.assertEqual(translated("Руддщ", "en"), "Hello")
        self.assertEqual(normalize_input("Р", "en"), "H")
        self.assertNotEqual(normalize_input("Р", "en"), "h")

    def test_punctuation_keys_producing_russian_letters_support_shift(self):
        english = "`[];',."
        shifted = '~{}:"<>'
        russian = "ёхъжэбю"
        self.assertEqual(translated(english, "ru"), russian)
        self.assertEqual(translated(shifted, "ru"), russian.upper())
        self.assertEqual(translated(russian, "en"), english)
        self.assertEqual(translated(russian.upper(), "en"), shifted)

    def test_mapping_is_physical_rather_than_transliteration_or_visual_similarity(self):
        for source, expected in (("а", "f"), ("е", "t"), ("р", "h"), ("у", "e")):
            with self.subTest(source=source):
                self.assertEqual(normalize_input(source, "en"), expected)
        self.assertEqual(normalize_input("p", "ru"), "з")

    def test_typographical_errors_remain_errors(self):
        self.assertEqual(translated("ghbdty", "ru"), "привен")
        self.assertNotEqual(translated("ghbdty", "ru"), "привет")
        self.assertEqual(translated("рудду", "en"), "helle")
        self.assertNotEqual(translated("рудду", "en"), "hello")

    def test_native_target_alphabet_is_unchanged_including_uppercase(self):
        alphabets = {
            "en": string.ascii_letters,
            "ru": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        }
        for language, letters in alphabets.items():
            with self.subTest(language=language):
                self.assertEqual(translated(letters, language), letters)
                self.assertEqual(translated(letters.upper(), language), letters.upper())

    def test_controls_digits_spaces_and_unmapped_symbols_are_unchanged(self):
        characters = (
            " \t\n\r\x1b\x03\x04\x0c\x15\x17\x7f0123456789/?\\|!@#$%^&*()-_=+🙂λéشあ"
        )
        for language in ("ru", "en"):
            with self.subTest(language=language):
                self.assertEqual(translated(characters, language), characters)
        self.assertEqual(normalize_input("/", "ru"), "/")
        self.assertEqual(normalize_input(".", "en"), ".")

    def test_empty_or_multiple_character_events_pass_through_unchanged(self):
        for event in ("", "ab", "Ghbdtn", "руддщ", "\x1b[A", "🙂🙂"):
            for language in ("ru", "en"):
                with self.subTest(event=event, language=language):
                    self.assertEqual(normalize_input(event, language), event)

    def test_invalid_language_is_rejected(self):
        for language in ("", "de", "RU"):
            with self.subTest(language=language), self.assertRaises(ValueError):
                normalize_input("a", language)


if __name__ == "__main__":
    unittest.main()
