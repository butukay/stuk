"""Check visible trends and boundary behavior rather than renderer internals."""

import unittest

from stuk.charts import line_chart


def pixels(chart):
    """Decode Unicode's documented braille dot positions for visual assertions."""
    positions = ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3))
    result = set()
    for row, text in enumerate(chart):
        for column, character in enumerate(text):
            if character == " ":
                continue
            bits = ord(character) - 0x2800
            for bit, (x, y) in enumerate(positions):
                if bits & (1 << bit):
                    result.add((column * 2 + x, row * 4 + y))
    return result


class LineChartTests(unittest.TestCase):
    def test_empty_history_returns_exact_blank_rectangle(self):
        self.assertEqual(line_chart([], 5, 3), ("     ",) * 3)

    def test_output_dimensions_and_characters_are_terminal_safe(self):
        chart = line_chart([10, 35, 20, 60], 17, 4)
        self.assertIsInstance(chart, tuple)
        self.assertEqual(len(chart), 4)
        self.assertTrue(all(len(row) == 17 for row in chart))
        self.assertTrue(
            all(
                character == " " or 0x2800 <= ord(character) <= 0x28FF
                for row in chart
                for character in row
            )
        )

    def test_single_point_sits_at_latest_right_edge(self):
        chart = line_chart([50], 3, 2, minimum=0, maximum=100)
        self.assertEqual(pixels(chart), {(5, 4)})

    def test_tiny_chart_still_contains_a_point(self):
        chart = line_chart([0], 1, 1, minimum=0, maximum=100)
        self.assertEqual(len(chart), 1)
        self.assertEqual(len(chart[0]), 1)
        self.assertEqual(pixels(chart), {(1, 3)})

    def test_constant_series_draws_a_connected_horizontal_line(self):
        drawn = pixels(line_chart([50] * 4, 7, 3, minimum=0, maximum=100))
        self.assertEqual({y for _, y in drawn}, {6})
        self.assertEqual({x for x, _ in drawn}, set(range(14)))

    def test_automatic_scale_centers_a_constant_series(self):
        drawn = pixels(line_chart([20, 20], 5, 3))
        self.assertEqual(len({y for _, y in drawn}), 1)
        self.assertTrue(all(0 < y < 11 for _, y in drawn))

    def test_peak_and_latest_endpoint_are_visible_on_fixed_accuracy_scale(self):
        drawn = pixels(line_chart([0, 100, 0], 5, 3, minimum=0, maximum=100))
        self.assertIn((0, 11), drawn)
        self.assertIn((4, 0), drawn)
        self.assertIn((9, 11), drawn)
        self.assertEqual({x for x, _ in drawn}, set(range(10)))

    def test_long_history_retains_the_exact_latest_observation(self):
        values = [0] * 999 + [100]
        drawn = pixels(line_chart(values, 4, 2, minimum=0, maximum=100))
        self.assertIn((7, 0), drawn)
        self.assertIn((0, 7), drawn)
        self.assertIn((6, 7), drawn)

    def test_downsampling_keeps_the_statistical_direction_of_a_long_trend(self):
        drawn = pixels(line_chart(list(range(1000)), 7, 4, minimum=0, maximum=1000))
        left = [y for x, y in drawn if x < 4]
        right = [y for x, y in drawn if x > 9]
        self.assertGreater(sum(left) / len(left), sum(right) / len(right) + 7)
        self.assertIn((13, 0), drawn)

    def test_explicit_bounds_clip_outliers_without_leaving_the_grid(self):
        drawn = pixels(line_chart([-50, 150], 4, 2, minimum=0, maximum=100))
        self.assertIn((0, 7), drawn)
        self.assertIn((7, 0), drawn)
        self.assertTrue(all(0 <= x < 8 and 0 <= y < 8 for x, y in drawn))

    def test_wpm_zero_baseline_and_zero_series_do_not_divide_by_zero(self):
        drawn = pixels(line_chart([0, 0, 0], 4, 2, minimum=0))
        self.assertEqual({y for _, y in drawn}, {7})

    def test_invalid_dimensions_and_nonfinite_values_raise_value_error(self):
        for width, height in ((0, 2), (2, 0), (-1, 3), (2.5, 2), (True, 2)):
            with (
                self.subTest(width=width, height=height),
                self.assertRaises(ValueError),
            ):
                line_chart([1], width, height)
        for value in (float("nan"), float("inf"), -float("inf"), None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                line_chart([value], 4, 2)

    def test_invalid_explicit_scales_raise_value_error(self):
        for low, high in ((10, 10), (20, 10), (float("nan"), 100), (0, float("inf"))):
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                line_chart([50], 4, 2, minimum=low, maximum=high)


if __name__ == "__main__":
    unittest.main()
