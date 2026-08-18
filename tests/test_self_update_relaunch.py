"""Regression tests for the self-update relaunch chain (4.0.29): `open -n` forces a
genuinely new instance, the relaunch is actively verified (not assumed), the update-bar
status never masquerades as a clickable button while non-actionable, and the app never
silently drifts to another port when its usual one is taken by something foreign.

Covers: _wait_for_relaunch's timeout/success paths, _verify_and_finish_relaunch's
terminal-error path when the relaunch never shows up, _handle_port_conflict only
proceeding on an explicit 'temp' choice from the (monkeypatched) dialog, the update-bar
JS not applying button styling while working/restarting, and the real
old-server-running -> new-version-launch -> takeover -> same-port chain end to end."""
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _hold(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


class WaitForRelaunch(unittest.TestCase):
    """_wait_for_relaunch: verifies a NEW version actually answers, doesn't just assume
    the launch worked, and gives up after its window instead of polling forever."""

    def test_times_out_when_nothing_answers(self):
        port = _free_port()  # nobody listening -> every poll fails
        t0 = time.time()
        ok = app._wait_for_relaunch(port, "1.0.0", window=1.0)
        self.assertFalse(ok)
        self.assertLess(time.time() - t0, 3.0)  # didn't hang past the window

    def test_succeeds_once_a_new_version_answers(self):
        # a server whose /api/status reports a version different from the old one
        old_ver = app.__version__
        app.__version__ = "9.9.9-newtest"
        srv = app.make_server("127.0.0.1", 0)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            ok = app._wait_for_relaunch(port, old_ver, window=10.0)
            self.assertTrue(ok)
        finally:
            app.__version__ = old_ver
            srv.shutdown()
            th.join(timeout=5)
            srv.server_close()

    def test_same_version_answering_does_not_count(self):
        # the OLD server itself is still up and answering — that's not a relaunch
        srv = app.make_server("127.0.0.1", 0)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            ok = app._wait_for_relaunch(port, app.__version__, window=1.0)
            self.assertFalse(ok)
        finally:
            srv.shutdown()
            th.join(timeout=5)
            srv.server_close()


class VerifyAndFinishRelaunch(unittest.TestCase):
    """When the relaunch never shows up (even after the one retry), the updater must
    leave a terminal, actionable error state instead of silently giving up."""

    def tearDown(self):
        app._set_update("idle", "", 0, target=None)

    def test_relaunch_failure_sets_terminal_error_state(self):
        popen_calls = []

        def fake_wait_for_relaunch(port, old_version, window=None, host="127.0.0.1"):
            return False

        import subprocess as sp
        real = sp.Popen

        def fake_popen(args, **kw):
            popen_calls.append(args)
            class _P:
                pass
            return _P()

        orig_wait = app._wait_for_relaunch
        sp.Popen = fake_popen
        app._wait_for_relaunch = fake_wait_for_relaunch
        try:
            app._verify_and_finish_relaunch(_free_port(), "/tmp/Fake.app", "1.0.0")
        finally:
            sp.Popen = real
            app._wait_for_relaunch = orig_wait

        with app._UPDATE["lock"]:
            state = app._UPDATE["state"]
            detail = app._UPDATE["detail"]
        self.assertEqual(state, "error")
        self.assertIn("quit", detail.lower())
        self.assertEqual(len(popen_calls), 1)          # exactly one retry attempt
        self.assertEqual(popen_calls[0][0], "open")
        self.assertIn("-n", popen_calls[0])

    def test_relaunch_success_on_retry_leaves_no_error(self):
        results = iter([False, True])   # fails once, succeeds on the retry
        app._set_update("relaunching", "x", 100, target="9.9.9")
        orig_wait = app._wait_for_relaunch
        app._wait_for_relaunch = lambda *a, **k: next(results)
        import subprocess as sp
        real = sp.Popen
        sp.Popen = lambda *a, **k: type("P", (), {})()
        try:
            app._verify_and_finish_relaunch(_free_port(), "/tmp/Fake.app", "1.0.0")
        finally:
            app._wait_for_relaunch = orig_wait
            sp.Popen = real
        with app._UPDATE["lock"]:
            self.assertNotEqual(app._UPDATE["state"], "error")


class PortConflictDialog(unittest.TestCase):
    """_handle_port_conflict must only fall back to another port when the (native-dialog)
    choice function explicitly says 'temp' — never on its own."""

    def test_quit_choice_never_touches_bind_fallback(self):
        avoid = app.PORT_CANDIDATES[0]
        try:
            holder = _hold(avoid)
        except OSError:
            self.skipTest(f"port {avoid} already in use on this machine")
        orig_dialog = app._port_conflict_dialog
        orig_fallback = app._bind_fallback

        def boom(*a, **k):
            raise AssertionError("_bind_fallback must not be called when the user quits")

        app._port_conflict_dialog = lambda port, holder: "quit"
        app._bind_fallback = boom
        try:
            result = app._handle_port_conflict("127.0.0.1", avoid)
            self.assertIsNone(result)
        finally:
            app._port_conflict_dialog = orig_dialog
            app._bind_fallback = orig_fallback
            holder.close()

    def test_explicit_temp_choice_lands_on_a_stable_candidate(self):
        avoid = app.PORT_CANDIDATES[0]
        try:
            holder = _hold(avoid)
        except OSError:
            self.skipTest(f"port {avoid} already in use on this machine")
        orig_dialog = app._port_conflict_dialog
        app._port_conflict_dialog = lambda port, holder: "temp"
        try:
            result = app._handle_port_conflict("127.0.0.1", avoid)
            self.assertIsNotNone(result)
            srv, on_temp = result
            try:
                self.assertTrue(on_temp)
                self.assertIn(srv.server_address[1], app.PORT_CANDIDATES)
                self.assertNotEqual(srv.server_address[1], avoid)
            finally:
                srv.server_close()
        finally:
            app._port_conflict_dialog = orig_dialog
            holder.close()


class UpdateBarNotAButton(unittest.TestCase):
    """The Updating…/Restarting… states must not look like a clickable button (dropped
    chrome + spinner), only actionable states (error/retry) keep the button look."""

    def test_working_state_strips_button_chrome_and_shows_a_spinner(self):
        html = app.shell("Test", "<p>body</p>")
        self.assertIn(".updbtn.working{", html)
        self.assertIn("updspin", html)
        # setMsg toggles the 'working' class and swaps in the spinner markup
        self.assertIn("go.classList.toggle('working'", html)
        self.assertIn("setMsg(", html)
        self.assertIn(",true)", html)

    def test_waitforrelaunch_times_out_instead_of_polling_forever(self):
        html = app.shell("Test", "<p>body</p>")
        self.assertIn("relaunchFailed", html)
        self.assertIn("deadline", html)

    def test_relaunch_failure_retry_rechecks_status_instead_of_redownloading(self):
        # Regression: clicking the "Installed, but didn't restart…" state used to re-run the
        # WHOLE update flow (confirm() -> re-download -> re-verify) because it's the same
        # #updgo button with its original click listener still attached. It must instead just
        # recheck /api/status and reload if the new version is already up — no confirm(), no
        # POST to /api/self_update.
        html = app.shell("Test", "<p>body</p>")
        self.assertIn("go.dataset.relaunchRetry", html)
        # the recheck branch must come before the confirm() call in source order, so it's
        # reached first on a retry click
        i_retry = html.index("go.dataset.relaunchRetry==='1'")
        i_confirm = html.index("if(!confirm(")
        self.assertLess(i_retry, i_confirm)
        # relaunchFailed() must flag the retry state so the next click takes that branch
        relaunch_failed = html[html.index("function relaunchFailed()"):]
        self.assertIn("go.dataset.relaunchRetry='1'", relaunch_failed[:300])

    def test_client_relaunch_deadline_not_tighter_than_server_patience(self):
        # The server (_verify_and_finish_relaunch) waits _RELAUNCH_VERIFY_WINDOW, retries the
        # launch once, then waits it out again — roughly double the constant. The browser's own
        # waitForRelaunch deadline must clear that, or it declares failure while the server is
        # still legitimately retrying (e.g. a slow ditto/mv bundle swap under disk/CPU load).
        html = app.shell("Test", "<p>body</p>")
        self.assertGreaterEqual(app._RELAUNCH_VERIFY_WINDOW, 60.0)
        m = re.search(r"var deadline=Date\.now\(\)\+(\d+);", html)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)) / 1000.0, 2 * app._RELAUNCH_VERIFY_WINDOW)


