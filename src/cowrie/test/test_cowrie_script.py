# SPDX-FileCopyrightText: 2026 Michel Oosterhof <michel@oosterhof.net>
#
# SPDX-License-Identifier: BSD-3-Clause

# ABOUTME: tests for cowrie/scripts/cowrie.py — the cowrie start/stop entry point
# ABOUTME: covers the init-marker check on cowrie start

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cowrie.scripts import cowrie as cowrie_script


class CheckInitializedTests(unittest.TestCase):
    """check_initialized refuses to proceed unless cwd has a cowrie config."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self._prior_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        self.addCleanup(os.chdir, self._prior_cwd)

    def test_accepts_etc_cowrie_cfg(self) -> None:
        (Path(self.tmpdir) / "etc").mkdir()
        (Path(self.tmpdir) / "etc" / "cowrie.cfg").write_text("")

        cowrie_script.check_initialized()  # should not raise

    def test_accepts_etc_cowrie_cfg_dist(self) -> None:
        (Path(self.tmpdir) / "etc").mkdir()
        (Path(self.tmpdir) / "etc" / "cowrie.cfg.dist").write_text("")

        cowrie_script.check_initialized()  # should not raise

    def test_accepts_source_checkout_layout(self) -> None:
        bundled = Path(self.tmpdir) / "src" / "cowrie" / "data" / "etc"
        bundled.mkdir(parents=True)
        (bundled / "cowrie.cfg.dist").write_text("")

        cowrie_script.check_initialized()  # should not raise

    def test_refuses_when_neither_present(self) -> None:
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stderr),
            self.assertRaises(SystemExit) as ctx,
        ):
            cowrie_script.check_initialized()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("not initialized", stderr.getvalue())


class CowrieStartTests(unittest.TestCase):
    """cowrie start runs twistd in-process so it shares our sys.path.

    An external twistd found on PATH may belong to a different Python
    environment that cannot import the cowrie package or find its twisted
    plugin.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self._prior_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        self.addCleanup(os.chdir, self._prior_cwd)
        self._prior_argv = sys.argv[:]
        self.addCleanup(lambda: setattr(sys, "argv", self._prior_argv))
        (Path(self.tmpdir) / "etc").mkdir()
        (Path(self.tmpdir) / "etc" / "cowrie.cfg").write_text("")

    def test_stdout_mode_runs_twistd_in_process(self) -> None:
        with (
            mock.patch.dict(
                os.environ, {"COWRIE_STDOUT": "yes", "AUTHBIND_ENABLED": "no"}
            ),
            mock.patch("os.execvp") as execvp,
            mock.patch("twisted.scripts.twistd.run") as run,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as ctx,
        ):
            cowrie_script.cowrie_start([])

        self.assertEqual(ctx.exception.code, 0)
        execvp.assert_not_called()
        run.assert_called_once_with()
        self.assertEqual(
            sys.argv,
            [
                "twistd",
                "--umask=0022",
                "-n",
                "--logger",
                "cowrie.python.logfile.stdoutLogger",
                "cowrie",
            ],
        )


class CowrieInitTests(unittest.TestCase):
    """cowrie init materialises ./etc/cowrie.cfg from the bundled template."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self._prior_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        self.addCleanup(os.chdir, self._prior_cwd)

    def test_writes_etc_cowrie_cfg(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cowrie_script.cowrie_init()

        target = Path(self.tmpdir) / "etc" / "cowrie.cfg"
        self.assertTrue(target.is_file())
        # Bytes match the bundled template.
        from cowrie.core.resources import read_data_bytes

        self.assertEqual(target.read_bytes(), read_data_bytes("etc", "cowrie.cfg.dist"))

    def test_satisfies_init_marker_after_running(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            cowrie_script.cowrie_init()
            cowrie_script.check_initialized()  # should not raise

    def test_creates_var_skeleton(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            cowrie_script.cowrie_init()

        for sub in (
            "var/log/cowrie",
            "var/lib/cowrie",
            "var/lib/cowrie/downloads",
            "var/lib/cowrie/tty",
            "var/run",
        ):
            self.assertTrue((Path(self.tmpdir) / sub).is_dir(), f"{sub} not created")

    def test_refuses_to_overwrite_existing(self) -> None:
        (Path(self.tmpdir) / "etc").mkdir()
        (Path(self.tmpdir) / "etc" / "cowrie.cfg").write_text("custom")

        out = io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as ctx,
        ):
            cowrie_script.cowrie_init()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("already exists", out.getvalue())
        # File untouched.
        self.assertEqual(
            (Path(self.tmpdir) / "etc" / "cowrie.cfg").read_text(), "custom"
        )
