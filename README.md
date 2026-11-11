# stuk

**English** · [Русский](README.ru.md)

A minimal terminal typing trainer for Russian and English.

![stuk typing screen](docs/preview.png)

Thin borders, quiet colors, and room to focus. Typed letters brighten, mistakes
get a soft highlight, and a lavender cursor marks the next character. Speed and
accuracy appear after you finish an exercise.

## Install

Requires **Python 3.10+** with `curses`, `curl`, and a UTF-8 terminal on Linux
or macOS. Install with one command:

```sh
curl -fsSL https://raw.githubusercontent.com/butukay/stuk/master/install.py | python3
```

Then run `stuk` from any directory. If `~/.local/bin` was missing from your
`PATH`, the installer adds it for Bash, Zsh, or Fish; open a new terminal.
The installer also prints the full command path so you can start immediately.

No `pip`, `git`, virtual environment, or `sudo` is needed. The app lives at
`~/.local/share/stuk/stuk.pyz` (or `$XDG_DATA_HOME/stuk/stuk.pyz`), with a
command at `~/.local/bin/stuk`. Installation downloads source from this GitHub
repository; the trainer itself works offline. **Run the same command to update.**
Your settings and practice history are preserved.

## Run

```sh
stuk
stuk --lang en
stuk --words 50
stuk --mode free
stuk --lang en --letters asdfjkl
stuk --help
```

The first exercise uses Russian, 25 words, and gradual letter unlocks. Switch
languages with `F4` or `--lang en`. Exercise length can be 1–60 words.

To try it directly from a checkout without installing:

```sh
git clone https://github.com/butukay/stuk.git
cd stuk
./stuk
```

## Controls

| Key | Action |
| --- | --- |
| `Esc` or `Ctrl+C` | Quit |
| `Tab` | Start a fresh exercise |
| `F2` or `Ctrl+O` | Open / close settings |
| `F3` or `Ctrl+P` | Open / close progress and charts |
| `F4` or `Ctrl+L` | Switch Russian / English and start a fresh exercise |
| Type | Begin; the timer starts on your first character |
| `Backspace` | Correct the previous character |
| `Ctrl+W` | Delete the previous word |
| `Ctrl+K` | Show / hide the keyboard |
| `Enter` after finishing | Start the next exercise |

The exercise footer follows `Esc`, `Tab`, `F2`, `F3`, `F4`. In progress,
`F4` changes only the language being viewed; your exercise stays in place.
In the custom-letter editor, `F4` keeps separate RU/EN drafts until you apply
or cancel editing.

In settings, use `↑↓` to select a row and `←→` or `Enter` to change its value.
`Esc` returns to practice. Choose your mode, letters, adaptation, palette,
keyboard, language, and exercise length (10, 25, or 50 words; use `--words`
for other lengths). The timer pauses in menus and undersized terminals.

## Keyboard and settings

The optional keyboard shows the selected layout and highlights the next key,
including Space. Turn it on in settings or with `Ctrl+K`.

![stuk with the optional keyboard](docs/keyboard.png)

The keyboard needs at least 46 × 22 terminal cells. In smaller windows it
temporarily disappears while its saved preference stays enabled. The app
adapts to resizing and keeps the cursor visible. Below 32 × 12, typing pauses.

Settings are saved to `$XDG_CONFIG_HOME/stuk/settings.json`, falling back to
`~/.config/stuk/settings.json`. Command-line options override saved preferences
for the current launch. Invalid settings are ignored. Remove this file to reset
preferences; practice history is stored separately.

A wrong character does not block typing. You can correct it until the exercise
ends; accuracy still counts corrected mistakes. Speed uses correctly typed
characters, with five characters counting as one word.

For the full palette, use a terminal with 256 colors, such as
`TERM=xterm-256color`. Other terminals use basic colors or monochrome.
All vocabulary is bundled, and practice needs no network connection.

## Input layout

Type with either the Russian or English system layout: input maps to the
physical keys of the selected practice language. For example, `ghbdtn` counts
as `привет` in Russian, and `руддщ` becomes `hello` in English. This also works
in the custom-letter editor.

The mapping includes `ё`, `х`, `ъ`, `ж`, `э`, `б`, `ю` and their English
punctuation keys. Case is preserved, so Shift and Caps Lock still affect
correctness. Mapping never depends on the expected character: the wrong key
remains a mistake. Shortcuts are handled separately.

Standard QWERTY and ЙЦУКЕН layouts are used. Terminals send characters rather
than physical key codes, so ambiguous punctuation such as `.` in Russian
practice is interpreted as the English-layout key for `ю`.

## Adaptive practice

Adaptation is on by default. Turn it off in `F2` or set `"adaptive": false` in
settings. Up to three focus letters appear above the text: newly unlocked
letters and letters that need more accuracy or speed.

The next exercise includes these letters more often, including rare ones.
At least 35% of word selections remain ordinary selections within your chosen
alphabet. Adjacent repeats are avoided when the word pool allows it.
Analysis uses the latest 30 completed exercises in the selected language,
including corrected mistakes. Menu time and long pauses are excluded from
inter-letter timing.

After an exercise, see its number and your confident-letter count. With enough
history, results also compare speed with the previous five exercises of the
same language and length, or show a personal best. Comparisons require three
earlier exercises; personal bests require at least 90% accuracy.

