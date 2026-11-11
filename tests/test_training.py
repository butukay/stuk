"""Exercise training behavior without a terminal or writes to real user data."""

import copy
import curses
import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from stuk.adaptive import generate_practice_text
from stuk.curriculum import ORDERS
from stuk.history import HistoryError, make_record
from stuk.session import TypingSession
from stuk.settings import Settings
from stuk.tui import Trainer


class FakeScreen:
    def __init__(self, rows=32, columns=110):
        self.rows, self.columns = rows, columns
        self.bkgd = Mock()
        self.clearok = Mock()
        self.refresh = Mock()
        self.erase()

    def getmaxyx(self):
        return self.rows, self.columns

    def erase(self):
        self.cells = [[" "] * self.columns for _ in range(self.rows)]

    def addnstr(self, row, column, text, count, style):
        for offset, character in enumerate(text[:count]):
            self.cells[row][column + offset] = character

    def contents(self):
        return "\n".join("".join(row) for row in self.cells)


class FakePalette:
    background, ink, muted, faint, future, accent, error, cursor = range(8)

    def __init__(self):
        self.apply = Mock()
        self.close = Mock()


def weak_history(letter="a"):
    session = TypingSession(letter * 3)
    for index in range(3):
        session.input("z" if letter != "z" else "x", 10 + index * 0.5)
    return [make_record(session, "en", 1)]


