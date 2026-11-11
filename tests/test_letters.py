import copy
import unittest

from stuk.adaptive import ALPHABETS
from stuk.curriculum import ORDERS, curriculum_state
from stuk.letters import COPY, render_letters

SIZES = ((12, 32), (22, 46), (24, 80), (32, 110))


def lesson(language, letters):
    return {
        "language": language,
        "keys": {
            letter: {
                "attempts": 12,
                "mistakes": 0,
                "interval_total": 2.0,
                "interval_count": 5,
            }
            for letter in letters
        },
    }


def content_text(segments):
    return "\n".join(segment.text for segment in segments if segment.role != "faint")


class LetterRenderingTests(unittest.TestCase):
    def histories(self, language):
        order = ORDERS[language]
        return ([], [lesson(language, order[:6])], [lesson(language, order)])

    def test_all_supported_sizes_keep_segments_in_bounds_and_content_separate(self):
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                for history in self.histories(language):
                    for mode in ("guided", "free", "custom"):
                        for error in (False, True):
                            with self.subTest(
                                size=(rows, columns),
                                language=language,
                                mode=mode,
                                records=len(history),
                                error=error,
                            ):
                                segments = render_letters(
                                    history,
                                    language,
                                    rows,
                                    columns,
                                    practice_mode=mode,
                                    custom_letters=ALPHABETS[language][:4],
                                    error=error,
                                )
                                occupied = set()
                                top = next(
                                    s for s in segments if s.text.startswith("╭")
                                )
                                bottom = next(
                                    s for s in segments if s.text.startswith("╰")
                                )
                                left, right = top.x, top.x + len(top.text) - 1
                                for segment in segments:
                                    self.assertGreaterEqual(segment.y, 0)
                                    self.assertLess(segment.y, rows)
                                    self.assertGreaterEqual(segment.x, 0)
                                    self.assertLessEqual(
                                        segment.x + len(segment.text), columns
                                    )
                                    if segment.role == "faint":
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
                                        self.assertNotEqual(segment.y, bottom.y)
                                        self.assertTrue(
                                            all(
                                                left < column < right
                                                for _, column in cells
                                            )
                                        )

    def test_empty_history_shows_starter_availability_and_next_letter(self):
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                with self.subTest(size=(rows, columns), language=language):
                    segments = render_letters([], language, rows, columns)
                    text = content_text(segments)
                    self.assertIn(f"6/{len(ALPHABETS[language])}", text)
                    self.assertIn(f"{COPY[language]['mastered']}: 0/", text)
                    self.assertIn(f": {ORDERS[language][6]}", text)
                    self.assertIn(COPY[language]["guided"], text)
                    self.assertIn("—", text)

    def test_every_mastered_letter_is_explicitly_listed_at_every_supported_size(self):
        for language in ("ru", "en"):
            history = [lesson(language, ORDERS[language])]
            for rows, columns in SIZES:
                with self.subTest(language=language, size=(rows, columns)):
                    segments = render_letters(history, language, rows, columns)
                    label_y = next(
                        segment.y
                        for segment in segments
                        if segment.text.startswith(COPY[language]["mastered"] + ":")
                    )
                    listed = [
                        segment
                        for segment in segments
                        if segment.role == "accent" and segment.y > label_y
                    ]
                    visible = "".join(
                        segment.text.replace(" ", "") for segment in listed
                    )
                    self.assertEqual(visible, ORDERS[language])
                    self.assertIn(
                        COPY[language]["all_mastered"], content_text(segments)
                    )
                    self.assertLessEqual(len(listed), 3)

    def test_partial_mastery_is_shown_as_actual_letters_not_only_a_counter(self):
        for language in ("ru", "en"):
            order = ORDERS[language]
            segments = render_letters([lesson(language, order[:6])], language, 12, 32)
            self.assertIn(" ".join(order[:6]), content_text(segments))
            self.assertIn(f": {order[7]}", content_text(segments))

    def test_full_alphabet_grid_uses_roles_for_mastered_available_and_locked(self):
        for language in ("ru", "en"):
            order = ORDERS[language]
            history = [lesson(language, order[:2])]
            segments = render_letters(history, language, 24, 80)
            grid = {
                segment.text: segment.role
                for segment in segments
                if len(segment.text) == 1 and segment.text in ALPHABETS[language]
            }
            self.assertEqual(set(grid), set(ALPHABETS[language]))
            for letter in order[:2]:
                self.assertEqual(grid[letter], "accent")
            for letter in order[2:6]:
                self.assertEqual(grid[letter], "ink")
            for letter in order[6:]:
                self.assertEqual(grid[letter], "future")

    def test_free_and_custom_modes_show_actual_allowed_counts(self):
        for language in ("ru", "en"):
            total = len(ALPHABETS[language])
            for mode, custom, count in (
                ("free", None, total),
                ("custom", ALPHABETS[language][:4], 4),
            ):
                with self.subTest(language=language, mode=mode):
                    segments = render_letters(
                        [], language, 24, 80, practice_mode=mode, custom_letters=custom
                    )
                    text = content_text(segments)
                    self.assertIn(
                        f"{COPY[language]['available']}: {count}/{total}", text
                    )
                    self.assertIn(COPY[language][mode], text)
                    self.assertIn(COPY[language]["milestone"], text)
                    grid = {
                        s.text: s.role
                        for s in segments
                        if len(s.text) == 1 and s.text in ALPHABETS[language]
                    }
                    allowed = ALPHABETS[language] if mode == "free" else custom
                    for letter in ALPHABETS[language]:
                        self.assertEqual(
                            grid[letter], "ink" if letter in allowed else "future"
                        )

    def test_all_letters_open_is_distinct_from_all_letters_mastered(self):
        for language in ("ru", "en"):
            order = ORDERS[language]
            history = [lesson(language, order[:-1])]
            self.assertEqual(curriculum_state(history, language).available, order)
            self.assertNotEqual(curriculum_state(history, language).mastered, order)
            for rows, columns in SIZES:
                segments = render_letters(history, language, rows, columns)
                text = content_text(segments)
                self.assertIn(COPY[language]["all_open"], text)
                self.assertNotIn(COPY[language]["all_mastered"], text)

    def test_error_and_navigation_remain_visible_on_every_supported_size(self):
        for rows, columns in SIZES:
            for language in ("ru", "en"):
                segments = render_letters([], language, rows, columns, error=True)
                self.assertTrue(any(s.role == "error" for s in segments))
                text = content_text(segments)
                for key in ("↑↓", "tab", "esc"):
                    self.assertIn(key, text)

    def test_other_language_history_does_not_grant_mastery(self):
        segments = render_letters([lesson("ru", ORDERS["ru"])], "en", 24, 80)
        self.assertIn("mastered: 0/26", content_text(segments))
        self.assertIn("available: 6/26", content_text(segments))

    def test_rendering_does_not_mutate_history_or_custom_letters(self):
        history = [lesson("en", ORDERS["en"][:6]), lesson("ru", ORDERS["ru"][:6])]
        original = copy.deepcopy(history)
        for language in ("ru", "en"):
            render_letters(
                history, language, 24, 80, practice_mode="custom", custom_letters="aabb"
            )
        self.assertEqual(history, original)


if __name__ == "__main__":
    unittest.main()
