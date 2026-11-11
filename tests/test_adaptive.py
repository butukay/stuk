import random
import unittest
from unittest.mock import patch

from stuk.adaptive import (
    KeySkill,
    adaptive_text,
    focus_letters,
    generate_practice_text,
    has_words,
    mastery,
    skills_for,
)
from stuk.curriculum import ORDERS
from stuk.words import EN_WORDS, RU_WORDS, generate_text


def record(language="en", keys=None):
    return {"language": language, "keys": keys or {}}


def samples(attempts=20, mistakes=0, mean=0.25, intervals=10):
    return {
        "attempts": attempts,
        "mistakes": mistakes,
        "interval_total": mean * intervals,
        "interval_count": intervals,
    }


class AdaptiveTests(unittest.TestCase):
    def test_cold_start_matches_regular_generation(self):
        for language in ("ru", "en"):
            text, focus = adaptive_text(language, 25, [], random.Random(12))
            self.assertEqual(text, generate_text(language, 25, random.Random(12)))
            self.assertEqual(focus, ())
            self.assertEqual(mastery({}, language), (0, 33 if language == "ru" else 26))

    def test_skills_filter_language_normalize_case_and_ignore_spaces(self):
        history = [
            record(keys={"A": samples(10, 1, intervals=5), " ": samples()}),
            record("ru", {"а": samples()}),
            record(keys={"a": samples(15, 2, intervals=5), "!": samples()}),
        ]
        skills = skills_for(history, "en")
        self.assertEqual(set(skills), {"a"})
        self.assertEqual(skills["a"], KeySkill(25, 3, 2.5, 10))

    def test_weak_letters_recover_when_old_sessions_leave_recent_window(self):
        bad = record(keys={"a": samples(20, 10)})
        good = record(keys={"a": samples()})
        self.assertEqual(focus_letters(skills_for([bad], "en")), ("a",))
        self.assertEqual(focus_letters(skills_for([bad] + [good] * 30, "en")), ())
        self.assertEqual(skills_for([bad] + [good] * 30, "en")["a"].attempts, 600)

    def test_other_languages_do_not_use_up_recent_session_window(self):
        history = [record(keys={"a": samples(20, 10)})]
        history += [record("ru", {"а": samples()})] * 40
        self.assertEqual(focus_letters(skills_for(history, "en")), ("a",))

    def test_focus_requires_samples_and_ranks_errors_and_relative_slowness(self):
        skills = {
            "a": KeySkill(20, 5, 2, 10),
            "b": KeySkill(20, 0, 9, 10),
            "c": KeySkill(20, 0, 2, 10),
            "d": KeySkill(2, 2, 2, 2),
            " ": KeySkill(20, 20, 10, 10),
        }
        self.assertEqual(focus_letters(skills), ("a", "b"))
        self.assertEqual(focus_letters(skills, 1), ("a",))
        self.assertEqual(focus_letters(skills, 0), ())

    def test_equal_focus_scores_have_deterministic_alphabetic_order(self):
        skills = {letter: KeySkill(10, 2) for letter in ("z", "a", "n", "b")}
        self.assertEqual(focus_letters(skills), ("a", "b", "n"))

    def test_mastery_requires_accuracy_timing_and_sufficient_observations(self):
        skills = {
            "a": KeySkill(12, 0, 2.5, 5),
            "b": KeySkill(11, 0, 1, 5),
            "c": KeySkill(20, 1, 1, 5),
            "d": KeySkill(20, 0, 2.6, 5),
            "e": KeySkill(20, 0, 1, 4),
            "f": KeySkill(34, 1, 1, 5),
            "я": KeySkill(20, 0, 1, 5),
        }
        self.assertEqual(mastery(skills, "en"), (2, 26))
        self.assertEqual(mastery(skills, "ru"), (1, 33))

    def test_adaptive_sampling_emphasizes_weak_letters_without_inventing_words(self):
        history = [record(keys={"q": samples(20, 8)})]
        baseline_hits = 0
        focused_hits = 0
        ordinary_hits = 0
        for seed in range(10):
            text, focus = adaptive_text("en", 60, history, random.Random(seed))
            words = text.split()
            self.assertEqual(focus, ("q",))
            self.assertEqual(len(words), 60)
            self.assertTrue(set(words).issubset(EN_WORDS))
            self.assertTrue(all(a != b for a, b in zip(words, words[1:])))
            focused_hits += sum("q" in word for word in words)
            ordinary_hits += sum("q" not in word for word in words)
            baseline_hits += sum(
                "q" in word
                for word in generate_text("en", 60, random.Random(seed)).split()
            )
        self.assertGreater(focused_hits, baseline_hits * 5)
        self.assertGreater(ordinary_hits, 150)

    def test_slow_letters_are_practiced_even_without_mistakes(self):
        history = [record(keys={"q": samples(mean=0.9), "a": samples(mean=0.2)})]
        text, focus = adaptive_text("en", 25, history, random.Random(1))
        self.assertEqual(focus, ("q",))
        self.assertGreater(sum("q" in word for word in text.split()), 10)

    def test_common_focus_letter_does_not_crowd_out_rare_weak_letters(self):
        history = [record(keys={letter: samples(20, 4) for letter in "eqz"})]
        text, focus = adaptive_text("en", 60, history, random.Random(8))
        self.assertEqual(focus, ("e", "q", "z"))
        for letter in focus:
            self.assertGreaterEqual(sum(letter in word for word in text.split()), 12)

    def test_reported_focus_only_contains_letters_present_in_short_passage(self):
        history = [record(keys={"q": samples(20, 8)})]
        for seed in range(10):
            text, focus = adaptive_text("en", 1, history, random.Random(seed))
            self.assertTrue(all(letter in text for letter in focus))

    def test_adaptive_generation_is_deterministic_at_small_and_large_counts(self):
        for language, letter, pool in (("en", "a", EN_WORDS), ("ru", "а", RU_WORDS)):
            history = [record(language, {letter: samples(20, 4)})]
            for count in (1, 2, 25, 60):
                left = adaptive_text(language, count, history, random.Random(20))
                right = adaptive_text(language, count, history, random.Random(20))
                self.assertEqual(left, right)
                self.assertEqual(len(left[0].split()), count)
                self.assertTrue(set(left[0].split()).issubset(pool))

    def test_unavailable_focus_letters_fall_back_to_regular_words(self):
        history = [record(keys={"q": samples(20, 8)})]
        with patch("stuk.adaptive.EN_WORDS", ("calm", "soft")):
            text, focus = adaptive_text("en", 25, history, random.Random(1))
        self.assertTrue(text)
        self.assertEqual(focus, ())

    def test_malformed_metadata_does_not_poison_skill_totals(self):
        history = [
            None,
            record(keys={"a": samples(), "b": {"attempts": True}}),
            record(keys={"c": samples(20, 21), "d": samples(mean=float("nan"))}),
        ]
        skills = skills_for(history, "en")
        self.assertEqual(set(skills), {"a", "d"})
        self.assertEqual(skills["d"], KeySkill(20, 0, 0, 0))

    def test_invalid_language_and_count_are_rejected(self):
        for language in ("de", ""):
            with self.assertRaises(ValueError):
                skills_for([], language)
            with self.assertRaises(ValueError):
                mastery({}, language)
            with self.assertRaises(ValueError):
                adaptive_text(language, 25, [])
        with self.assertRaises(ValueError):
            adaptive_text("en", 0, [])


