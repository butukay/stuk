import unittest

from stuk.session import Keystroke, TypingSession


class TypingSessionTests(unittest.TestCase):
    def test_session_waits_for_first_printable_character(self):
        session = TypingSession("hello")
        self.assertEqual(session.elapsed(100), 0)
        self.assertEqual(session.wpm(100), 0)
        self.assertEqual(session.accuracy, 100)
        self.assertFalse(session.complete)
        self.assertIsNone(session.started_at)

    def test_controls_and_multiple_characters_do_not_start_timer(self):
        session = TypingSession("hello")
        for character in ("", "hi", "\n", "\t", "\x1b", "\x7f"):
            self.assertFalse(session.input(character, 1))
        self.assertEqual(session.attempts, 0)
        self.assertEqual(session.position, 0)
        self.assertIsNone(session.started_at)

    def test_unicode_and_spaces_are_accepted(self):
        session = TypingSession("я ё")
        for now, character in enumerate("я ё"):
            self.assertTrue(session.input(character, now))
        self.assertEqual(session.typed, "я ё")
        self.assertTrue(session.complete)

    def test_wrong_character_advances_and_can_be_corrected(self):
        session = TypingSession("cat")
        session.input("x", 10)
        self.assertEqual(session.position, 1)
        self.assertEqual(session.mistakes, 1)
        self.assertTrue(session.backspace())
        session.input("c", 11)
        self.assertEqual(session.typed, "c")
        self.assertEqual(session.attempts, 2)
        self.assertEqual(session.mistakes, 1)
        self.assertEqual(session.accuracy, 50)

    def test_deleting_all_characters_preserves_original_start(self):
        session = TypingSession("hello")
        session.input("h", 10)
        session.backspace()
        self.assertFalse(session.backspace())
        session.input("h", 20)
        self.assertEqual(session.started_at, 10)
        self.assertEqual(session.elapsed(30), 20)

    def test_completion_freezes_timer_and_ignores_further_input(self):
        session = TypingSession("cat")
        session.input("c", 10)
        session.input("a", 11)
        session.input("t", 12)
        self.assertEqual(session.finished_at, 12)
        self.assertEqual(session.elapsed(100), 2)
        self.assertFalse(session.input("x", 100))
        self.assertFalse(session.backspace())
        self.assertFalse(session.delete_word())
        self.assertEqual(session.typed, "cat")
        self.assertEqual(session.attempts, 3)

    def test_speed_counts_only_currently_correct_characters(self):
        session = TypingSession("cat dog")
        for character in "cat x":
            session.input(character, 10)
        self.assertAlmostEqual(session.wpm(22), 4)
        session.backspace()
        self.assertAlmostEqual(session.wpm(22), 4)
        session.backspace()
        self.assertAlmostEqual(session.wpm(22), 3)

    def test_zero_and_negative_elapsed_time_do_not_divide_by_zero(self):
        session = TypingSession("cat")
        session.input("c", 10)
        self.assertEqual(session.wpm(10), 0)
        self.assertEqual(session.elapsed(9), 0)

    def test_delete_word_removes_partial_word(self):
        session = TypingSession("hello world again")
        for character in "hello wor":
            session.input(character, 10)
        self.assertTrue(session.delete_word())
        self.assertEqual(session.typed, "hello ")
        self.assertEqual(session.attempts, 9)

    def test_delete_word_skips_trailing_spaces(self):
        session = TypingSession("hello world again")
        for character in "hello ":
            session.input(character, 10)
        session.delete_word()
        self.assertEqual(session.typed, "")
        self.assertFalse(session.delete_word())
        self.assertEqual(session.started_at, 10)

    def test_invalid_passages_are_rejected(self):
        for text in ("", "line\nbreak", "\t", None):
            with self.assertRaises(ValueError):
                TypingSession(text)

    def test_pause_before_first_input_does_not_start_or_block_session(self):
        session = TypingSession("hello")
        session.pause(10)
        self.assertEqual(session.elapsed(20), 0)
        self.assertIsNone(session.started_at)
        self.assertTrue(session.input("h", 30))
        self.assertEqual(session.started_at, 30)
        self.assertEqual(session.elapsed(35), 5)

    def test_paused_session_freezes_elapsed_and_resumes_without_changing_start(self):
        session = TypingSession("hello")
        session.input("h", 10)
        session.pause(15)
        self.assertEqual(session.elapsed(100), 5)
        session.resume(105)
        self.assertEqual(session.started_at, 10)
        self.assertEqual(session.elapsed(110), 10)
        self.assertTrue(session.input("e", 110))

    def test_repeated_pause_and_resume_are_idempotent(self):
        session = TypingSession("hello")
        session.resume(1)
        session.input("h", 10)
        session.pause(15)
        session.pause(20)
        self.assertEqual(session.elapsed(30), 5)
        session.resume(25)
        session.resume(30)
        self.assertEqual(session.elapsed(35), 15)

    def test_multiple_pauses_are_excluded_from_speed(self):
        session = TypingSession("hello world")
        for character in "hello":
            session.input(character, 10)
        session.pause(15)
        self.assertAlmostEqual(session.wpm(100), 12)
        session.resume(25)
        session.pause(30)
        session.resume(50)
        self.assertEqual(session.elapsed(52), 12)
        self.assertAlmostEqual(session.wpm(52), 5)

    def test_input_and_editing_are_ignored_while_paused(self):
        session = TypingSession("hello world")
        for character in "hello ":
            session.input(character, 10)
        session.pause(15)
        self.assertFalse(session.input("x", 20))
        self.assertFalse(session.backspace())
        self.assertFalse(session.delete_word())
        self.assertEqual(session.typed, "hello ")
        self.assertEqual(session.attempts, 6)
        self.assertEqual(session.mistakes, 0)
        session.resume(25)
        self.assertTrue(session.backspace())
        self.assertTrue(session.delete_word())

    def test_completion_excludes_pause_and_stays_frozen(self):
        session = TypingSession("cat")
        session.input("c", 10)
        session.pause(12)
        session.resume(20)
        session.input("a", 22)
        session.input("t", 24)
        self.assertEqual(session.elapsed(100), 6)
        self.assertAlmostEqual(session.wpm(100), 6)
        session.pause(101)
        session.resume(200)
        self.assertEqual(session.elapsed(300), 6)
        self.assertEqual(session.finished_at, 24)

    def test_keystrokes_capture_expected_letter_and_corrected_mistakes(self):
        session = TypingSession("cat")
        session.input("x", 10)
        session.backspace()
        session.input("c", 10.4)
        session.input("a", 10.6)
        self.assertEqual(session.keystrokes[0], Keystroke("c", False, None))
        self.assertEqual(session.keystrokes[1].expected, "c")
        self.assertTrue(session.keystrokes[1].correct)
        self.assertAlmostEqual(session.keystrokes[1].interval, 0.4)
        self.assertEqual(session.keystrokes[2].expected, "a")
        self.assertAlmostEqual(session.keystrokes[2].interval, 0.2)

    def test_keystrokes_ignore_idle_time_zero_intervals_and_control_keys(self):
        session = TypingSession("hello world")
        session.input("h", 10)
        session.input("e", 10)
        session.input("\n", 11)
        session.input("l", 14)
        session.input("l", 17)
        session.input("o", 16)
        self.assertEqual(
            [key.interval for key in session.keystrokes],
            [None, None, None, 3, None],
        )

    def test_first_key_after_pause_has_no_latency_sample(self):
        session = TypingSession("hello")
        session.input("h", 10)
        session.pause(10.2)
        self.assertFalse(session.input("e", 11))
        session.resume(20)
        session.input("e", 20.3)
        session.input("l", 20.6)
        self.assertIsNone(session.keystrokes[1].interval)
        self.assertAlmostEqual(session.keystrokes[2].interval, 0.3)

    def test_delete_word_does_not_remove_keystroke_history(self):
        session = TypingSession("hello world")
        for index, character in enumerate("hexlo "):
            session.input(character, index / 5)
        before = list(session.keystrokes)
        session.delete_word()
        self.assertEqual(session.keystrokes, before)
        self.assertFalse(session.keystrokes[2].correct)


if __name__ == "__main__":
    unittest.main()
