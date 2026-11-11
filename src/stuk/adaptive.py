"""Recent-session practice with explicit alphabets and labeled letter drills."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import median

from .words import EN_WORDS, RU_WORDS, generate_text

ALPHABETS = {
    "ru": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "en": "abcdefghijklmnopqrstuvwxyz",
}


@dataclass
class KeySkill:
    attempts: int = 0
    mistakes: int = 0
    interval_total: float = 0.0
    interval_count: int = 0


def skills_for(history: list[dict], language: str) -> dict[str, KeySkill]:
    """Aggregate the latest 30 sessions of one language, in chronological history."""
    if language not in ALPHABETS:
        raise ValueError("Language must be 'ru' or 'en'.")
    sessions = [
        row
        for row in history
        if isinstance(row, dict) and row.get("language") == language
    ][-30:]
    skills: dict[str, KeySkill] = {}
    for row in sessions:
        keys = row.get("keys", {})
        if not isinstance(keys, dict):
            continue
        for expected, values in keys.items():
            if not isinstance(expected, str) or not isinstance(values, dict):
                continue
            letter = expected.lower()
            if len(letter) != 1 or letter not in ALPHABETS[language]:
                continue
            attempts = values.get("attempts", 0)
            mistakes = values.get("mistakes", 0)
            if type(attempts) is not int or attempts <= 0:
                continue
            if type(mistakes) is not int or not 0 <= mistakes <= attempts:
                continue
            skill = skills.setdefault(letter, KeySkill())
            skill.attempts += attempts
            skill.mistakes += mistakes
            total = values.get("interval_total", 0.0)
            count = values.get("interval_count", 0)
            if (
                type(count) is int
                and 0 < count <= attempts
                and type(total) in (int, float)
                and math.isfinite(total)
                and total > 0
            ):
                skill.interval_total += total
                skill.interval_count += count
    return skills


def focus_letters(skills: dict[str, KeySkill], limit: int = 3) -> tuple[str, ...]:
    """Rank observed weak letters by mistakes and delay relative to other letters.

    Three attempts are required. Errors contribute four times their rate; a mean
    interval at least 15% above the median contributes a smaller latency score.
    """
    if limit <= 0:
        return ()
    eligible = {
        letter: skill
        for letter, skill in skills.items()
        if len(letter) == 1
        and letter in ALPHABETS["ru"] + ALPHABETS["en"]
        and skill.attempts >= 3
    }
    means = [
        skill.interval_total / skill.interval_count
        for skill in eligible.values()
        if skill.interval_count >= 3 and skill.interval_total > 0
    ]
    reference = median(means) if means else None
    ranked: list[tuple[float, str]] = []
    for letter, skill in eligible.items():
        error_rate = skill.mistakes / skill.attempts
        delay = 0.0
        if reference and skill.interval_count >= 3:
            mean = skill.interval_total / skill.interval_count
            relative = mean / reference - 1
            if mean > 0.25 and relative >= 0.15:
                delay = min(relative, 2.0) * 0.35
        score = error_rate * 4 + delay
        if score > 0.02:
            ranked.append((score, letter))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return tuple(letter for _, letter in ranked[:limit])


def mastery(skills: dict[str, KeySkill], language: str) -> tuple[int, int]:
    """Count letters with 12 attempts, 97% accuracy, and five intervals <=0.5s mean."""
    if language not in ALPHABETS:
        raise ValueError("Language must be 'ru' or 'en'.")
    confident = 0
    for letter in ALPHABETS[language]:
        skill = skills.get(letter)
        if (
            skill is not None
            and skill.attempts >= 12
            and skill.mistakes / skill.attempts <= 0.03
            and skill.interval_count >= 5
            and 0 < skill.interval_total / skill.interval_count <= 0.5
        ):
            confident += 1
    return confident, len(ALPHABETS[language])


def adaptive_text(
    language: str,
    count: int,
    history: list[dict],
    rng: random.Random | None = None,
    *,
    allowed: str | None = None,
    target: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Mix focused and ordinary words, never leaving a requested alphabet."""
    letters = _validate_practice(language, count, allowed, target)
    if letters is not None:
        return _restricted_text(language, count, history, letters, True, rng, target)
    chooser = rng if rng is not None else random.Random()
    ordinary = generate_text(language, count, chooser).split()
    pool = RU_WORDS if language == "ru" else EN_WORDS
    focus = tuple(
        letter
        for letter in focus_letters(skills_for(history, language))
        if any(letter in word for word in pool)
    )
    if not focus:
        return " ".join(ordinary), ()
    slots = [True] * (count - math.ceil(count * 0.35))
    slots += [False] * (count - len(slots))
    chooser.shuffle(slots)
    words: list[str] = []
    focus_index = 0
    for index, use_focus in enumerate(slots):
        previous = words[-1] if words else None
        target = focus[focus_index % len(focus)]
        candidates = [word for word in pool if target in word and word != previous]
        if use_focus and candidates:
            weights = [
                1
                + word.count(target) * len(focus)
                + sum(
                    word.count(letter) * (len(focus) - rank)
                    for rank, letter in enumerate(focus)
                )
                for word in candidates
            ]
            word = chooser.choices(candidates, weights=weights, k=1)[0]
            focus_index += 1
        else:
            word = ordinary[index]
            if word == previous:
                word = chooser.choice([item for item in pool if item != previous])
        words.append(word)
    text = " ".join(words)
    return text, tuple(letter for letter in focus if letter in text)