_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

_OLD_SERVER_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from ai_session_search import app
app.__version__ = "1.0.0-oldtest"
app.CONFIG_DIR = {cfg!r}
srv = app.make_server("127.0.0.1", {port!r})
app._write_runtime_file({port!r})
srv.serve_forever()
"""


class OldServerReplacedByNewOnSamePort(unittest.TestCase):
    """(5) The real chain: an old-version server is running on committed port P; starting
    up as a new version with P as the committed port must kill the old one and land the
    new server on that SAME port P — never drift elsewhere.

    The "old" server runs in a real child process (not just another thread of this test),
    both because that's what actually happens (a separate app instance) and because
    _replace_stale_server's last-resort path kills the PID /api/status reports — which
    must never be this test process's own PID."""

    def setUp(self):
        self.cfg_dir = tempfile.mkdtemp(prefix="aiss-itest-cfg-")
        self.saved_cfg = app.CONFIG_DIR
        app.CONFIG_DIR = self.cfg_dir
        self.saved_version = app.__version__
        self.port = _free_port()
        app._commit_port(self.port)
        self.old_proc = None

    def tearDown(self):
        if self.old_proc and self.old_proc.poll() is None:
            self.old_proc.kill()
            self.old_proc.wait(timeout=5)
        app.CONFIG_DIR = self.saved_cfg
        app.__version__ = self.saved_version
        shutil.rmtree(self.cfg_dir, ignore_errors=True)

    def test_new_version_reclaims_the_committed_port_from_the_old_server(self):
        import subprocess
        script = _OLD_SERVER_SCRIPT.format(src=_SRC_DIR, cfg=self.cfg_dir, port=self.port)
        self.old_proc = subprocess.Popen([sys.executable, "-c", script],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # wait for the old server to actually come up
        d = None
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/status", timeout=1) as r:
                    d = json.loads(r.read().decode())
                break
            except Exception:
                time.sleep(0.1)
        self.assertIsNotNone(d, "old-version server never came up")
        self.assertEqual(d.get("version"), "1.0.0-oldtest")

        # "new version" starting up: same committed port, newer version.
        app.__version__ = "2.0.0-newtest"
        running, running_ver = app._running_server([self.port], "127.0.0.1")
        self.assertEqual(running, self.port)
        self.assertEqual(running_ver, "1.0.0-oldtest")
        freed = app._replace_stale_server(self.port, "127.0.0.1")
        self.assertTrue(freed, "expected the stale old-version server to be reclaimed")

        new_srv = app._bind_retrying("127.0.0.1", self.port, attempts=20, delay=0.2)
        try:
            self.assertIsNotNone(new_srv, "the new instance must land on the SAME port")
            self.assertEqual(new_srv.server_address[1], self.port)
            # the old process is really gone, not just unresponsive
            self.old_proc.wait(timeout=5)
            self.assertIsNotNone(self.old_proc.poll())
        finally:
            if new_srv is not None:
                new_srv.server_close()


if __name__ == "__main__":
    unittest.main()