A letter is confident after 12 attempts at 97% accuracy or better, with at least
five measured intervals averaging no more than 0.5 seconds. Current confidence
uses the latest 30 exercises: 33 letters in Russian and 26 in English.

## Letter unlocks and practice modes

**Guided** practice starts with six letters: `е н о т а с` in Russian and
`e n i r a t` in English. Text uses only unlocked letters. Each stage supports
real words, and the newest letter gets extra practice.

Once every available letter has reached the confidence threshold at least
once, the next letter unlocks. Earned unlocks are permanent, even if later
exercises go worse. Existing practice history also counts.

Change your mode at any time in `F2`:

- **Guided** (`guided`): gradually unlock letters.
- **All letters** (`free`): use the entire alphabet from the start.
- **Custom letters** (`custom`): practice only your chosen set.

Select custom letters and press `Enter` to edit. `Ctrl+U` clears the field,
`Enter` applies the set and enables custom mode, and `Esc` cancels editing.
RU/EN sets are saved separately. One letter is enough; duplicates and characters
outside the selected alphabet are removed. When real words cannot cover the
whole set, a clearly labeled letter drill uses only your chosen letters.

Free and custom practice count toward guided unlocks. Turning adaptation off
keeps your chosen mode. CLI options: `--mode guided|free|custom`; `--letters`
selects a custom set and takes precedence over `--mode` for that launch.

## Progress and charts

Press `F3` to see speed and accuracy charts, exercise count, practice time,
confident letters, and current focus. `Tab`, `F4`, or `←→` changes the viewed
language without changing your exercise. `Esc` returns to where you left off,
excluding the time spent viewing progress.

Use `↑/↓` to switch between charts and letters; `L` opens letters and `G`
opens charts. The letters screen shows mastered letters, the set available in
your current mode, and the next guided unlock. Mastery is permanent; confidence
on the charts reflects recent practice.

![Letter progress and the next unlock — demo data](docs/letters.png)

![Progress charts — demo data](docs/progress.png)

These captures use a temporary demo profile. Your own charts appear after your
first completed exercise. They show the latest 30 exercises per language,
with exercise numbers on the horizontal axis. Larger screens zoom the accuracy
scale to your results and label its bounds; compact charts use 0–100%.

History is stored at `$XDG_DATA_HOME/stuk/history.json`, falling back to
`~/.local/share/stuk/history.json`. Only completed exercises are saved, once
each. Restarting, switching languages, or quitting mid-exercise adds no record.
Records contain results and per-letter aggregates, not the text you typed.
Copy the history file to back it up.

Writes are atomic and locked across simultaneous instances. If saving fails,
a warning appears and stuk retries after the next completion, when opening
progress, and on exit. Until then, results stay in the running app.
Damaged history files are never automatically overwritten.

## Colors

The default **Graphite Lavender** palette uses `#16161e` for the background,
`#e1dbea` for text, and `#c4b5fd` for accents. Settings offer `lavender`,
`terminal` (your terminal's own colors), and `warm` (sand tones). Changes apply
immediately.

Override individual roles in the settings file; other roles keep the palette
defaults:

```json
{
  "language": "en",
  "words": 25,
  "show_keyboard": true,
  "adaptive": true,
  "practice_mode": "guided",
  "custom_letters": {"ru": "енотас", "en": "enirat"},
  "theme": "lavender",
  "colors": {
    "accent": "#c4b5fd",
    "error": "#ed9aaa"
  }
}
```

| Color role | Purpose |
| --- | --- |
| `background` | App background |
| `foreground` | Correctly typed characters and primary text |
| `pending` | Characters still to type |
| `muted` | Labels and keyboard |
| `border` | Borders and the unfilled progress bar |
| `accent` | Cursor, active key, selection, and progress |
| `error` | Mistakes |
| `cursor_text` | Character on the cursor background |

Values can be `#RRGGBB`, ANSI/xterm indices `0–255`, or `"default"`.
For example, `"background": "default"` keeps the terminal background, including
transparency. Explicit overrides take priority over palettes; use `"colors": {}`
to reset them. Restart after editing the file by hand.

See [examples/settings.json](examples/settings.json) for a complete example.
Exact RGB is used with direct color or a mutable terminal palette; otherwise,
stuk selects the nearest available color.

## Development

```sh
PYTHONPATH=src python3 -m stuk
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q install.py src tests
```

Ruff is only needed for development:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[dev]'
.venv/bin/ruff format install.py src tests
.venv/bin/ruff check install.py src tests
```

Source lives in `src/stuk/`. Input and timing are in `session.py`; vocabulary,
adaptation, and unlocks in `words.py`, `adaptive.py`, and `curriculum.py`;
screens and layout in `tui.py`, `layout.py`, and `keyboard.py`; preferences and
colors in `settings.py`, `theme.py`, and `palette.py`; persistence and progress
in `history.py`, `charts.py`, `progress.py`, and `letters.py`; CLI handling in
`cli.py`. The standalone installer is `install.py`.

Tests use the standard library, including real terminal sessions via PTY and
isolated installation checks. They never use real practice history.

Inspired by [btyper](https://github.com/Ada-lave/btyper). stuk's code and
vocabulary were written independently.