def _letters(language: str, allowed: str | None) -> str | None:
    if language not in ("ru", "en"):
        raise ValueError("Language must be 'ru' or 'en'.")
    if allowed is None:
        return None
    if (
        not isinstance(allowed, str)
        or not allowed
        or any(letter not in ALPHABETS[language] for letter in allowed)
    ):
        raise ValueError("The alphabet must contain lowercase letters of its language.")
    return "".join(letter for letter in ALPHABETS[language] if letter in allowed)


def _validate_practice(
    language: str, count: int, allowed: str | None, target: str | None
) -> str | None:
    letters = _letters(language, allowed)
    if type(count) is not int or not 1 <= count <= 60:
        raise ValueError("Word count must be an integer between 1 and 60.")
    if target is not None and (
        not isinstance(target, str)
        or len(target) != 1
        or target not in (letters if letters is not None else ALPHABETS[language])
    ):
        raise ValueError("The target must be a letter of the practice alphabet.")
    return letters


def _word_pool(language: str, letters: str | None) -> tuple[str, ...]:
    pool = RU_WORDS if language == "ru" else EN_WORDS
    if letters is None:
        return pool
    alphabet = set(letters)
    eligible = tuple(word for word in pool if set(word) <= alphabet)
    covered = set("".join(eligible))
    # A partial word pool would silently omit chosen letters, so use drills then.
    return eligible if alphabet <= covered else ()


def has_words(language: str, allowed: str | None = None) -> bool:
    """Whether real words can practice every requested letter; otherwise label drills."""
    return bool(_word_pool(language, _letters(language, allowed)))


def _practice_focus(
    language: str, letters: str, history: list[dict], target: str | None
) -> tuple[str, ...]:
    skills = {
        letter: skill
        for letter, skill in skills_for(history, language).items()
        if letter in letters
    }
    unmastered = [
        letter
        for letter in letters
        if not mastery({letter: skills[letter]} if letter in skills else {}, language)[
            0
        ]
    ]
    unmastered.sort(key=lambda letter: skills.get(letter, KeySkill()).attempts)
    priority = [target] if target in unmastered else []
    priority += list(focus_letters(skills, len(letters))) + unmastered
    return tuple(dict.fromkeys(priority))[:3]


