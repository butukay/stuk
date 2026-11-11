"""A terminal-independent progress screen with honest, per-language trends."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .adaptive import focus_letters, mastery, skills_for
from .charts import line_chart


@dataclass(frozen=True)
class Segment:
    y: int
    x: int
    text: str
    role: str = "ink"


COPY = {
    "ru": {
        "title": "прогресс",
        "language": "русский",
        "empty": "история пока пуста",
        "start": "завершите упражнение",
        "then": "здесь появятся графики",
        "count": "упражнений",
        "minutes": "мин",
        "confident": "уверенно",
        "speed": "скорость",
        "unit": "слов/мин",
        "accuracy": "точность",
        "focus": "фокус",
        "steady": "точность и ровный ритм",
        "footer": "esc назад · tab/F4 язык · ↑↓ буквы",
        "unsaved": "история не сохранена",
        "recent": "последние",
    },
    "en": {
        "title": "progress",
        "language": "english",
        "empty": "no exercises yet",
        "start": "finish an exercise",
        "then": "your trends will appear here",
        "count": "exercises",
        "minutes": "min",
        "confident": "confident",
        "speed": "speed",
        "unit": "wpm",
        "accuracy": "accuracy",
        "focus": "focus",
        "steady": "accuracy and a steady rhythm",
        "footer": "esc back · tab/F4 language · ↑↓ letters",
        "unsaved": "history could not be saved",
        "recent": "latest",
    },
}


def render_progress(
    history: list[dict],
    language: str,
    rows: int,
    columns: int,
    *,
    error: bool = False,
) -> list[Segment]:
    """Render the latest 30 exercises; retain counts over all recorded practice."""
    copy = COPY[language]
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
        put(y, "│", "faint", at=left + width - 1)
    put(top, f" {copy['title']} · {copy['language']} ", "muted")
    footer = copy["footer"] if len(copy["footer"]) <= inner else "esc  tab/F4  ↑↓"
    put(rows - 2 if rows >= 16 else rows - 1, footer, "muted")

    records = [record for record in history if record["language"] == language]
    if not records:
        middle = (top + bottom) // 2
        for y, text, role in (
            (middle - 1, copy["empty"], "ink"),
            (middle + 1, copy["start"], "muted"),
            (middle + 2, copy["then"], "muted"),
        ):
            put(y, text, role, at=x + max(0, (inner - len(text)) // 2))
        if error:
            put(bottom - 1, copy["unsaved"], "error")
        return segments

    recent = records[-30:]
    skills = skills_for(history, language)
    confident, total = mastery(skills, language)
    minutes = sum(record["duration"] for record in records) / 60
    if inner >= 48:
        summary = (
            f"{len(records)} {copy['count']}   ·   {minutes:.0f} {copy['minutes']}"
        )
        put(top + 2, summary)
        count = f"{copy['confident']} {confident}/{total}"
        put(top + 2, count, "accent", at=x + inner - len(count), limit=len(count))
    else:
        put(top + 2, f"{len(records)} {copy['count']} · {confident}/{total}")

    speed = [record["wpm"] for record in recent]
    accuracy = [record["accuracy"] for record in recent]
    first_number = len(records) - len(recent) + 1
    focus = focus_letters(skills)
    focus_text = f"{copy['focus']}: {' '.join(focus)}" if focus else copy["steady"]

    if rows >= 24 and inner >= 38:
        put(top + 3, f"{copy['recent']} {len(recent)} / {len(records)}", "muted")
        chart_height = max(2, (bottom - (top + 5) - 9) // 2)

        def chart(
            label: str,
            values: list[float],
            y: int,
            maximum: float,
            unit: str,
            minimum: float = 0,
        ) -> None:
            put(y, label, "muted")
            latest = f"{values[-1]:.0f}{unit}"
            put(y, latest, "accent", at=x + inner - len(latest), limit=len(latest))
            plot_x, plot_width = x + 6, inner - 6
            grid = line_chart(
                values, plot_width, chart_height, minimum=minimum, maximum=maximum
            )
            for index, line in enumerate(grid):
                put(y + 1 + index, "│", "faint", at=plot_x - 1, limit=1)
                put(y + 1 + index, line, "accent", at=plot_x, limit=plot_width)
            put(y + 1, f"{maximum:4.0f}", "muted", limit=4)
            put(y + chart_height, f"{minimum:4.0f}", "muted", limit=4)
            axis_y = y + chart_height + 1
            put(
                axis_y,
                "└" + "─" * plot_width,
                "faint",
                at=plot_x - 1,
                limit=plot_width + 1,
            )
            put(axis_y + 1, f"#{first_number}", "muted", at=plot_x)
            end_label = f"#{len(records)}"
            put(
                axis_y + 1,
                end_label,
                "muted",
                at=x + inner - len(end_label),
                limit=len(end_label),
            )

        maximum = max(10.0, math.ceil(max(speed) * 1.1 / 10) * 10)
        chart(copy["speed"], speed, top + 5, maximum, f" {copy['unit']}")
        accuracy_minimum = max(0.0, math.floor(min(accuracy) / 5) * 5 - 5)
        chart(
            copy["accuracy"],
            accuracy,
            top + 9 + chart_height,
            100,
            "%",
            accuracy_minimum,
        )
        put(
            bottom - 2,
            copy["unsaved"] if error else focus_text,
            "error" if error else "muted",
        )
    else:
        if error:
            put(top + 3, copy["unsaved"], "error")
        title_y = top + 4
        chart_height = max(1, (bottom - title_y - 5) // 2)
        for index, (label, values, maximum, suffix) in enumerate(
            (
                (copy["speed"], speed, max(10.0, max(speed) * 1.1), f" {copy['unit']}"),
                (copy["accuracy"], accuracy, 100.0, "%"),
            )
        ):
            y = title_y + index * (chart_height + 3)
            put(y, f"{label} · {values[-1]:.0f}{suffix}", "muted")
            for row, line in enumerate(
                line_chart(values, inner, chart_height, 0, maximum)
            ):
                put(y + 1 + row, line, "accent")
        if bottom - 1 > title_y + 2 * chart_height + 3:
            put(bottom - 1, focus_text, "muted")
    return segments
