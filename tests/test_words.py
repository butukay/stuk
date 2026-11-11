import random
import unittest

from stuk.curriculum import ORDERS
from stuk.words import EN_WORDS, RU_WORDS, generate_text


class WordGenerationTests(unittest.TestCase):
    def test_default_passage_uses_twenty_five_russian_words(self):
        words = generate_text().split()
        self.assertEqual(len(words), 25)
        self.assertTrue(set(words).issubset(RU_WORDS))

    def test_english_passage_uses_requested_count(self):
        words = generate_text("en", 50).split()
        self.assertEqual(len(words), 50)
        self.assertTrue(set(words).issubset(EN_WORDS))

    def test_pools_are_unique_lowercase_simple_words(self):
        for pool in (RU_WORDS, EN_WORDS):
            self.assertGreaterEqual(len(pool), 100)
            self.assertEqual(len(pool), len(set(pool)))
            self.assertTrue(all(word.isalpha() and word.islower() for word in pool))

    def test_word_pools_cover_every_letter_for_mastery(self):
        for pool, alphabet in (
            (RU_WORDS, "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"),
            (EN_WORDS, "abcdefghijklmnopqrstuvwxyz"),
        ):
            with self.subTest(alphabet=alphabet):
                self.assertTrue(set(alphabet).issubset("".join(pool)))

    def test_starter_vocabulary_has_variety_and_uses_all_six_letters(self):
        for language, pool in (("ru", RU_WORDS), ("en", EN_WORDS)):
            with self.subTest(language=language):
                available = set(ORDERS[language][:6])
                eligible = [word for word in pool if set(word) <= available]
                self.assertGreaterEqual(len(set(eligible)), 6)
                self.assertEqual(set("".join(eligible)), available)

    def test_every_unlock_has_a_real_word_in_its_available_alphabet(self):
        for language, pool in (("ru", RU_WORDS), ("en", EN_WORDS)):
            order = ORDERS[language]
            for count in range(7, len(order) + 1):
                with self.subTest(language=language, available=order[:count]):
                    available = set(order[:count])
                    self.assertTrue(
                        any(
                            order[count - 1] in word and set(word) <= available
                            for word in pool
                        )
                    )

    def test_seed_makes_generation_repeatable(self):
        self.assertEqual(
            generate_text("ru", 25, random.Random(42)),
            generate_text("ru", 25, random.Random(42)),
        )

    def test_passages_never_repeat_adjacent_words(self):
        for language in ("ru", "en"):
            for seed in range(10):
                words = generate_text(language, 60, random.Random(seed)).split()
                self.assertTrue(
                    all(left != right for left, right in zip(words, words[1:]))
                )

    def test_count_boundaries_are_supported(self):
        for count in (1, 60):
            self.assertEqual(len(generate_text(count=count).split()), count)

    def test_invalid_language_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_text("de")

    def test_invalid_count_is_rejected(self):
        for count in (-1, 0, 61, 2.5, "25", True):
            with self.assertRaises(ValueError):
                generate_text(count=count)


if __name__ == "__main__":
    unittest.main()