class RestrictedPracticeTests(unittest.TestCase):
    def test_locked_letters_never_leak_at_any_guided_stage(self):
        for language, order in ORDERS.items():
            history = [record(language, {letter: samples(20, 5) for letter in order})]
            pool = RU_WORDS if language == "ru" else EN_WORDS
            for size in range(6, len(order) + 1):
                allowed = order[:size]
                for count in (1, 2, 25, 60):
                    for seed in range(3):
                        with self.subTest(
                            language=language, size=size, count=count, seed=seed
                        ):
                            text, focus = adaptive_text(
                                language,
                                count,
                                history,
                                random.Random(seed),
                                allowed=allowed,
                                target=allowed[-1] if size > 6 else None,
                            )
                            words = text.split()
                            self.assertEqual(len(words), count)
                            self.assertTrue(set(text) <= set(allowed + " "))
                            self.assertTrue(set(words) <= set(pool))
                            self.assertTrue(
                                all(a != b for a, b in zip(words, words[1:]))
                            )
                            self.assertTrue(
                                all(
                                    letter in allowed and letter in text
                                    for letter in focus
                                )
                            )

    def test_cold_start_covers_all_six_starter_letters_in_real_words(self):
        for language, order in ORDERS.items():
            allowed = order[:6]
            self.assertTrue(has_words(language, allowed))
            for adaptive in (True, False):
                for seed in range(20):
                    with self.subTest(language=language, adaptive=adaptive, seed=seed):
                        text, focus = generate_practice_text(
                            language,
                            25,
                            [],
                            allowed=allowed,
                            adaptive=adaptive,
                            rng=random.Random(seed),
                        )
                        self.assertEqual(set(text.replace(" ", "")), set(allowed))
                        self.assertLessEqual(len(focus), 3)
                        if not adaptive:
                            self.assertEqual(focus, ())

    def test_newly_unlocked_letter_gets_repeated_targeted_practice(self):
        for language, order in ORDERS.items():
            for size in range(7, len(order) + 1):
                allowed, target = order[:size], order[size - 1]
                history = [
                    record(language, {letter: samples() for letter in allowed[:-1]})
                ]
                for seed in range(3):
                    with self.subTest(language=language, target=target, seed=seed):
                        text, focus = adaptive_text(
                            language,
                            25,
                            history,
                            random.Random(seed),
                            allowed=allowed,
                            target=target,
                        )
                        self.assertEqual(focus[0], target)
                        self.assertGreaterEqual(
                            sum(target in word for word in text.split()), 4
                        )

    def test_one_word_exercise_still_contains_explicit_new_target(self):
        for language, order in ORDERS.items():
            allowed = order[:7]
            for seed in range(5):
                text, focus = adaptive_text(
                    language,
                    1,
                    [],
                    random.Random(seed),
                    allowed=allowed,
                    target=allowed[-1],
                )
                self.assertIn(allowed[-1], text)
                self.assertIn(allowed[-1], focus)

    def test_nonadaptive_restricted_practice_ignores_weak_history(self):
        history = [record(keys={"e": samples(20, 10)})]
        first = generate_practice_text(
            "en", 25, history, allowed="enirat", adaptive=False, rng=random.Random(7)
        )
        second = generate_practice_text(
            "en", 25, [], allowed="enirat", adaptive=False, rng=random.Random(7)
        )
        self.assertEqual(first, second)
        self.assertEqual(first[1], ())
        self.assertTrue(set(first[0]) <= set("enirat "))

    def test_free_nonadaptive_practice_matches_existing_regular_generator(self):
        for language in ("ru", "en"):
            actual = generate_practice_text(
                language, 25, [], adaptive=False, rng=random.Random(10)
            )
            self.assertEqual(
                actual, (generate_text(language, 25, random.Random(10)), ())
            )

    def test_single_letter_custom_alphabet_has_finite_varied_drills(self):
        for language, letter in (("en", "q"), ("ru", "ъ")):
            self.assertFalse(has_words(language, letter))
            for adaptive in (True, False):
                with self.subTest(language=language, adaptive=adaptive):
                    text, focus = generate_practice_text(
                        language,
                        60,
                        [],
                        allowed=letter,
                        adaptive=adaptive,
                        rng=random.Random(9),
                    )
                    groups = text.split()
                    self.assertEqual(len(groups), 60)
                    self.assertTrue(all(set(group) == {letter} for group in groups))
                    self.assertTrue(all(3 <= len(group) <= 5 for group in groups))
                    self.assertTrue(all(a != b for a, b in zip(groups, groups[1:])))
                    self.assertEqual(focus, (letter,) if adaptive else ())

    def test_partial_word_coverage_uses_labeled_drills_for_every_custom_letter(self):
        with patch("stuk.adaptive.EN_WORDS", ("a", "aa")):
            self.assertFalse(has_words("en", "aeq"))
            text, focus = adaptive_text("en", 25, [], random.Random(4), allowed="aeq")
        self.assertEqual(set(text.replace(" ", "")), set("aeq"))
        self.assertEqual(len(text.split()), 25)
        self.assertTrue(all(3 <= len(group) <= 5 for group in text.split()))
        self.assertEqual(set(focus), set("aeq"))

    def test_custom_drills_are_repeatable_and_duplicate_letters_do_not_bias_them(self):
        first = adaptive_text("en", 25, [], random.Random(4), allowed="qzq")
        second = adaptive_text("en", 25, [], random.Random(4), allowed="zq")
        self.assertEqual(first, second)
        self.assertEqual(set(first[0].replace(" ", "")), set("qz"))

    def test_single_real_word_pool_can_repeat_without_crashing(self):
        with patch("stuk.adaptive.EN_WORDS", ("air",)):
            self.assertTrue(has_words("en", "air"))
            text, _ = adaptive_text("en", 25, [], random.Random(4), allowed="air")
        self.assertEqual(text.split(), ["air"] * 25)

    def test_invalid_custom_alphabets_counts_and_targets_are_rejected(self):
        for allowed in ("", "A", "en1", "аen", "e n", [], 12, True):
            with self.subTest(allowed=allowed), self.assertRaises(ValueError):
                adaptive_text("en", 25, [], allowed=allowed)
        for count in (0, 61, True, 25.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                generate_practice_text("en", count, [], allowed="enirat")
        for target in ("z", "en", [], True):
            with self.subTest(target=target), self.assertRaises(ValueError):
                adaptive_text("en", 25, [], allowed="enirat", target=target)
        with self.assertRaises(ValueError):
            generate_practice_text("en", 25, [], allowed="enirat", adaptive="false")
        with self.assertRaises(ValueError):
            has_words("de", "ab")


if __name__ == "__main__":
    unittest.main()
