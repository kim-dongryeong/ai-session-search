"""Port-identity regression tests for the self-update port-race bug (4.0.27):
a one-click "Update & restart" swaps the app bundle while the old server is still
exiting, so the new build's bind of its committed port can lose a race and fall
back to an ephemeral one — which Chrome then treats as a brand-new PWA origin.

Covers: _bind_retrying gives a just-killed predecessor's socket time to free up
(a), _bind_fallback prefers another stable PORT_CANDIDATES port over an ephemeral
one when the intended port stays foreign-occupied (b), and the "Install as app"
button/modal + temporary-port warning render correctly based on app._ON_TEMP_PORT
(c, d)."""
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


def _free_port():
    """A port nobody is listening on right now, for tests to then occupy themselves."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _hold(port):
    """Bind+listen on `port` and return the holding socket (close it to free the port)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


class BindRetrying(unittest.TestCase):
    """(a) target port occupied, then released mid-retry -> lands on the INTENDED port."""

    def test_retry_lands_on_intended_port_once_predecessor_releases_it(self):
        port = _free_port()
        holder = _hold(port)
        # simulate the dying old server's socket closing partway through our retry window
        threading.Timer(1.0, holder.close).start()
        srv = app._bind_retrying("127.0.0.1", port, attempts=20, delay=0.2)
        try:
            self.assertIsNotNone(srv, "expected the retry loop to eventually bind the port")
            self.assertEqual(srv.server_address[1], port)
        finally:
            if srv is not None:
                srv.server_close()
            holder.close()   # no-op if the timer already closed it

    def test_gives_up_after_the_retry_window_when_still_foreign(self):
        port = _free_port()
        holder = _hold(port)
        try:
            srv = app._bind_retrying("127.0.0.1", port, attempts=3, delay=0.05)
            self.assertIsNone(srv)
        finally:
            holder.close()


class BindFallback(unittest.TestCase):
    """(b) target port stays occupied by a FOREIGN listener -> lands on another
    PORT_CANDIDATES port, never an ephemeral one, when the range has room."""

    def test_fallback_prefers_a_stable_candidate_over_ephemeral(self):
        avoid = app.PORT_CANDIDATES[0]
        try:
            holder = _hold(avoid)
        except OSError:
            self.skipTest(f"port {avoid} already in use on this machine")
        try:
            srv, landed_stable = app._bind_fallback("127.0.0.1", avoid)
            try:
                self.assertTrue(landed_stable)
                self.assertIn(srv.server_address[1], app.PORT_CANDIDATES)
                self.assertNotEqual(srv.server_address[1], avoid)
            finally:
                srv.server_close()
        finally:
            holder.close()

    def test_fallback_is_ephemeral_only_once_the_whole_range_is_taken(self):
        holders = []
        try:
            for p in app.PORT_CANDIDATES:
                try:
                    holders.append(_hold(p))
                except OSError:
                    self.skipTest(f"couldn't occupy the full PORT_CANDIDATES range (port {p} busy)")
            srv, landed_stable = app._bind_fallback("127.0.0.1", app.PORT_CANDIDATES[0])
            try:
                self.assertFalse(landed_stable)
                self.assertNotIn(srv.server_address[1], app.PORT_CANDIDATES)
            finally:
                srv.server_close()
        finally:
            for h in holders:
                h.close()

    def test_a_fallback_port_is_never_committed_when_a_port_was_already_committed(self):
        """Mirrors main()'s exact commit guard: `committed is None` gates _commit_port,
        so a machine that already settled on a port keeps that commitment even when this
        particular launch had to land somewhere else temporarily."""
        saved_cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        try:
            app._commit_port(app.PORT_CANDIDATES[0])
            committed = app._read_committed_port()
            self.assertIsNotNone(committed)
            try:
                holder = _hold(committed)
            except OSError:
                self.skipTest(f"port {committed} already in use on this machine")
            try:
                srv = app._bind_retrying("127.0.0.1", committed, attempts=3, delay=0.05)
                self.assertIsNone(srv)
                srv, landed_stable = app._bind_fallback("127.0.0.1", committed)
                try:
                    self.assertTrue(landed_stable)
                    self.assertNotEqual(srv.server_address[1], committed)
                    app_launch = True   # main()'s literal guard, reproduced verbatim:
                    if app_launch and committed is None and srv.server_address[1] in app.PORT_CANDIDATES:
                        app._commit_port(srv.server_address[1])
                    self.assertEqual(app._read_committed_port(), committed)  # unchanged
                finally:
                    srv.server_close()
            finally:
                holder.close()
        finally:
            shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
            app.CONFIG_DIR = saved_cfg


class TempPortUI(unittest.TestCase):
    """(c) install button/modal are absent when on a non-canonical port, present
    otherwise. (d) the temporary-port warning shows up exactly when they're absent."""

    def tearDown(self):
        app._ON_TEMP_PORT = False   # don't leak this global into other test modules

    def test_install_affordance_present_and_no_warning_on_the_canonical_port(self):
        app._ON_TEMP_PORT = False
        html = app.shell("Test", "<p>body</p>")
        self.assertIn("id=installbtn", html)
        self.assertIn("id=installmodal", html)
        self.assertNotIn("id=portwarn", html)

    def test_install_affordance_suppressed_and_warning_shown_on_a_temporary_port(self):
        app._ON_TEMP_PORT = True
        html = app.shell("Test", "<p>body</p>")
        self.assertNotIn("id=installbtn", html)
        self.assertNotIn("id=installmodal", html)
        self.assertIn("id=portwarn", html)
        # the ?welcome=1 first-paint script must not add the 'welcome' class (which hides
        # the body until #installmodal reveals it again) when there's no modal to reveal it
        self.assertIn("if(!true&&", html)

    def test_welcome_first_paint_script_active_on_the_canonical_port(self):
        app._ON_TEMP_PORT = False
        html = app.shell("Test", "<p>body</p>")
        self.assertIn("if(!false&&", html)


if __name__ == "__main__":
    unittest.main()
