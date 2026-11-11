"""Letter milestones earned from completed exercises, without separate state."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .adaptive import KeySkill, skills_for

ORDERS = {
    "en": "eniratsolhdcumpgbywfkvqjxz",
    "ru": "енотасрилвкдумпьязбыгчйжшхюцщфёэъ",
}


@dataclass(frozen=True)
class CurriculumState:
    available: str
    mastered: str
    next_letter: str | None
    total: int


def _order(language: str) -> str:
    if not isinstance(language, str) or language not in ORDERS:
        raise ValueError("Language must be 'ru' or 'en'.")
    return ORDERS[language]


def mastered_letters(skills: dict[str, KeySkill], language: str) -> str:
    """Return letters meeting the same confidence thresholds as recent mastery."""
    confident = []
    for letter in _order(language):
        skill = skills.get(letter)
        if (
            skill is not None
            and skill.attempts >= 12
            and skill.mistakes / skill.attempts <= 0.03
            and skill.interval_count >= 5
            and 0 < skill.interval_total / skill.interval_count <= 0.5
        ):
            confident.append(letter)
    return "".join(confident)


def curriculum_state(history: list[dict], language: str) -> CurriculumState:
    """Replay chronological history; earned letters and unlocks never regress.

    Each milestone uses at most 30 exercises of the selected language. Retaining
    earned milestones separately during the replay prevents later practice or a
    smaller recent window from removing earlier progress.
    """
    order = _order(language)
    recent: deque[dict] = deque(maxlen=30)
    earned: set[str] = set()
    for record in history:
        if not isinstance(record, dict) or record.get("language") != language:
            continue
        recent.append(record)
        earned.update(mastered_letters(skills_for(list(recent), language), language))

    unlocked = 6
    while unlocked < len(order) and all(
        letter in earned for letter in order[:unlocked]
    ):
        unlocked += 1
    return CurriculumState(
        available=order[:unlocked],
        mastered="".join(letter for letter in order if letter in earned),
        next_letter=order[unlocked] if unlocked < len(order) else None,
        total=len(order),
    )
