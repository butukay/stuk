"""Small braille line charts, independent of terminal state or color."""

from __future__ import annotations

import math

_DOTS = ((1, 8), (2, 16), (4, 32), (64, 128))


def _finite(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite numbers") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite numbers")
    return result


def _sample(values: list[float], capacity: int) -> list[float]:
    """Average balanced buckets, keeping the latest observation untouched."""
    if len(values) <= capacity:
        return values
    groups = capacity - 1
    previous = len(values) - 1
    sampled = []
    for group in range(groups):
        start = group * previous // groups
        end = (group + 1) * previous // groups
        size = end - start
        sampled.append(math.fsum(value / size for value in values[start:end]))
    return [*sampled, values[-1]]


def line_chart(
    values: list[float],
    width: int,
    height: int,
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[str, ...]:
    """Draw a continuous trend in an exact ``width`` by ``height`` rectangle.

    Each braille cell holds two columns and four rows of pixels. Values outside
    explicit bounds are clipped. Automatic bounds add eight percent of breathing
    room, or at least one unit for a constant series. A lone observation sits at
    the right edge. Empty data returns spaces; invalid dimensions, nonfinite
    values, and reversed or equal explicit bounds raise ``ValueError``.
    """
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise ValueError("chart width and height must be positive integers")
    data = [_finite(value, "values") for value in values]
    low = None if minimum is None else _finite(minimum, "minimum")
    high = None if maximum is None else _finite(maximum, "maximum")
    if low is not None and high is not None and low >= high:
        raise ValueError("minimum must be less than maximum")
    if not data:
        return tuple(" " * width for _ in range(height))

    if low is None:
        low = min(min(data), high) if high is not None else min(data)
    if high is None:
        high = max(max(data), low)
    span = high - low
    if not math.isfinite(span):
        raise ValueError("chart range is too large")
    padding = span * 0.08 if span else max(abs(high) * 0.08, 1.0)
    if minimum is None and math.isfinite(low - padding):
        low -= padding
    if maximum is None and math.isfinite(high + padding):
        high += padding
    span = high - low
    if not math.isfinite(span) or span <= 0:
        raise ValueError("chart range must be positive and finite")

    pixel_width, pixel_height = width * 2, height * 4
    sampled = _sample(data, pixel_width)
    cells = [[0] * width for _ in range(height)]

    def dot(x: int, y: int) -> None:
        cells[y // 4][x // 2] |= _DOTS[y % 4][x % 2]

    def connect(start: tuple[int, int], end: tuple[int, int]) -> None:
        x, y = start
        target_x, target_y = end
        dx, dy = abs(target_x - x), -abs(target_y - y)
        step_x = 1 if x < target_x else -1
        step_y = 1 if y < target_y else -1
        error = dx + dy
        while True:
            dot(x, y)
            if (x, y) == end:
                return
            doubled = error * 2
            if doubled >= dy:
                error += dy
                x += step_x
            if doubled <= dx:
                error += dx
                y += step_y

    previous = None
    for index, value in enumerate(sampled):
        x = (
            round(index * (pixel_width - 1) / (len(sampled) - 1))
            if len(sampled) > 1
            else pixel_width - 1
        )
        normalized = (min(high, max(low, value)) - low) / span
        y = round((1 - normalized) * (pixel_height - 1))
        point = (x, y)
        if previous is None:
            dot(x, y)
        else:
            connect(previous, point)
        previous = point
    return tuple(
        "".join(chr(0x2800 + dots) if dots else " " for dots in row) for row in cells
    )
