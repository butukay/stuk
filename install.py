#!/usr/bin/env python3
"""Install the latest stuk using only the Python standard library."""

from __future__ import annotations

import io
import os
import shlex
import subprocess
import sys
import tempfile
import urllib.request
import zipapp
import zipfile
from pathlib import Path, PurePosixPath

SOURCE_URL = "https://codeload.github.com/butukay/stuk/zip/refs/heads/master"
PATH_MARKER = "# stuk: command path"


def check_python() -> None:
    """Fail before downloading or changing files if Python cannot run stuk."""
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")
    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        raise RuntimeError("stuk supports Linux and macOS.")
    try:
        import curses  # noqa: F401
    except ImportError as error:
        raise RuntimeError(
            "Install Python with curses support, then try again."
        ) from error


def build_app(source: bytes, target: Path) -> None:
    """Package source modules without extracting paths from the downloaded ZIP."""
    archive = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as upstream:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            modules = set()
            for entry in upstream.infolist():
                parts = PurePosixPath(entry.filename).parts
                if len(parts) < 4 or parts[1:3] != ("src", "stuk"):
                    continue
                if ".." in parts or parts[0] == "/":
                    raise RuntimeError("The source archive contains an invalid path.")
                if not entry.filename.endswith(".py"):
                    continue
                name = str(PurePosixPath(*parts[2:]))
                if name in modules:
                    raise RuntimeError("The source archive contains duplicate modules.")
                modules.add(name)
                package.writestr(name, upstream.read(entry))
            if not {"stuk/__init__.py", "stuk/cli.py", "stuk/tui.py"} <= modules:
                raise RuntimeError("The source archive is missing stuk modules.")
            package.writestr(
                "__main__.py", "from stuk.cli import main\nraise SystemExit(main())\n"
            )
    archive.seek(0)
    zipapp.create_archive(archive, target, interpreter="/usr/bin/env python3")
    target.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    subprocess.run(
        [sys.executable, str(target), "--version"],
        cwd=target.parent,
        env=environment,
        check=True,
        capture_output=True,
        timeout=15,
    )


def add_to_path(home: Path, bin_dir: Path) -> bool:
    """Make the command available in new terminals without duplicating entries."""
    if str(bin_dir) in os.environ.get("PATH", "").split(os.pathsep):
        return False
    shell = Path(os.environ.get("SHELL", "/bin/sh")).name
    quoted = shlex.quote(str(bin_dir))
    snippet = (
        f"\n{PATH_MARKER}\n"
        f'case ":$PATH:" in\n'
        f"    *:{quoted}:*) ;;\n"
        f'    *) export PATH={quoted}:"$PATH" ;;\n'
        "esac\n"
    )
    if shell == "fish":
        configured = Path(os.environ.get("XDG_CONFIG_HOME", ""))
        config = configured if configured.is_absolute() else home / ".config"
        files = [config / "fish" / "conf.d" / "stuk.fish"]
        fish_path = "'" + str(bin_dir).replace("\\", "\\\\").replace("'", "\\'") + "'"
        snippet = (
            f"\n{PATH_MARKER}\n"
            f"if not contains -- {fish_path} $PATH\n"
            f"    set -gx PATH {fish_path} $PATH\nend\n"
        )
    elif shell == "zsh":
        configured = Path(os.environ.get("ZDOTDIR", ""))
        directory = configured if configured.is_absolute() else home
        files = [directory / ".zshrc"]
    elif shell == "bash":
        login = next(
            (
                home / name
                for name in (".bash_profile", ".bash_login")
                if (home / name).exists()
            ),
            home / ".profile",
        )
        files = [home / ".bashrc", login]
    else:
        files = [home / ".profile"]
    for path in files:
        content = path.read_text() if path.exists() else ""
        if PATH_MARKER not in content:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as profile:
                profile.write(snippet)
    return True


def main() -> int:
    """Download, verify, and atomically replace the user installation."""
    try:
        check_python()
        home = Path.home()
        configured = Path(os.environ.get("XDG_DATA_HOME", ""))
        data = configured if configured.is_absolute() else home / ".local" / "share"
        app_dir = data / "stuk"
        bin_dir = home / ".local" / "bin"
        command = bin_dir / "stuk"
        app = app_dir / "stuk.pyz"
        legacy = home / ".local" / "share" / "stuk" / "app" / "bin" / "stuk"
        if command.is_symlink():
            if command.resolve() not in (
                app.resolve(),
                legacy.resolve(),
                (app_dir / "app" / "bin" / "stuk").resolve(),
            ):
                raise RuntimeError(
                    f"{command} points to another program; move it before installing."
                )
        elif command.exists():
            raise RuntimeError(f"{command} already exists; move it before installing.")
        print("Downloading stuk…", flush=True)
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            source = response.read()
        app_dir.mkdir(parents=True, exist_ok=True)
        bin_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".install-", dir=app_dir) as temporary:
            staged = Path(temporary) / "stuk.pyz"
            build_app(source, staged)
            # Create the replacement link before replacing a working installation.
            with tempfile.TemporaryDirectory(prefix=".stuk-", dir=bin_dir) as links:
                link = Path(links) / "stuk"
                link.symlink_to(app)
                os.replace(staged, app)
                os.replace(link, command)
        needs_terminal = add_to_path(home, bin_dir)
    except (
        OSError,
        RuntimeError,
        ValueError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as error:
        print(f"stuk installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Installed stuk to {command}")
    if needs_terminal:
        print(
            f"Open a new terminal and run stuk, or run {shlex.quote(str(command))} now."
        )
    else:
        print("Run stuk to start.")
    print(
        "Run the same installation command to update. Your progress and settings are kept."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
