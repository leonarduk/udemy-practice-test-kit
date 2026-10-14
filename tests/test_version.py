"""The package version has one source of truth, and the CLI reports it."""

import contextlib
import importlib.metadata
import io
import unittest

import ptkit
from ptkit import cli


class VersionTests(unittest.TestCase):
    def test_installed_metadata_matches_dunder_version(self):
        # pyproject.toml reads its version from ptkit.__version__; if that
        # wiring breaks, an installed kit reports a version that doesn't
        # move when __version__ is bumped, and course repos' `pip install`
        # goes back to silently keeping a stale kit.
        try:
            installed = importlib.metadata.version("udemy-practice-test-kit")
        except importlib.metadata.PackageNotFoundError:
            self.skipTest("kit not installed; run `pip install -e .`")
        self.assertEqual(installed, ptkit.__version__)

    def test_cli_prints_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            cli.main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"ptkit {ptkit.__version__}")


if __name__ == "__main__":
    unittest.main()
