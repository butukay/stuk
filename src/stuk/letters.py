"""A quiet, terminal-independent view of available and earned letters."""

from __future__ import annotations

from .adaptive import ALPHABETS
from .curriculum import curriculum_state
from .progress import Segment

COPY = {
    "ru": {
        "title": "буквы · русский",
        "mode": "режим",
        "guided": "обучение",
        "free": "свободный",
        "custom": "свои буквы",
        "available": "доступно",
        "mastered": "освоено",
        "alphabet": "алфавит",
        "later": "позже",
        "legend_short": ("осв.", "дост.", "позже"),
        "next": "следующая",
        "milestone": "следующая по этапам",
        "next_short": "далее",
        "all_open": "все буквы открыты",
        "all_mastered": "все буквы освоены",
        "settings": "F2 выбор режима и букв",
        "settings_short": "F2 режим и буквы",
        "footer": "esc назад · tab/F4 язык · ↑↓ графики",
        "footer_short": "esc  tab/F4  ↑↓",
        "unsaved": "история не сохранена",
    },
    "en": {
        "title": "letters · english",
        "mode": "mode",
        "guided": "guided",
        "free": "free",
        "custom": "custom",
        "available": "available",
        "mastered": "mastered",
        "alphabet": "alphabet",
        "later": "later",
        "legend_short": ("done", "open", "later"),
        "next": "next letter",
        "milestone": "next milestone",
        "next_short": "next",
        "all_open": "all letters open",
        "all_mastered": "all letters mastered",
        "settings": "F2 choose mode and letters",
        "settings_short": "F2 mode and letters",
        "footer": "esc back · tab/F4 language · ↑↓ charts",
        "footer_short": "esc  tab/F4  ↑↓",
        "unsaved": "history could not be saved",
    },
}


def render_letters(
    history: list[dict],
    language: str,
    rows: int,
    columns: int,
    *,
    practice_mode: str = "guided",
    custom_letters: str | None = None,
    error: bool = False,
) -> list[Segment]:
    """Show permanent milestones separately from the current practice alphabet."""
    state = curriculum_state(history, language)
    if rows < 12 or columns < 32:
        return []
    copy = COPY[language]
    mode = practice_mode if practice_mode in ("guided", "free", "custom") else "guided"
    alphabet = ALPHABETS[language]
    if mode == "free":
        allowed = alphabet
    elif mode == "custom":
        selected = custom_letters.lower() if isinstance(custom_letters, str) else ""
        allowed = "".join(letter for letter in alphabet if letter in selected)
    else:
        allowed = state.available

    segments: list[Segment] = []
    width = min(88, columns - 2)
    left = (columns - width) // 2
    top = 1 if rows >= 16 else 0
    bottom = rows - 4 if rows >= 16 else rows - 2
    x, inner = left + 3, width - 6

    def put(
        y: int, text: str, role: str = "ink", *, at: int = x, limit: int = inner
    ) -> None:
        if 0 <= y < rows and 0 <= at < columns:
            text = text[: min(limit, columns - at)]
            if text:
                segments.append(Segment(y, at, text, role))

    put(top, "╭" + "─" * (width - 2) + "╮", "faint", at=left, limit=width)
    put(bottom, "╰" + "─" * (width - 2) + "╯", "faint", at=left, limit=width)
    for y in range(top + 1, bottom):
        put(y, "│", "faint", at=left)
        put(y, "│", "faint", at=left + width - 1, limit=1)
    put(top, f" {copy['title']} ", "muted")
    footer = copy["footer"] if len(copy["footer"]) <= inner else copy["footer_short"]
    put(rows - 2 if rows >= 16 else rows - 1, footer, "muted")

    mode_text = f"{copy['mode']}: {copy[mode]}"
    available_text = f"{copy['available']}: {len(allowed)}/{state.total}"
    mastered_text = f"{copy['mastered']}: {len(state.mastered)}/{state.total}"
    per_line = max(1, (inner + 1) // 2)
    mastered_lines = [
        " ".join(state.mastered[index : index + per_line])
        for index in range(0, len(state.mastered), per_line)
    ] or ["—"]

    full = rows >= 24 or (rows >= 20 and inner >= 32)
    if state.next_letter is None:
        next_text = (
            copy["all_mastered"]
            if len(state.mastered) == state.total
            else copy["all_open"]
        )
    else:
        caption = copy["next"] if mode == "guided" else copy["milestone"]
        if not full:
            caption = copy["next_short"]
        next_text = f"{caption}: {state.next_letter}"

    if not full:
        put(top + 1, mode_text, "muted")
        put(top + 2, available_text)
        put(top + 3, mastered_text, "muted")
        for index, line in enumerate(mastered_lines):
            put(top + 4 + index, line, "accent" if state.mastered else "muted")
        put(bottom - 2, next_text)
        put(
            bottom - 1,
            copy["unsaved"] if error else copy["settings_short"],
            "error" if error else "muted",
        )
        return segments

    alphabet_rows = (len(alphabet) + per_line - 1) // per_line
    content_height = 8 + alphabet_rows + len(mastered_lines)
    start = top + 1 + max(0, (bottom - top - 1 - content_height) // 2)
    put(start, mode_text, "muted")
    put(start, "F2", "ink", at=x + inner - 2, limit=2)
    put(start + 1, available_text)
    put(start + 3, copy["alphabet"], "muted")
    grid_y = start + 4
    for index, letter in enumerate(alphabet):
        role = (
            "accent"
            if letter in state.mastered
            else ("ink" if letter in allowed else "future")
        )
        put(
            grid_y + index // per_line,
            letter,
            role,
            at=x + index % per_line * 2,
            limit=1,
        )

    legend_y = grid_y + alphabet_rows
    labels = (copy["mastered"], copy["available"], copy["later"])
    if sum(map(len, labels)) + 6 > inner:
        labels = copy["legend_short"]
    at = x
    for index, (label, role) in enumerate(zip(labels, ("accent", "ink", "future"))):
        if index:
            put(legend_y, " · ", "muted", at=at, limit=3)
            at += 3
        put(legend_y, label, role, at=at, limit=len(label))
        at += len(label)

    earned_y = legend_y + 1
    put(earned_y, mastered_text, "muted")
    for index, line in enumerate(mastered_lines):
        put(earned_y + 1 + index, line, "accent" if state.mastered else "muted")
    next_y = earned_y + 1 + len(mastered_lines)
    put(next_y, next_text)
    put(
        next_y + 1,
        copy["unsaved"] if error else copy["settings"],
        "error" if error else "muted",
    )
    return segments
