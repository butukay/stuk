import unittest

from stuk.theme import (
    COLOR_KEYS,
    THEMES,
    indexed_rgb,
    nearest_color,
    resolve_colors,
    rgb,
    valid_color,
)


class ThemeTests(unittest.TestCase):
    def test_builtin_palettes_are_complete_and_valid(self):
        self.assertEqual(set(THEMES), {"lavender", "terminal", "warm"})
        for name, palette in THEMES.items():
            with self.subTest(theme=name):
                self.assertEqual(set(palette), set(COLOR_KEYS))
                self.assertTrue(all(valid_color(value) for value in palette.values()))

    def test_lavender_matches_desktop_colors(self):
        self.assertEqual(
            resolve_colors(),
            {
                "background": "#16161e",
                "foreground": "#e1dbea",
                "muted": "#8d859e",
                "border": "#38303f",
                "pending": "#746c83",
                "accent": "#c4b5fd",
                "error": "#ed9aaa",
                "cursor_text": "#16161e",
            },
        )

    def test_terminal_theme_inherits_terminal_default_colors(self):
        palette = resolve_colors("terminal")
        self.assertEqual(palette["background"], "default")
        self.assertEqual(palette["foreground"], "default")
        self.assertEqual(palette["accent"], 5)
        self.assertEqual(palette["muted"], 8)

    def test_color_validation_accepts_only_supported_values(self):
        for value in ("#000000", "#FFFFFF", "#aBc123", "default", 0, 15, 255):
            with self.subTest(value=value):
                self.assertTrue(valid_color(value))
        for value in (
            "#fff",
            "#fffffff",
            "ffffff",
            "#00000g",
            "#000000\n",
            "#000000 ",
            " default",
            "DEFAULT",
            "",
            -1,
            256,
            0.0,
            True,
            False,
            None,
            [],
            {},
        ):
            with self.subTest(value=value):
                self.assertFalse(valid_color(value))

    def test_overrides_accept_known_valid_fields_independently(self):
        palette = resolve_colors(
            "warm",
            {
                "accent": "#aBc123",
                "background": "default",
                "foreground": 0,
                "error": True,
                "border": "#bad",
                "unknown": "#ffffff",
            },
        )
        self.assertEqual(palette["accent"], "#aBc123")
        self.assertEqual(palette["background"], "default")
        self.assertEqual(palette["foreground"], 0)
        self.assertEqual(palette["error"], THEMES["warm"]["error"])
        self.assertEqual(palette["border"], THEMES["warm"]["border"])
        self.assertNotIn("unknown", palette)

    def test_resolving_does_not_mutate_builtins_or_overrides(self):
        original = THEMES["lavender"].copy()
        overrides = {"accent": "#000000"}
        palette = resolve_colors(overrides=overrides)
        palette["background"] = "#ffffff"
        self.assertEqual(THEMES["lavender"], original)
        self.assertEqual(overrides, {"accent": "#000000"})
        self.assertIsNot(resolve_colors(), resolve_colors())

    def test_unknown_theme_and_non_dict_overrides_fall_back_safely(self):
        for theme in ("missing", "", None, []):
            with self.subTest(theme=theme):
                self.assertEqual(resolve_colors(theme), THEMES["lavender"])
        self.assertEqual(resolve_colors(overrides=[]), THEMES["lavender"])

    def test_rgb_conversion_preserves_channel_values_and_case(self):
        self.assertEqual(rgb("#000000"), (0, 0, 0))
        self.assertEqual(rgb("#FFFFFF"), (255, 255, 255))
        self.assertEqual(rgb("#aBc123"), (171, 193, 35))

    def test_rgb_rejects_non_hex_color_formats(self):
        for value in ("#abc", "#00000g", "default", 0, None, "#ffffff\n"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    rgb(value)

    def test_indexed_rgb_maps_ansi_cube_and_grayscale_boundaries(self):
        for index, expected in (
            (0, (0, 0, 0)),
            (15, (255, 255, 255)),
            (16, (0, 0, 0)),
            (21, (0, 0, 255)),
            (67, (95, 135, 175)),
            (231, (255, 255, 255)),
            (232, (8, 8, 8)),
            (255, (238, 238, 238)),
        ):
            with self.subTest(index=index):
                self.assertEqual(indexed_rgb(index), expected)

    def test_indexed_rgb_rejects_invalid_indices(self):
        for index in (-1, 256, True, False, 15.0, "15", None):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    indexed_rgb(index)

    def test_xterm_cube_primary_colors_use_fixed_indices(self):
        for color, index in (
            ("#000000", 16),
            ("#ff0000", 196),
            ("#00ff00", 46),
            ("#0000ff", 21),
            ("#ffffff", 231),
            ("#5f87af", 67),
        ):
            with self.subTest(color=color):
                self.assertEqual(nearest_color(color), index)

    def test_xterm_grays_use_nearest_grayscale_not_ansi_colors(self):
        self.assertEqual(nearest_color("#808080"), 244)
        self.assertEqual(nearest_color("#626262"), 241)
        self.assertEqual(nearest_color("#16161e"), 234)

    def test_limited_color_terminals_can_choose_black_and_bright_colors(self):
        for count in (8, 16):
            with self.subTest(count=count):
                self.assertEqual(nearest_color("#000000", count), 0)
                self.assertEqual(nearest_color("#16161e", count), 0)
                self.assertEqual(nearest_color("#800000", count), 1)
        self.assertEqual(nearest_color("#ffffff", 8), 7)
        self.assertEqual(nearest_color("#ffffff", 16), 15)
        self.assertEqual(nearest_color("#ff0000", 16), 9)

    def test_quantization_is_repeatable_and_stays_in_supported_indices(self):
        for palette in THEMES.values():
            for color in palette.values():
                if isinstance(color, str) and color.startswith("#"):
                    for count in (8, 16, 256):
                        result = nearest_color(color, count)
                        self.assertEqual(result, nearest_color(color, count))
                        self.assertGreaterEqual(result, 16 if count == 256 else 0)
                        self.assertLess(result, count)

    def test_unsupported_color_counts_are_rejected(self):
        for count in (0, 1, 88, 255, 257, True, 16.0, "256"):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    nearest_color("#000000", count)


if __name__ == "__main__":
    unittest.main()