def _coverage_words(
    pool: tuple[str, ...], letters: str, chooser: random.Random, target: str | None
) -> list[str]:
    """Reserve a small real-word cover so starter and custom letters get practice."""
    remaining = set(letters)
    words = []
    while remaining:
        candidates = pool
        if not words and target is not None:
            candidates = tuple(word for word in pool if target in word)
        best = max(len(set(word) & remaining) for word in candidates)
        candidates = tuple(
            word for word in candidates if len(set(word) & remaining) == best
        )
        word = chooser.choice(candidates)
        words.append(word)
        remaining.difference_update(word)
    return words


def _letter_drills(
    count: int,
    letters: str,
    focus: tuple[str, ...],
    chooser: random.Random,
    target: str | None,
) -> str:
    remaining = list(letters)
    chooser.shuffle(remaining)
    if target is not None:
        remaining.remove(target)
        remaining.insert(0, target)
    weights = [
        1 + (len(focus) - focus.index(key)) * 2 if key in focus else 1
        for key in letters
    ]
    groups = []
    for _ in range(count):
        characters = []
        for _ in range(chooser.randint(3, 5)):
            character = (
                remaining.pop(0)
                if remaining
                else chooser.choices(letters, weights=weights, k=1)[0]
            )
            characters.append(character)
        group = "".join(characters)
        if groups and group == groups[-1]:
            if len(letters) == 1:
                group = letters * (4 if len(group) != 4 else 3)
            else:
                alternatives = [letter for letter in letters if letter != group[-1]]
                group = group[:-1] + chooser.choice(alternatives)
        groups.append(group)
    return " ".join(groups)


def _restricted_text(
    language: str,
    count: int,
    history: list[dict],
    letters: str,
    adaptive: bool,
    rng: random.Random | None,
    target: str | None,
) -> tuple[str, tuple[str, ...]]:
    chooser = rng if rng is not None else random.Random()
    focus = _practice_focus(language, letters, history, target) if adaptive else ()
    pool = _word_pool(language, letters)
    if not pool:
        text = _letter_drills(count, letters, focus, chooser, target)
        return text, tuple(letter for letter in focus if letter in text)

    coverage = _coverage_words(pool, letters, chooser, target)
    ordinary_count = min(count, max(math.ceil(count * 0.35), len(coverage)))
    focused_count = count - ordinary_count if focus else 0
    slots = [True] * focused_count + [False] * (count - focused_count)
    chooser.shuffle(slots)
    words = []
    focus_index = 0
    for use_focus in slots:
        previous = words[-1] if words else None
        candidates = tuple(word for word in pool if word != previous) or pool
        target_letter = focus[focus_index % len(focus)] if focus else None
        targeted = (
            tuple(word for word in candidates if target_letter in word)
            if use_focus
            else ()
        )
        if targeted:
            weights = [
                1
                + word.count(target_letter) * len(focus)
                + sum(
                    word.count(key) * (len(focus) - rank)
                    for rank, key in enumerate(focus)
                )
                for word in targeted
            ]
            word = chooser.choices(targeted, weights=weights, k=1)[0]
            focus_index += 1
        elif coverage and not use_focus:
            word = coverage.pop(0)
            if word == previous:
                # The preceding focused word already supplied this cover's letters.
                word = chooser.choice(candidates)
        else:
            word = chooser.choice(candidates)
        words.append(word)
    text = " ".join(words)
    return text, tuple(letter for letter in focus if letter in text)


def generate_practice_text(
    language: str,
    count: int,
    history: list[dict],
    *,
    allowed: str | None = None,
    adaptive: bool = True,
    rng: random.Random | None = None,
    target: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Generate free, guided, or custom practice; drills require a visible UI label."""
    letters = _validate_practice(language, count, allowed, target)
    if type(adaptive) is not bool:
        raise ValueError("Adaptive practice must be a boolean.")
    if letters is not None:
        return _restricted_text(
            language, count, history, letters, adaptive, rng, target
        )
    if adaptive:
        return adaptive_text(language, count, history, rng, target=target)
    return generate_text(language, count, rng), ()
