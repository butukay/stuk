"""Command-line entry point; keep terminal setup out of noninteractive commands."""

from __future__ import annotations

import argparse
import locale
import os
import sys

from . import __version__
from .settings import clean_letters, load_settings


def word_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use a number from 1 to 60") from error
    if not 1 <= count <= 60:
        raise argparse.ArgumentTypeError("use a number from 1 to 60")
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stuk",
        description="Minimal terminal typing practice.",
        epilog="Esc: quit · Tab: fresh text · F2: settings · F3: progress · F4: language",
    )
    parser.add_argument(
        "--lang", choices=("ru", "en"), help="override the saved language"
    )
    parser.add_argument(
        "--words",
        type=word_count,
        metavar="1–60",
        help="override saved word count (default: 25)",
    )
    parser.add_argument(
        "--mode",
        choices=("guided", "free", "custom"),
        help="staged, full-alphabet, or custom practice",
    )
    parser.add_argument(
        "--letters",
        metavar="LETTERS",
        help="practice these letters in the selected language",
    )
    parser.add_argument("--version", action="version", version=f"stuk {__version__}")
    arguments = parser.parse_args(argv)

    settings = load_settings()
    if arguments.lang is not None:
        settings.language = arguments.lang
    if arguments.words is not None:
        settings.words = arguments.words
    if arguments.mode is not None:
        settings.practice_mode = arguments.mode
    if arguments.letters is not None:
        letters = clean_letters(arguments.letters, settings.language)
        if not letters:
            parser.error("--letters needs at least one letter of the selected language")
        settings.custom_letters[settings.language] = letters
        settings.practice_mode = "custom"

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "stuk needs an interactive terminal. Run stuk in a terminal.",
            file=sys.stderr,
        )
        return 1
    if os.environ.get("TERM", "") in ("", "dumb", "unknown"):
        print(
            "stuk needs a terminal with cursor support (for example xterm-256color).",
            file=sys.stderr,
        )
        return 1

    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        print(
            "stuk needs a valid UTF-8 locale. Try LC_ALL=C.UTF-8 ./stuk",
            file=sys.stderr,
        )
        return 1
    encoding = (
        locale.nl_langinfo(locale.CODESET)
        if hasattr(locale, "nl_langinfo")
        else locale.getpreferredencoding(False)
    )
    if "utf8" not in encoding.lower().replace("-", ""):
        print("stuk needs a UTF-8 locale. Try LC_ALL=C.UTF-8 ./stuk", file=sys.stderr)
        return 1

    try:
        import curses
    except ImportError:
        print(
            "stuk needs Python with curses support on Linux or macOS.", file=sys.stderr
        )
        return 1

    from .tui import run

    try:
        curses.wrapper(run, settings)
    except KeyboardInterrupt:
        return 130
    except curses.error as error:
        print(f"stuk could not open the terminal: {error}", file=sys.stderr)
        return 1
    return 0
