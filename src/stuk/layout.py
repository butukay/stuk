"""Terminal-independent wrapping and viewport geometry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextLine:
    start: int
    text: str


def wrap_text(text: str, width: int) -> list[TextLine]:
    """Wrap on word boundaries, preserving spaces and character positions."""
    if width < 1:
        raise ValueError("width must be positive")
    lines = []
    start = 0
    while start < len(text):
        end = min(start + width, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary + 1
        lines.append(TextLine(start, text[start:end]))
        start = end
    return lines


@dataclass(frozen=True)
class Layout:
    left: int
    width: int
    header_y: int
    text_y: int
    frame_bottom: int
    spacing: int
    first_line: int
    visible_lines: int
    progress_y: int
    status_y: int
    footer_y: int
    keyboard_y: int | None


def arrange(
    rows: int,
    columns: int,
    lines: list[TextLine],
    position: int,
    show_keyboard: bool = False,
) -> Layout:
    """Keep the active line visible and leave space around the exercise."""
    spacing = 2 if rows >= 20 else 1
    base_height = 9 + (7 if show_keyboard else 0)
    capacity = max(1, (rows - 4 - base_height) // spacing + 1)
    visible = min(max(1, len(lines)), capacity)
    active = max(
        (index for index, line in enumerate(lines) if line.start <= position),
        default=0,
    )
    first = max(0, min(active - visible // 2, len(lines) - visible))
    block_height = base_height + (visible - 1) * spacing
    header_y = max(1, (rows - 3 - block_height) // 2)
    text_y = header_y + 2
    frame_bottom = text_y + (visible - 1) * spacing + 2
    progress_y = frame_bottom + 2
    width = min(68, columns - 8)
    return Layout(
        left=(columns - width) // 2,
        width=width,
        header_y=header_y,
        text_y=text_y,
        frame_bottom=frame_bottom,
        spacing=spacing,
        first_line=first,
        visible_lines=visible,
        progress_y=progress_y,
        status_y=progress_y + 2,
        footer_y=rows - 2,
        keyboard_y=progress_y + 5 if show_keyboard else None,
    )
