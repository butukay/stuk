"""Exercise installation and updates without network access or user files."""

import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stuk_installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def source_archive(version: str | None = None) -> bytes:
    """Use the real package, as a GitHub source ZIP would contain it."""
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for path in (ROOT / "src" / "stuk").glob("*.py"):
            content = path.read_bytes()
            if version is not None and path.name == "__init__.py":
                content = f'__version__ = "{version}"\n'.encode()
            archive.writestr(f"stuk-master/src/stuk/{path.name}", content)
    return payload.getvalue()


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="stuk-install-test-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name) / "home with spaces"
        self.home.mkdir()
        self.data = self.home / "data"
        self.config = self.home / "config"
        self.bin = self.home / ".local" / "bin"
        self.command = self.bin / "stuk"
        self.app = self.data / "stuk" / "stuk.pyz"
        self.environment = {
            "XDG_DATA_HOME": str(self.data),
            "XDG_CONFIG_HOME": str(self.config),
            "SHELL": "/bin/bash",
            "PATH": "/usr/bin:/bin",
            "ZDOTDIR": "",
        }
        self.output = io.StringIO()
        self.errors = io.StringIO()

    def install(self, payload: bytes | None = None) -> int:
        archive = source_archive() if payload is None else payload
        with (
            patch.dict(os.environ, self.environment),
            patch.object(installer.Path, "home", return_value=self.home),
            patch.object(
                installer.urllib.request, "urlopen", return_value=io.BytesIO(archive)
            ) as download,
            redirect_stdout(self.output),
            redirect_stderr(self.errors),
        ):
            self.download = download
            return installer.main()

    def run_installed(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(self.environment)
        environment.pop("PYTHONPATH", None)
        return subprocess.run(
            [str(self.command), *arguments],
            cwd=self.home,
            env=environment,
            input="",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    def test_fresh_install_runs_outside_checkout_and_sets_up_bash(self) -> None:
        profile = self.home / ".profile"
        profile.write_text("# keep this preference\n")
        self.assertEqual(self.install(), 0, self.errors.getvalue())
        self.assertTrue(self.command.is_symlink())
        self.assertEqual(self.command.resolve(), self.app)
        self.assertTrue(os.access(self.command, os.X_OK))
        result = self.run_installed("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--lang", result.stdout)
        self.assertIn("--letters", result.stdout)
        self.assertTrue(profile.read_text().startswith("# keep this preference\n"))
        self.assertIn(installer.PATH_MARKER, (self.home / ".bashrc").read_text())
        environment = os.environ.copy()
        environment.update(self.environment)
        result = subprocess.run(
            ["/bin/sh", "-c", '. "$1"; command -v stuk', "sh", str(profile)],
            cwd=self.home,
            env=environment,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.stdout.strip(), str(self.command))
        self.assertIn("Open a new terminal", self.output.getvalue())

    def test_update_replaces_app_without_touching_learning_data_or_profiles(
        self,
    ) -> None:
        history = self.data / "stuk" / "history.json"
        settings = self.config / "stuk" / "settings.json"
        for path in (history, settings):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"user data must survive unchanged\n")
        self.assertEqual(self.install(), 0, self.errors.getvalue())
        profile = (self.home / ".bashrc").read_bytes()
        self.assertEqual(
            self.install(source_archive("9.9.9")), 0, self.errors.getvalue()
        )
        self.assertEqual(self.run_installed("--version").stdout.strip(), "stuk 9.9.9")
        self.assertEqual((self.home / ".bashrc").read_bytes(), profile)
        for path in (history, settings):
            self.assertEqual(path.read_bytes(), b"user data must survive unchanged\n")
        self.assertEqual(list(self.app.parent.glob(".install-*")), [])

    def test_broken_download_leaves_previous_command_working(self) -> None:
        self.assertEqual(self.install(), 0, self.errors.getvalue())
        previous = self.run_installed("--version").stdout
        self.assertEqual(self.install(b"not a zip archive"), 1)
        self.assertEqual(self.run_installed("--version").stdout, previous)
        self.assertEqual(list(self.app.parent.glob(".install-*")), [])

    def test_previous_venv_install_can_be_upgraded(self) -> None:
        legacy = self.home / ".local" / "share" / "stuk" / "app" / "bin" / "stuk"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("old executable")
        self.bin.mkdir(parents=True)
        self.command.symlink_to(legacy)
        self.assertEqual(self.install(), 0, self.errors.getvalue())
        self.assertEqual(self.run_installed("--version").returncode, 0)
        self.assertEqual(legacy.read_text(), "old executable")

    def test_unrelated_command_is_preserved(self) -> None:
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                self.bin.mkdir(parents=True, exist_ok=True)
                target = self.home / "another-program"
                target.write_text("unrelated executable")
                if symlink:
                    self.command.symlink_to(target)
                else:
                    self.command.write_text("unrelated executable")
                self.assertEqual(self.install(), 1)
                self.assertEqual(self.command.read_text(), "unrelated executable")
                self.assertFalse(self.app.exists())
                self.command.unlink()

    def test_path_setup_respects_zsh_fish_and_existing_path(self) -> None:
        for shell, profile in (
            ("/bin/zsh", self.home / ".zshrc"),
            ("/usr/bin/fish", self.config / "fish" / "conf.d" / "stuk.fish"),
        ):
            with self.subTest(shell=shell):
                self.environment["SHELL"] = shell
                self.assertEqual(self.install(), 0, self.errors.getvalue())
                content = profile.read_text()
                self.assertIn(str(self.bin), content)
                self.assertEqual(self.install(), 0, self.errors.getvalue())
                self.assertEqual(profile.read_text(), content)
        self.environment["PATH"] = str(self.bin) + ":/usr/bin:/bin"
        self.output = io.StringIO()
        self.assertEqual(self.install(), 0, self.errors.getvalue())
        self.assertNotIn("Open a new terminal", self.output.getvalue())

    def test_invalid_archive_paths_and_missing_modules_are_rejected(self) -> None:
        for name in ("stuk-master/src/stuk/../../outside.py", "stuk-master/README.md"):
            with self.subTest(name=name):
                payload = io.BytesIO()
                with zipfile.ZipFile(payload, "w") as archive:
                    archive.writestr(name, "not a package")
                self.assertEqual(self.install(payload.getvalue()), 1)
                self.assertFalse(self.command.exists())
                self.assertFalse((self.home / "outside.py").exists())

    def test_old_python_is_rejected_before_download_or_file_changes(self) -> None:
        with patch.object(installer.sys, "version_info", (3, 9)):
            self.assertEqual(self.install(), 1)
            self.download.assert_not_called()
        self.assertIn("Python 3.10", self.errors.getvalue())
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
