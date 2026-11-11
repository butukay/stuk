import copy
import unittest
from dataclasses import FrozenInstanceError

from stuk.adaptive import ALPHABETS, KeySkill, mastery, skills_for
from stuk.curriculum import ORDERS, curriculum_state, mastered_letters


def lesson(letters, language="en", attempts=12, mistakes=0, intervals=5, mean=0.4):
    return {
        "language": language,
        "keys": {
            letter: {
                "attempts": attempts,
                "mistakes": mistakes,
                "interval_total": intervals * mean,
                "interval_count": intervals,
            }
            for letter in letters
        },
    }


class CurriculumTests(unittest.TestCase):
    def test_orders_contain_each_language_letter_once(self):
        for language, order in ORDERS.items():
            with self.subTest(language=language):
                self.assertEqual(set(order), set(ALPHABETS[language]))
                self.assertEqual(len(order), len(set(order)))

    def test_new_profiles_start_with_six_available_letters(self):
        for language, starter in (("en", "enirat"), ("ru", "енотас")):
            with self.subTest(language=language):
                state = curriculum_state([], language)
                self.assertEqual(state.available, starter)
                self.assertEqual(state.mastered, "")
                self.assertEqual(state.next_letter, ORDERS[language][6])
                self.assertEqual(state.total, len(ORDERS[language]))
                with self.assertRaises(FrozenInstanceError):
                    state.available = "anything"

    def test_next_letter_unlocks_only_after_all_current_letters_are_mastered(self):
        for language, order in ORDERS.items():
            with self.subTest(language=language):
                history = [lesson(order[:5], language)]
                self.assertEqual(
                    curriculum_state(history, language).available, order[:6]
                )
                history.append(lesson(order[5], language))
                state = curriculum_state(history, language)
                self.assertEqual(state.available, order[:7])
                self.assertEqual(state.mastered, order[:6])
                self.assertEqual(state.next_letter, order[7])
                history.append(lesson(order[6], language))
                self.assertEqual(
                    curriculum_state(history, language).available, order[:8]
                )

    def test_confidence_thresholds_match_existing_mastery(self):
        cases = (
            (KeySkill(12, 0, 2.5, 5), True),
            (KeySkill(11, 0, 2.0, 5), False),
            (KeySkill(20, 1, 2.0, 5), False),
            (KeySkill(100, 3, 2.5, 5), True),
            (KeySkill(100, 4, 2.5, 5), False),
            (KeySkill(12, 0, 2.501, 5), False),
            (KeySkill(12, 0, 1.0, 4), False),
            (KeySkill(12, 0, 0.0, 5), False),
        )
        for skill, qualifies in cases:
            with self.subTest(skill=skill):
                self.assertEqual(
                    mastered_letters({"e": skill}, "en"), "e" if qualifies else ""
                )
                self.assertEqual(
                    len(mastered_letters({"e": skill}, "en")),
                    mastery({"e": skill}, "en")[0],
                )

    def test_repeated_lessons_accumulate_evidence_before_unlocking(self):
        order = ORDERS["en"]
        history = [lesson(order[:6], attempts=6, intervals=3)]
        self.assertEqual(curriculum_state(history, "en").mastered, "")
        history.append(lesson(order[:6], attempts=6, intervals=3))
        self.assertEqual(curriculum_state(history, "en").available, order[:7])

    def test_bad_and_empty_later_lessons_never_relock_earned_letters(self):
        for language, order in ORDERS.items():
            with self.subTest(language=language):
                history = [lesson(order[:6], language)]
                history += [lesson(order[:6], language, 100, 100, 0)] * 35
                history += [lesson("", language)] * 35
                state = curriculum_state(history, language)
                self.assertEqual(state.available, order[:7])
                self.assertEqual(state.mastered, order[:6])
                self.assertEqual(
                    mastered_letters(skills_for(history, language), language), ""
                )

    def test_recent_good_practice_can_recover_from_an_old_error_heavy_lesson(self):
        order = ORDERS["en"]
        history = [lesson(order[:6], attempts=100, mistakes=100, intervals=0)]
        history += [lesson(order[:6])] * 29
        self.assertEqual(curriculum_state(history, "en").available, order[:6])
        history.append(lesson(order[:6]))
        self.assertEqual(curriculum_state(history, "en").available, order[:7])

    def test_languages_have_independent_learning_and_recent_windows(self):
        history = [lesson(ORDERS["en"][:6])]
        history += [lesson("", "ru")] * 40
        self.assertEqual(curriculum_state(history, "en").available, ORDERS["en"][:7])
        self.assertEqual(curriculum_state(history, "ru").available, ORDERS["ru"][:6])

    def test_full_alphabet_mastery_completes_curriculum(self):
        for language, order in ORDERS.items():
            with self.subTest(language=language):
                state = curriculum_state([lesson(order, language)], language)
                self.assertEqual(state.available, order)
                self.assertEqual(state.mastered, order)
                self.assertIsNone(state.next_letter)

    def test_historical_free_practice_can_fast_track_previously_earned_letters(self):
        for language, order in ORDERS.items():
            with self.subTest(language=language):
                history = [lesson(order[1:], language)]
                state = curriculum_state(history, language)
                self.assertEqual(state.available, order[:6])
                self.assertEqual(state.mastered, order[1:])
                history += [lesson("", language)] * 31
                history.append(lesson(order[0], language))
                state = curriculum_state(history, language)
                self.assertEqual(state.available, order)
                self.assertEqual(state.mastered, order)
                self.assertIsNone(state.next_letter)

    def test_replay_does_not_mutate_input_history(self):
        history = [lesson(ORDERS["en"][:6]), lesson(ORDERS["ru"][:6], "ru")]
        original = copy.deepcopy(history)
        curriculum_state(history, "en")
        curriculum_state(history, "ru")
        self.assertEqual(history, original)

    def test_unknown_language_is_rejected(self):
        for language in ("de", "", None):
            with self.subTest(language=language):
                with self.assertRaises(ValueError):
                    curriculum_state([], language)
                with self.assertRaises(ValueError):
                    mastered_letters({}, language)


if __name__ == "__main__":
    unittest.main()
