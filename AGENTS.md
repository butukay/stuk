# Repository Guidelines

## Project Structure & Module Organization

`stuk` is an offline terminal typing trainer for Python 3.10+ on Linux and macOS. Code lives in `src/stuk/`:

- `session.py`: input, corrections, timing, and keystroke observations.
- `words.py` / `adaptive.py`: vocabulary, weak-letter practice, and confidence.
- `curriculum.py` / `letters.py`: earned unlocks and letter progress.
- `history.py`: validated, locked, atomic exercise persistence.
- `charts.py` / `progress.py`: terminal-independent charts and progress rendering.
- `layout.py` / `keyboard.py`: wrapping, viewport geometry, and physical layouts.
- `tui.py`: curses screens and keyboard interaction.
- `settings.py`, `theme.py`, `palette.py`: preferences, colors, and terminal adaptation.
- `cli.py`: arguments and terminal validation.

`tests/` contains unit and PTY tests. `docs/` holds terminal captures; `progress.png` uses demo data. `examples/settings.json` documents configurable colors. The `stuk` launcher runs from a checkout.

## Build, Test, and Development Commands

- `./stuk`: run without installation.
- `./stuk --lang en --words 50`: start a longer English exercise.
- `PYTHONPATH=src python3 -m stuk`: run the package.
- `PYTHONPATH=src python3 -m unittest discover -s tests -v`: run unit and PTY tests.
- `python3 -m compileall -q src tests`: check compilation.
- `python3 -m venv .venv` followed by `.venv/bin/python -m pip install '.[dev]'`: install development tools.
- `.venv/bin/ruff format src tests` and `.venv/bin/ruff check src tests`: format and lint.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions/modules, and `PascalCase` classes. Annotate public interfaces. Ruff configuration lives in `pyproject.toml`. Prefer standard-library modules; keep learning and chart logic independent of curses.

## Testing Guidelines

Use `unittest`, `test_*.py` files, and behavior-focused methods. Cover corrections, timing, adaptive selection, persistence failures, charts, and terminal lifecycle when changing them. Use deterministic RNGs and temporary XDG directories; tests must never write real user history. No coverage percentage is mandated.

## Commit & Pull Request Guidelines

No Git history establishes a format. Use concise, imperative subjects and focused commits. Pull requests should explain behavior, link relevant issues, list validation, and include terminal captures for visual changes.

## Product & Data Principles

Preserve thin borders, quiet colors, and spacing; omit branding. Show metrics after exercises; keep graphs and letters on F3. Align RU/EN and separate learning histories. Keep earned unlocks permanent and respect guided, free, and custom choices; never leak letters outside the selected alphabet. Save completed exercises once; preserve damaged files. Pause in menus and undersized terminals. Validate settings and restore terminal colors. Avoid network requests and unnecessary menus.