def observed_record(language, letters, repetitions=12):
    passage = " ".join(letter * repetitions for letter in letters)
    session = TypingSession(passage)
    for index, character in enumerate(passage):
        session.input(character, 10 + index * 0.2)
    return make_record(session, language, len(letters))


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.load = self.patch("stuk.tui.load_history", return_value=[])
        self.append = self.patch("stuk.tui.append_record")
        self.save = self.patch("stuk.tui.save_settings")
        self.generate = self.patch("stuk.tui.generate_text", return_value="abc")
        self.patch("stuk.tui.Palette", return_value=FakePalette())
        self.patch("stuk.tui.time", SimpleNamespace(monotonic=lambda: self.now))

    def patch(self, target, *arguments, **keywords):
        patcher = patch(target, *arguments, **keywords)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def trainer(self, *, history=None, adaptive=True, text="abc"):
        if history is not None:
            self.load.return_value = copy.deepcopy(history)
        self.generate.return_value = text
        return Trainer(
            FakeScreen(),
            Settings(language="en", words=1, adaptive=adaptive, practice_mode="free"),
        )

    def type_text(self, trainer, text):
        for character in text:
            self.now += 0.25
            self.assertTrue(trainer.handle_key(character))

    def mode_trainer(
        self, *, language="en", mode="guided", history=None, words=25, screen=None
    ):
        self.load.return_value = copy.deepcopy(history or [])
        return Trainer(
            screen or FakeScreen(),
            Settings(language=language, words=words, practice_mode=mode),
        )

    def open_letter_editor(self, trainer):
        trainer.handle_key(curses.KEY_F2)
        for _ in range(6):
            trainer.handle_key(curses.KEY_DOWN)
        trainer.handle_key("\n")
        self.assertTrue(trainer.letters_editing)

    def test_completion_is_saved_once_across_redraw_input_and_progress(self):
        trainer = self.trainer()
        self.type_text(trainer, "abc")
        self.assertTrue(trainer.session.complete)
        self.append.assert_called_once_with(trainer.completed_record)
        first_record = trainer.completed_record
        trainer.draw()
        trainer.draw()
        trainer.handle_key("x")
        trainer.handle_key(curses.KEY_F3)
        trainer.draw()
        trainer.handle_key("\t")
        trainer.draw()
        trainer.handle_key("\x1b")
        trainer.draw()
        self.assertEqual(self.append.call_count, 1)
        self.assertEqual(trainer.history, [first_record])

        trainer.handle_key("\n")
        self.assertFalse(trainer.session.complete)
        self.assertIsNone(trainer.completed_record)
        self.assertEqual(self.append.call_count, 1)
        self.type_text(trainer, "abc")
        self.assertEqual(self.append.call_count, 2)
        self.assertEqual(len(trainer.history), 2)
        self.assertNotEqual(first_record["id"], trainer.completed_record["id"])

    def test_resetting_incomplete_exercise_does_not_save_it(self):
        trainer = self.trainer()
        previous = trainer.session
        self.type_text(trainer, "a")
        trainer.handle_key("\t")
        self.assertIsNot(trainer.session, previous)
        self.assertEqual(trainer.session.typed, "")
        self.assertEqual(trainer.history, [])
        self.assertIsNone(trainer.completed_record)
        self.append.assert_not_called()

    def test_save_failure_keeps_in_memory_progress_and_displays_error(self):
        self.append.side_effect = OSError("read-only data directory")
        trainer = self.trainer()
        self.type_text(trainer, "abc")
        self.assertTrue(trainer.history_error)
        self.assertEqual(trainer.history, [trainer.completed_record])
        trainer.draw()
        self.assertIn("progress could not be saved", trainer.screen.contents())
        self.assertEqual(self.append.call_count, 1)
        trainer.handle_key(curses.KEY_F3)
        trainer.draw()
        self.assertIn("history could not be saved", trainer.screen.contents())
        self.assertEqual(self.append.call_count, 2)
        self.assertTrue(
            all(
                call.args[0] == trainer.completed_record
                for call in self.append.call_args_list
            )
        )
        self.assertEqual(len(trainer.history), 1)

    def test_next_completion_retries_old_record_before_saving_new_record(self):
        persisted = {}

        def store(record):
            if self.append.call_count == 1:
                raise OSError("temporarily unavailable")
            persisted[record["id"]] = record

        self.append.side_effect = store
        trainer = self.trainer()
        self.type_text(trainer, "abc")
        first_record = trainer.completed_record
        self.assertTrue(trainer.history_error)
        self.assertEqual(persisted, {})
        trainer.handle_key("\n")
        self.type_text(trainer, "abc")
        self.assertEqual(
            set(persisted), {first_record["id"], trainer.completed_record["id"]}
        )
        self.assertFalse(trainer.history_error)
        self.assertEqual(len(trainer.history), 2)
        self.assertEqual(self.append.call_count, 3)
        self.assertEqual(self.append.call_args_list[1].args[0], first_record)

    def test_reopening_progress_retries_unsaved_record_without_duplicates(self):
        self.append.side_effect = [OSError("temporarily unavailable"), None]
        trainer = self.trainer()
        self.type_text(trainer, "abc")
        record = trainer.completed_record
        self.assertTrue(trainer.history_error)
        trainer.handle_key(curses.KEY_F3)
        self.assertFalse(trainer.history_error)
        self.assertEqual(self.append.call_count, 2)
        self.assertEqual(self.append.call_args.args[0], record)
        trainer.handle_key(curses.KEY_F3)
        trainer.handle_key(curses.KEY_F3)
        trainer.draw()
        self.assertEqual(self.append.call_count, 2)
        self.assertEqual(trainer.history, [record])

    def test_unreadable_history_does_not_prevent_practice(self):
        self.load.side_effect = HistoryError("damaged history")
        trainer = self.trainer()
        self.assertTrue(trainer.history_error)
        self.assertEqual(trainer.history, [])
        self.type_text(trainer, "a")
        self.assertEqual(trainer.session.typed, "a")

    def test_disabled_adaptive_mode_uses_plain_words_despite_weak_history(self):
        adaptive = self.patch("stuk.tui.adaptive_text", return_value=("air", ("a",)))
        trainer = self.trainer(history=weak_history(), adaptive=False)
        self.generate.assert_called_once_with("en", 1)
        adaptive.assert_not_called()
        self.assertEqual(trainer.session.text, "abc")
        self.assertEqual(trainer.focus, ())

    def test_adaptive_mode_uses_history_and_displays_focus_in_header(self):
        adaptive = self.patch("stuk.tui.adaptive_text", return_value=("air", ("a",)))
        trainer = self.trainer(history=weak_history())
        adaptive.assert_called_once_with("en", 1, trainer.history)
        self.generate.assert_not_called()
        self.assertEqual(trainer.session.text, "air")
        trainer.draw()
        self.assertIn("focus: a", trainer.screen.contents())

    def test_completed_exercise_changes_next_focus_even_when_saving_fails(self):
        adaptive = self.patch("stuk.tui.adaptive_text", return_value=("air", ("a",)))
        self.append.side_effect = OSError("disk unavailable")
        trainer = self.trainer(text="aaa")
        adaptive.assert_not_called()
        self.type_text(trainer, "zzz")
        trainer.handle_key("\n")
        adaptive.assert_called_once_with("en", 1, trainer.history)
        self.assertEqual(trainer.focus, ("a",))
        self.assertEqual(trainer.session.text, "air")

    def test_progress_filter_does_not_change_training_language_or_accept_input(self):
        trainer = self.trainer()
        self.now = 100
        trainer.handle_key("a")
        self.now = 101
        trainer.handle_key(curses.KEY_F3)
        self.assertTrue(trainer.progress_open)
        self.now = 105
        trainer.handle_key("x")
        trainer.handle_key("\t")
        self.assertEqual(trainer.progress_language, "ru")
        self.assertEqual(trainer.settings.language, "en")
        self.assertEqual(trainer.session.typed, "a")
        trainer.draw()
        self.now = 111
        trainer.handle_key("\x1b")
        self.now = 112
        trainer.handle_key("b")
        self.now = 113
        trainer.handle_key("c")
        self.assertTrue(trainer.session.complete)
        self.assertEqual(trainer.completed_record["duration"], 3)
        self.assertEqual(trainer.completed_record["attempts"], 3)
        self.save.assert_not_called()

    def test_adaptive_toggle_in_settings_is_saved_and_resets_passage(self):
        trainer = self.trainer()
        self.type_text(trainer, "a")
        trainer.handle_key(curses.KEY_F2)
        for _ in range(4):
            trainer.handle_key(curses.KEY_DOWN)
        trainer.handle_key(" ")
        self.assertFalse(trainer.settings.adaptive)
        self.assertEqual(trainer.session.typed, "")
        self.save.assert_called_once_with(trainer.settings)
        self.append.assert_not_called()

    def test_guided_cold_start_uses_only_initial_letters_of_selected_language(self):
        practice = self.patch(
            "stuk.tui.generate_practice_text", wraps=generate_practice_text
        )
        for language, order in ORDERS.items():
            with self.subTest(language=language):
                trainer = self.mode_trainer(language=language)
                self.assertEqual(trainer.allowed, order[:6])
                self.assertEqual(
                    set(trainer.session.text.replace(" ", "")), set(order[:6])
                )
                self.assertFalse(trainer.drills)
                self.assertEqual(practice.call_args.kwargs["allowed"], order[:6])
                self.assertIsNone(practice.call_args.kwargs["target"])
                trainer.draw()
                self.assertIn(f"6/{len(order)}", trainer.screen.contents())
        self.generate.assert_not_called()

    def test_guided_stage_passes_newly_unlocked_letter_as_target(self):
        order = ORDERS["en"]
        history = [observed_record("en", order[:6])]
        practice = self.patch(
            "stuk.tui.generate_practice_text", wraps=generate_practice_text
        )
        trainer = self.mode_trainer(history=history)
        self.assertEqual(trainer.allowed, order[:7])
        self.assertEqual(practice.call_args.kwargs["target"], order[6])
        self.assertIn(order[6], trainer.focus)
        self.assertGreaterEqual(
            sum(order[6] in word for word in trainer.session.text.split()), 4
        )

    def test_free_mode_does_not_force_the_guided_alphabet(self):
        practice = self.patch("stuk.tui.generate_practice_text")
        trainer = self.trainer(text="zebra")
        self.assertIsNone(trainer.allowed)
        self.assertEqual(trainer.session.text, "zebra")
        self.assertNotIn("z", ORDERS["en"][:6])
        practice.assert_not_called()
        self.generate.assert_called_once_with("en", 1)

    def test_custom_editor_commits_only_current_language_and_restarts_practice(self):
        trainer = self.trainer()
        original_russian = trainer.settings.custom_letters["ru"]
        self.type_text(trainer, "a")
        self.open_letter_editor(trainer)
        trainer.handle_key("\x15")
        self.type_text(trainer, "Qazq1я")
        trainer.handle_key("\n")
        self.assertFalse(trainer.letters_editing)
        self.assertTrue(trainer.settings_open)
        self.assertEqual(trainer.settings.custom_letters["en"], "qaz")
        self.assertEqual(trainer.settings.custom_letters["ru"], original_russian)
        self.assertEqual(trainer.settings.practice_mode, "custom")
        self.assertEqual(trainer.allowed, "qaz")
        self.assertTrue(set(trainer.session.text) <= set("qaz "))
        self.assertEqual(trainer.session.typed, "")
        self.save.assert_called_once_with(trainer.settings)
        self.append.assert_not_called()

    def test_custom_editor_cancel_preserves_preferences_and_incomplete_session(self):
        trainer = self.trainer()
        previous = trainer.session
        preferences = copy.deepcopy(trainer.settings)
        self.type_text(trainer, "a")
        self.open_letter_editor(trainer)
        trainer.handle_key("\x15")
        self.type_text(trainer, "qz")
        trainer.handle_key("\x1b")
        self.assertFalse(trainer.letters_editing)
        self.assertTrue(trainer.settings_open)
        self.assertEqual(trainer.settings, preferences)
        self.assertIs(trainer.session, previous)
        self.assertEqual(trainer.session.typed, "a")
        self.save.assert_not_called()
        self.append.assert_not_called()

    def test_custom_editor_rejects_empty_alphabet_and_accepts_one_letter(self):
        trainer = self.trainer()
        preferences = copy.deepcopy(trainer.settings)
        self.open_letter_editor(trainer)
        trainer.handle_key("\x15")
        trainer.handle_key("\n")
        self.assertTrue(trainer.letters_editing)
        self.assertTrue(trainer.edit_error)
        self.assertEqual(trainer.settings, preferences)
        trainer.draw()
        self.assertIn("enter a letter", trainer.screen.contents())
        self.save.assert_not_called()
        trainer.handle_key("q")
        trainer.handle_key("\n")
        self.assertFalse(trainer.letters_editing)
        self.assertEqual(trainer.allowed, "q")
        self.assertTrue(trainer.drills)
        self.assertEqual(set(trainer.session.text.replace(" ", "")), {"q"})

    def test_settings_scroll_keeps_last_option_and_hints_inside_small_frame(self):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                trainer = self.mode_trainer(
                    language=language, mode="free", screen=FakeScreen(12, 32)
                )
                trainer.handle_key(curses.KEY_F2)
                for _ in range(6):
                    trainer.handle_key(curses.KEY_DOWN)
                trainer.draw()
                rows = trainer.screen.contents().splitlines()
                selected = next(row for row in rows if "›" in row)
                self.assertIn(trainer.copy["custom_letters"], selected)
                self.assertIn("enter", selected)
                self.assertTrue(selected.strip().startswith("│"))
                self.assertTrue(selected.strip().endswith("│"))
                self.assertIn(trainer.copy["select"], trainer.screen.contents())
                self.assertIn(trainer.copy["back"], trainer.screen.contents())
                self.assertIn("╭", rows[0])
                self.assertIn("╰", rows[-1])

    def test_mode_setting_cycles_without_changing_language_or_custom_letters(self):
        trainer = self.mode_trainer()
        custom = copy.deepcopy(trainer.settings.custom_letters)
        trainer.handle_key(curses.KEY_F2)
        for _ in range(5):
            trainer.handle_key(curses.KEY_DOWN)
        for expected in ("free", "custom", "guided"):
            trainer.handle_key(curses.KEY_RIGHT)
            self.assertEqual(trainer.settings.practice_mode, expected)
            self.assertEqual(trainer.settings.language, "en")
            self.assertEqual(trainer.settings.custom_letters, custom)
        self.assertEqual(self.save.call_count, 3)

    def test_completed_stage_announces_unlock_and_later_errors_do_not_relock_it(self):
        order = ORDERS["en"]
        history = [
            observed_record("en", order[:5]),
            observed_record("en", order[5], repetitions=11),
        ]
        trainer = self.mode_trainer(history=history)
        self.assertEqual(trainer.allowed, order[:6])
        self.type_text(trainer, trainer.session.text)
        self.assertEqual(trainer.course.available, order[:7])
        self.assertIn(f"letter unlocked: {order[6]}", trainer.result_feedback)
        trainer.draw()
        self.assertIn(f"letter unlocked: {order[6]}", trainer.screen.contents())
        trainer.handle_key("\n")
        self.assertEqual(trainer.allowed, order[:7])
        self.type_text(trainer, "z" * len(trainer.session.text))
        trainer.handle_key("\n")
        self.assertEqual(trainer.allowed, order[:7])
        self.assertTrue(set(trainer.session.text) <= set(order[:7] + " "))

    def test_progress_pages_and_language_filter_leave_current_exercise_untouched(self):
        trainer = self.trainer()
        self.type_text(trainer, "a")
        previous = trainer.session
        trainer.handle_key(curses.KEY_F3)
        self.assertEqual(trainer.progress_page, "graphs")
        trainer.handle_key("l")
        self.assertEqual(trainer.progress_page, "letters")
        trainer.draw()
        trainer.handle_key("\t")
        self.assertEqual(trainer.progress_language, "ru")
        trainer.draw()
        trainer.handle_key("g")
        self.assertEqual(trainer.progress_page, "graphs")
        trainer.handle_key("\x1b")
        self.assertIs(trainer.session, previous)
        self.assertEqual(trainer.session.typed, "a")
        self.assertEqual(trainer.settings.language, "en")
        self.save.assert_not_called()
        self.append.assert_not_called()

    def test_opposite_os_layout_completes_both_languages_without_false_errors(self):
        for language, passage, incoming in (
            ("ru", "привет", "ghbdtn"),
            ("en", "hello", "руддщ"),
        ):
            with self.subTest(language=language):
                self.generate.return_value = passage
                trainer = self.mode_trainer(language=language, mode="free", words=1)
                self.type_text(trainer, incoming)
                self.assertTrue(trainer.session.complete)
                self.assertEqual(trainer.session.typed, passage)
                self.assertEqual(trainer.completed_record["language"], language)
                self.assertEqual(trainer.completed_record["accuracy"], 100)
                self.assertEqual(trainer.completed_record["mistakes"], 0)
                self.assertEqual(set(trainer.completed_record["keys"]), set(passage))

    def test_opposite_layout_typo_is_correctable_and_remains_in_expected_key_history(
        self,
    ):
        for language, passage, incorrect, correction, expected_key in (
            ("ru", "привет", "gk", "hbdtn", "р"),
            ("en", "hello", "ро", "уддщ", "e"),
        ):
            with self.subTest(language=language):
                self.generate.return_value = passage
                trainer = self.mode_trainer(language=language, mode="free", words=1)
                self.type_text(trainer, incorrect)
                self.assertEqual(trainer.session.mistakes, 1)
                trainer.handle_key("\x7f")
                self.type_text(trainer, correction)
                self.assertEqual(trainer.session.typed, passage)
                self.assertEqual(trainer.completed_record["mistakes"], 1)
                key = trainer.completed_record["keys"][expected_key]
                self.assertEqual(key["attempts"], 2)
                self.assertEqual(key["mistakes"], 1)
                self.assertLess(trainer.completed_record["accuracy"], 100)

    def test_opposite_layout_uppercase_still_counts_as_a_case_error(self):
        for language, passage, incoming in (
            ("ru", "привет", "Ghbdtn"),
            ("en", "hello", "Руддщ"),
        ):
            with self.subTest(language=language):
                self.generate.return_value = passage
                trainer = self.mode_trainer(language=language, mode="free", words=1)
                self.type_text(trainer, incoming)
                self.assertEqual(trainer.session.typed, passage.capitalize())
                self.assertEqual(trainer.completed_record["mistakes"], 1)
                self.assertEqual(
                    trainer.completed_record["keys"][passage[0]]["mistakes"], 1
                )

    def test_ctrl_l_changes_normalization_language_without_recording_abandoned_text(
        self,
    ):
        trainer = self.trainer(text="hello")
        self.type_text(trainer, "р")
        self.assertEqual(trainer.session.typed, "h")
        self.generate.return_value = "привет"
        trainer.handle_key("\x0c")
        self.assertEqual(trainer.settings.language, "ru")
        self.assertEqual(trainer.session.typed, "")
        self.type_text(trainer, "ghbdtn")
        self.assertEqual(trainer.completed_record["accuracy"], 100)
        self.assertEqual([record["language"] for record in trainer.history], ["ru"])
        self.generate.return_value = "hello"
        trainer.handle_key("\x0c")
        self.type_text(trainer, "руддщ")
        self.assertEqual(trainer.completed_record["accuracy"], 100)
        self.assertEqual(
            [record["language"] for record in trainer.history], ["ru", "en"]
        )
        self.assertEqual(self.append.call_count, 2)
        self.assertEqual(self.save.call_count, 2)

    def test_custom_editor_accepts_physical_keys_from_opposite_layout(self):
        for language, incoming, expected in (
            ("en", "фыва", "asdf"),
            ("ru", "asdf", "фыва"),
            ("ru", "`[];',.", "ёхъжэбю"),
        ):
            with self.subTest(language=language, incoming=incoming):
                trainer = self.mode_trainer(language=language, mode="free", words=1)
                other = "en" if language == "ru" else "ru"
                original_other = trainer.settings.custom_letters[other]
                self.open_letter_editor(trainer)
                trainer.handle_key("\x15")
                self.type_text(trainer, incoming)
                trainer.handle_key("\n")
                self.assertEqual(trainer.settings.custom_letters[language], expected)
                self.assertEqual(trainer.settings.custom_letters[other], original_other)
                self.assertEqual(trainer.allowed, expected)
                self.assertTrue(set(trainer.session.text) <= set(expected + " "))
                self.assertEqual(trainer.session.attempts, 0)
        self.append.assert_not_called()

    def test_menu_aliases_are_not_turned_into_typing_events(self):
        trainer = self.trainer()
        trainer.handle_key(curses.KEY_F2)
        trainer.handle_key("о")
        self.assertEqual(trainer.selected_setting, 1)
        trainer.handle_key("л")
        self.assertEqual(trainer.selected_setting, 0)
        trainer.handle_key(curses.KEY_F3)
        trainer.handle_key("д")
        self.assertEqual(trainer.progress_page, "letters")
        trainer.handle_key("п")
        self.assertEqual(trainer.progress_page, "graphs")
        self.assertEqual(trainer.session.typed, "")
        self.assertEqual(trainer.settings.language, "en")
        self.save.assert_not_called()
        self.append.assert_not_called()

    def test_footer_keeps_quit_then_tab_then_function_keys_at_every_supported_size(
        self,
    ):
        for language in ("en", "ru"):
            for rows, columns in ((32, 110), (12, 32)):
                for complete in (False, True):
                    with self.subTest(
                        language=language, size=(rows, columns), complete=complete
                    ):
                        self.generate.return_value = (
                            "abc" if language == "en" else "дом"
                        )
                        trainer = self.mode_trainer(
                            language=language,
                            mode="free",
                            words=1,
                            screen=FakeScreen(rows, columns),
                        )
                        if complete:
                            self.type_text(trainer, trainer.session.text)
                        trainer.draw()
                        footer = "".join(trainer.screen.cells[rows - 2])
                        keys = re.findall(
                            r"\b(?:esc|tab|f2|f3|f4)\b", footer.casefold()
                        )
                        self.assertEqual(keys, ["esc", "tab", "f2", "f3", "f4"])
                        width = min(68, columns - 8)
                        left = (columns - width) // 2
                        self.assertFalse(footer[:left].strip())
                        self.assertFalse(footer[left + width :].strip())

    def test_f4_restarts_guided_practice_in_the_other_language_without_saving_partial(
        self,
    ):
        trainer = self.mode_trainer(language="en")
        original = trainer.session
        self.type_text(trainer, original.text[0])
        trainer.handle_key(curses.KEY_F4)
        self.assertEqual(trainer.settings.language, "ru")
        self.assertIsNot(trainer.session, original)
        self.assertEqual(trainer.session.typed, "")
        self.assertEqual(trainer.allowed, ORDERS["ru"][:6])
        self.assertTrue(set(trainer.session.text) <= set(ORDERS["ru"][:6] + " "))
        trainer.handle_key(curses.KEY_F4)
        self.assertEqual(trainer.settings.language, "en")
        self.assertEqual(trainer.allowed, ORDERS["en"][:6])
        self.assertEqual(trainer.history, [])
        self.assertEqual(self.save.call_count, 2)
        self.append.assert_not_called()

    def test_f4_custom_practice_uses_the_other_languages_selected_letters(self):
        settings = Settings(
            language="en",
            practice_mode="custom",
            custom_letters={"en": "qz", "ru": "фыва"},
        )
        trainer = Trainer(FakeScreen(), settings)
        self.type_text(trainer, trainer.session.text[0])
        trainer.handle_key(curses.KEY_F4)
        self.assertEqual(settings.language, "ru")
        self.assertEqual(settings.practice_mode, "custom")
        self.assertEqual(settings.custom_letters, {"en": "qz", "ru": "фыва"})
        self.assertEqual(trainer.allowed, "фыва")
        self.assertEqual(trainer.session.typed, "")
        self.assertTrue(set(trainer.session.text) <= set("фыва "))
        self.save.assert_called_once_with(settings)
        self.append.assert_not_called()

    def test_f4_inside_settings_keeps_the_menu_open_and_discards_only_partial_exercise(
        self,
    ):
        trainer = self.trainer()
        self.type_text(trainer, "a")
        trainer.handle_key(curses.KEY_F2)
        self.generate.return_value = "дом"
        trainer.handle_key(curses.KEY_F4)
        self.assertTrue(trainer.settings_open)
        self.assertEqual(trainer.settings.language, "ru")
        self.assertEqual(trainer.session.typed, "")
        trainer.draw()
        self.assertIn("настройки", trainer.screen.contents())
        trainer.handle_key("\x1b")
        self.type_text(trainer, "ljv")
        self.assertTrue(trainer.session.complete)
        self.assertEqual(trainer.completed_record["language"], "ru")
        self.assertEqual(trainer.completed_record["accuracy"], 100)
        self.assertEqual(len(trainer.history), 1)
        self.save.assert_called_once_with(trainer.settings)

    def test_f4_and_ctrl_l_on_progress_change_only_the_view_language(self):
        trainer = self.trainer()
        self.type_text(trainer, "a")
        original = trainer.session
        trainer.handle_key(curses.KEY_F3)
        for page in ("g", "l"):
            trainer.handle_key(page)
            trainer.handle_key(curses.KEY_F4)
            self.assertEqual(trainer.progress_language, "ru")
            trainer.draw()
            trainer.handle_key("\x0c")
            self.assertEqual(trainer.progress_language, "en")
            self.assertEqual(trainer.settings.language, "en")
            self.assertIs(trainer.session, original)
            self.assertEqual(trainer.session.typed, "a")
        self.save.assert_not_called()
        self.append.assert_not_called()

    def test_editor_language_switch_preserves_unsaved_drafts_without_committing_them(
        self,
    ):
        trainer = self.trainer()
        original_letters = copy.deepcopy(trainer.settings.custom_letters)
        self.open_letter_editor(trainer)
        trainer.handle_key("\x15")
        self.type_text(trainer, "qz")
        trainer.handle_key(curses.KEY_F4)
        self.assertTrue(trainer.letters_editing)
        self.assertTrue(trainer.settings_open)
        self.assertEqual(trainer.settings.language, "ru")
        self.assertEqual(trainer.edit_buffer, original_letters["ru"])
        trainer.handle_key("\x15")
        self.type_text(trainer, "asdf")
        self.assertEqual(trainer.edit_buffer, "фыва")
        trainer.handle_key("\x0c")
        self.assertEqual(trainer.settings.language, "en")
        self.assertEqual(trainer.edit_buffer, "qz")
        trainer.handle_key(curses.KEY_F4)
        self.assertEqual(trainer.edit_buffer, "фыва")
        self.assertEqual(trainer.settings.custom_letters, original_letters)
        trainer.handle_key("\x1b")
        self.assertFalse(trainer.letters_editing)
        self.assertTrue(trainer.settings_open)
        self.assertEqual(trainer.settings.custom_letters, original_letters)
        self.assertEqual(trainer.session.attempts, 0)
        self.assertEqual(self.save.call_count, 3)
        self.append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
