import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stuk.curriculum import ORDERS
from stuk.settings import (
    Settings,
    clean_letters,
    config_path,
    load_settings,
    save_settings,
)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "stuk" / "settings.json"

    def write_json(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_preferences_return_defaults_without_creating_files(self):
        self.assertEqual(load_settings(self.path), Settings())
        self.assertFalse(self.path.parent.exists())

    def test_settings_round_trip(self):
        expected = Settings(
            language="en",
            words=50,
            show_keyboard=True,
            adaptive=False,
            practice_mode="custom",
            custom_letters={"en": "qaz", "ru": "фыва"},
            theme="warm",
            colors={"accent": "#ABCDEF", "background": "default", "border": 238},
        )
        save_settings(expected, self.path)
        self.assertEqual(load_settings(self.path), expected)
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            {
                "language": "en",
                "words": 50,
                "show_keyboard": True,
                "adaptive": False,
                "practice_mode": "custom",
                "custom_letters": {"en": "qaz", "ru": "фыва"},
                "theme": "warm",
                "colors": {
                    "accent": "#ABCDEF",
                    "background": "default",
                    "border": 238,
                },
            },
        )
        self.assertTrue(self.path.read_text(encoding="utf-8").endswith("\n"))

    def test_existing_settings_are_replaced_without_temporary_files_left(self):
        save_settings(Settings(), self.path)
        save_settings(Settings(language="en"), self.path)
        self.assertEqual(load_settings(self.path).language, "en")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_replace_preserves_existing_settings_and_removes_tempfile(self):
        save_settings(Settings(), self.path)
        original = self.path.read_bytes()
        with patch("stuk.settings.os.replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                save_settings(Settings(language="en"), self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_new_config_directories_and_file_are_private(self):
        target = self.root / "new" / "nested" / "settings.json"
        save_settings(Settings(), target)
        for directory in (target.parent, target.parent.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_corrupt_or_non_utf8_preferences_return_defaults(self):
        self.path.parent.mkdir()
        for contents in (b"{invalid json", b"\xff\xfe"):
            self.path.write_bytes(contents)
            self.assertEqual(load_settings(self.path), Settings())

    def test_non_object_preferences_return_defaults(self):
        for value in (None, [], ["en"], "en", 25, True):
            with self.subTest(value=value):
                self.write_json(value)
                self.assertEqual(load_settings(self.path), Settings())

    def test_invalid_fields_do_not_discard_other_valid_fields(self):
        self.write_json({"language": "en", "words": 0, "show_keyboard": True})
        self.assertEqual(load_settings(self.path), Settings("en", 25, True))
        self.write_json({"language": "xx", "words": 60, "show_keyboard": True})
        self.assertEqual(load_settings(self.path), Settings("ru", 60, True))

    def test_word_count_validation_is_strict(self):
        for value in (0, 61, -1, True, False, 25.0, "25", None, [], {}):
            with self.subTest(value=value):
                self.write_json({"words": value})
                self.assertEqual(load_settings(self.path).words, 25)
        for value in (1, 60):
            self.write_json({"words": value})
            self.assertEqual(load_settings(self.path).words, value)

    def test_keyboard_validation_requires_json_boolean(self):
        for value in (1, 0, "true", None, [], {}):
            with self.subTest(value=value):
                self.write_json({"show_keyboard": value})
                self.assertFalse(load_settings(self.path).show_keyboard)
        for value in (True, False):
            self.write_json({"show_keyboard": value})
            self.assertEqual(load_settings(self.path).show_keyboard, value)

    def test_adaptive_validation_requires_json_boolean(self):
        for value in (1, 0, "true", "false", None, [], {}):
            with self.subTest(value=value):
                self.write_json({"adaptive": value})
                self.assertTrue(load_settings(self.path).adaptive)
        for value in (True, False):
            with self.subTest(value=value):
                self.write_json({"adaptive": value})
                self.assertEqual(load_settings(self.path).adaptive, value)

    def test_invalid_adaptive_setting_preserves_other_preferences(self):
        self.write_json(
            {
                "language": "en",
                "words": 50,
                "show_keyboard": True,
                "adaptive": "false",
                "theme": "warm",
                "colors": {"accent": "#abcdef"},
            }
        )
        self.assertEqual(
            load_settings(self.path),
            Settings(
                language="en",
                words=50,
                show_keyboard=True,
                theme="warm",
                colors={"accent": "#abcdef"},
            ),
        )

    def test_legacy_preferences_enable_adaptive_without_changing_existing_fields(self):
        self.write_json({"language": "en", "words": 25, "show_keyboard": True})
        settings = load_settings(self.path)
        self.assertTrue(settings.adaptive)
        self.assertEqual(
            (settings.language, settings.words, settings.show_keyboard),
            ("en", 25, True),
        )

    def test_known_practice_modes_are_loaded(self):
        for mode in ("guided", "free", "custom"):
            with self.subTest(mode=mode):
                self.write_json({"practice_mode": mode})
                self.assertEqual(load_settings(self.path).practice_mode, mode)

    def test_invalid_practice_mode_preserves_other_preferences(self):
        for mode in ("FREE", "unknown", "", None, True, 1, [], {}):
            with self.subTest(mode=mode):
                self.write_json(
                    {
                        "practice_mode": mode,
                        "language": "en",
                        "words": 50,
                        "adaptive": False,
                        "custom_letters": {"en": "qaz"},
                    }
                )
                settings = load_settings(self.path)
                self.assertEqual(settings.practice_mode, "guided")
                self.assertEqual(settings.language, "en")
                self.assertEqual(settings.words, 50)
                self.assertFalse(settings.adaptive)
                self.assertEqual(settings.custom_letters["en"], "qaz")

    def test_custom_alphabets_lowercase_filter_and_deduplicate_in_user_order(self):
        self.write_json(
            {
                "practice_mode": "custom",
                "custom_letters": {
                    "en": " Q A z q Ё я 123 ",
                    "ru": "Ф Ы в А ф Q1",
                    "de": "abc",
                },
            }
        )
        self.assertEqual(
            load_settings(self.path).custom_letters, {"en": "qaz", "ru": "фыва"}
        )
        self.assertEqual(clean_letters("a A z B a", "en"), "azb")
        self.assertEqual(clean_letters("Ё ё Я т я", "ru"), "ёят")

    def test_invalid_custom_language_field_does_not_discard_valid_other_language(self):
        for invalid in ("", "123 !", "english", None, True, 12, [], {}):
            with self.subTest(invalid=invalid):
                self.write_json({"custom_letters": {"en": "qaz", "ru": invalid}})
                self.assertEqual(
                    load_settings(self.path).custom_letters,
                    {
                        "en": "qaz",
                        "ru": ORDERS["ru"][:6],
                    },
                )
        self.write_json({"custom_letters": {"ru": "фыва"}})
        self.assertEqual(
            load_settings(self.path).custom_letters,
            {
                "en": ORDERS["en"][:6],
                "ru": "фыва",
            },
        )

    def test_non_object_custom_alphabets_fall_back_to_starter_letters(self):
        for invalid in (None, [], ["qaz"], "qaz", 25, True):
            with self.subTest(invalid=invalid):
                self.write_json({"custom_letters": invalid})
                self.assertEqual(
                    load_settings(self.path).custom_letters,
                    {language: order[:6] for language, order in ORDERS.items()},
                )

    def test_custom_alphabet_dict_is_not_shared_between_settings_instances(self):
        first, second = Settings(), Settings()
        first.custom_letters["en"] = "qaz"
        self.assertEqual(second.custom_letters["en"], ORDERS["en"][:6])

    def test_old_configuration_preserves_existing_choices_when_course_is_added(self):
        self.write_json(
            {
                "language": "en",
                "words": 50,
                "show_keyboard": True,
                "adaptive": False,
                "theme": "warm",
                "colors": {"accent": "#c4b5fd"},
            }
        )
        settings = load_settings(self.path)
        self.assertEqual(
            settings,
            Settings(
                language="en",
                words=50,
                show_keyboard=True,
                adaptive=False,
                theme="warm",
                colors={"accent": "#c4b5fd"},
            ),
        )
        self.assertEqual(settings.practice_mode, "guided")
        self.assertEqual(
            settings.custom_letters,
            {language: order[:6] for language, order in ORDERS.items()},
        )

    def test_language_validation_and_unknown_fields(self):
        for value in ("RU", "de", 1, None, [], {}):
            with self.subTest(value=value):
                self.write_json({"language": value, "theme": "anything"})
                self.assertEqual(load_settings(self.path), Settings())

    def test_preferences_from_before_themes_keep_existing_choices(self):
        self.write_json({"language": "en", "words": 25, "show_keyboard": True})
        self.assertEqual(
            load_settings(self.path),
            Settings(language="en", words=25, show_keyboard=True),
        )

    def test_known_themes_are_loaded(self):
        for theme in ("lavender", "terminal", "warm"):
            with self.subTest(theme=theme):
                self.write_json({"theme": theme})
                self.assertEqual(load_settings(self.path).theme, theme)

    def test_invalid_theme_does_not_discard_preferences_or_valid_colors(self):
        for theme in ("unknown", "WARM", "", None, True, 1, [], {}):
            with self.subTest(theme=theme):
                self.write_json(
                    {
                        "language": "en",
                        "words": 50,
                        "show_keyboard": True,
                        "theme": theme,
                        "colors": {"accent": "#c4b5fd"},
                    }
                )
                self.assertEqual(
                    load_settings(self.path),
                    Settings(
                        language="en",
                        words=50,
                        show_keyboard=True,
                        colors={"accent": "#c4b5fd"},
                    ),
                )

    def test_color_overrides_are_validated_independently(self):
        self.write_json(
            {
                "theme": "terminal",
                "colors": {
                    "background": "default",
                    "foreground": "#E1DBEA",
                    "muted": 244,
                    "border": "not a color",
                    "pending": 0,
                    "accent": "#c4b5fd",
                    "error": True,
                    "cursor_text": 255,
                    "unknown": "#ffffff",
                },
            }
        )
        actual = load_settings(self.path)
        self.assertEqual(actual.theme, "terminal")
        self.assertEqual(
            actual.colors,
            {
                "background": "default",
                "foreground": "#E1DBEA",
                "muted": 244,
                "pending": 0,
                "accent": "#c4b5fd",
                "cursor_text": 255,
            },
        )

    def test_invalid_color_values_including_booleans_are_rejected(self):
        for value in (
            -1,
            256,
            True,
            False,
            12.0,
            None,
            [],
            {},
            "#fff",
            "#12345g",
            "123456",
            "#01234567",
            "DEFAULT",
            "white",
            "\x1b[31m",
        ):
            with self.subTest(value=value):
                self.write_json({"theme": "warm", "colors": {"accent": value}})
                actual = load_settings(self.path)
                self.assertEqual(actual.theme, "warm")
                self.assertEqual(actual.colors, {})

    def test_non_object_colors_do_not_discard_other_fields(self):
        for colors in (None, [], ["#ffffff"], "#ffffff", 25, True):
            with self.subTest(colors=colors):
                self.write_json({"language": "en", "colors": colors})
                self.assertEqual(load_settings(self.path), Settings(language="en"))

    def test_color_overrides_are_not_shared_between_settings_instances(self):
        first, second = Settings(), Settings()
        first.colors["accent"] = "#ffffff"
        self.assertEqual(second.colors, {})

    def test_example_palette_loads_without_rejecting_any_fields(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "settings.json"
        values = json.loads(example.read_text(encoding="utf-8"))
        actual = load_settings(example)
        self.assertEqual(actual.theme, "lavender")
        self.assertEqual(actual.colors, values["colors"])
        self.assertEqual(actual.language, "ru")
        self.assertEqual(actual.words, 25)
        self.assertFalse(actual.show_keyboard)

    def test_absolute_xdg_path_takes_precedence(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "custom")}):
            self.assertEqual(
                config_path(), self.root / "custom" / "stuk" / "settings.json"
            )

    def test_empty_relative_or_missing_xdg_path_uses_home(self):
        expected = self.root / ".config" / "stuk" / "settings.json"
        for value in ("", "relative/config", "~/config"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"XDG_CONFIG_HOME": value}):
                    with patch("stuk.settings.Path.home", return_value=self.root):
                        self.assertEqual(config_path(), expected)
        with patch.dict(os.environ, {}, clear=True):
            with patch("stuk.settings.Path.home", return_value=self.root):
                self.assertEqual(config_path(), expected)

    def test_default_path_is_resolved_when_called(self):
        with patch("stuk.settings.config_path", return_value=self.path):
            save_settings(Settings(language="en"))
            self.assertEqual(load_settings().language, "en")


if __name__ == "__main__":
    unittest.main()
