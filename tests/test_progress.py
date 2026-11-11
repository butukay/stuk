import copy
import unittest

from stuk.progress import COPY, render_progress

SIZES = ((12, 32), (22, 46), (24, 80), (32, 110))


def exercise(language="en", wpm=42, accuracy=98, duration=30):
    letter = "a" if language == "en" else "а"
    return {
        "language": language,
        "duration": duration,
        "wpm": wpm,
        "accuracy": accuracy,
        "keys": {
            letter: {
                "attempts": 20,
                "mistakes": 0,
                "interval_total": 2.0,
                "interval_count": 10,
            }
        },
    }


def braille_cells(segments):
    return [
        (segment.y, segment.x + offset, character)
        for segment in segments
        for offset, character in enumerate(segment.text)
        if "\u2801" <= character <= "\u28ff"
    ]


class ProgressRenderingTests(unittest.TestCase):
    def test_segments_stay_inside_supported_terminal_sizes(self):
        populated = [
            exercise("en" if index % 2 else "ru", 20 + index % 70, 90 + index % 11)
            for index in range(80)
        ]
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                for history in ([], [exercise(language)], populated):
                    for error in (False, True):
                        with self.subTest(
                            size=(rows, columns),
                            language=language,
                            records=len(history),
                            error=error,
                        ):
                            segments = render_progress(
                                history, language, rows, columns, error=error
                            )
                            self.assertTrue(segments)
                            for segment in segments:
                                self.assertGreaterEqual(segment.y, 0)
                                self.assertLess(segment.y, rows)
                                self.assertGreaterEqual(segment.x, 0)
                                self.assertLess(segment.x, columns)
                                self.assertLessEqual(
                                    segment.x + len(segment.text), columns
                                )

    def test_content_preserves_frame_and_does_not_overlap_other_content(self):
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                for history in ([], [exercise(language)] * 40):
                    with self.subTest(
                        size=(rows, columns),
                        language=language,
                        records=len(history),
                    ):
                        segments = render_progress(
                            history, language, rows, columns, error=True
                        )
                        top = next(s for s in segments if s.text.startswith("╭"))
                        bottom = next(s for s in segments if s.text.startswith("╰"))
                        left, right = top.x, top.x + len(top.text) - 1
                        occupied = set()
                        for segment in segments:
                            is_frame = segment.role == "faint" and (
                                segment.y in (top.y, bottom.y)
                                or (segment.text == "│" and segment.x in (left, right))
                            )
                            if is_frame:
                                continue
                            cells = {
                                (segment.y, column)
                                for column in range(
                                    segment.x, segment.x + len(segment.text)
                                )
                            }
                            self.assertFalse(cells & occupied, segment)
                            occupied.update(cells)
                            if top.y < segment.y <= bottom.y:
                                self.assertTrue(
                                    all(left < column < right for _, column in cells),
                                    segment,
                                )
                                self.assertNotEqual(segment.y, bottom.y)

    def test_empty_history_explains_how_to_start_without_a_fabricated_trend(self):
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                with self.subTest(size=(rows, columns), language=language):
                    segments = render_progress([], language, rows, columns)
                    text = "\n".join(segment.text for segment in segments)
                    self.assertIn(COPY[language]["empty"], text)
                    self.assertIn(COPY[language]["start"], text)
                    self.assertFalse(braille_cells(segments))
                    self.assertFalse(any(s.role == "accent" for s in segments))

    def test_single_exercise_shows_one_point_per_metric_at_the_right_edge(self):
        for language in ("ru", "en"):
            for rows, columns in SIZES:
                with self.subTest(size=(rows, columns), language=language):
                    segments = render_progress(
                        [exercise(language)], language, rows, columns
                    )
                    points = braille_cells(segments)
                    self.assertEqual(len(points), 2)
                    for _, _, character in points:
                        self.assertEqual((ord(character) - 0x2800).bit_count(), 1)
                    for segment in segments:
                        if any("\u2801" <= char <= "\u28ff" for char in segment.text):
                            self.assertTrue("\u2801" <= segment.text[-1] <= "\u28ff")

    def test_selected_language_controls_summary_metrics_and_mastery_total(self):
        history = [exercise("ru", 11)] * 3 + [exercise("en", 73, 95)] * 2
        english = "\n".join(
            segment.text for segment in render_progress(history, "en", 24, 80)
        )
        russian = "\n".join(
            segment.text for segment in render_progress(history, "ru", 24, 80)
        )
        self.assertIn("2 exercises", english)
        self.assertIn("73 wpm", english)
        self.assertIn("95%", english)
        self.assertIn("1/26", english)
        self.assertNotIn("11 слов/мин", english)
        self.assertIn("3 упражнений", russian)
        self.assertIn("11 слов/мин", russian)
        self.assertIn("1/33", russian)
        self.assertNotIn("73 wpm", russian)

    def test_other_language_only_history_is_truthfully_empty(self):
        segments = render_progress([exercise("ru")], "en", 24, 80)
        self.assertIn(
            COPY["en"]["empty"], "\n".join(segment.text for segment in segments)
        )
        self.assertFalse(braille_cells(segments))

    def test_charts_label_recent_window_without_discarding_total_count(self):
        history = [exercise("en", 20 + index) for index in range(35)]
        text = "\n".join(
            segment.text for segment in render_progress(history, "en", 24, 80)
        )
        self.assertIn("35 exercises", text)
        self.assertIn("latest 30 / 35", text)
        self.assertIn("#6", text)
        self.assertIn("#35", text)
        self.assertIn("54 wpm", text)

    def test_unsaved_history_error_is_visible_even_on_smallest_screen(self):
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                for history in ([], [exercise(language)]):
                    with self.subTest(
                        size=(rows, columns),
                        language=language,
                        records=len(history),
                    ):
                        segments = render_progress(
                            history, language, rows, columns, error=True
                        )
                        errors = [s for s in segments if s.role == "error"]
                        self.assertTrue(errors)
                        self.assertTrue(
                            any(
                                COPY[language]["unsaved"].startswith(segment.text)
                                for segment in errors
                            )
                        )

    def test_rendering_never_mutates_history_or_nested_key_statistics(self):
        history = [exercise("ru"), exercise("en", 73, 95)]
        original = copy.deepcopy(history)
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                render_progress(history, language, rows, columns, error=True)
        self.assertEqual(history, original)


if __name__ == "__main__":
    unittest.main()
