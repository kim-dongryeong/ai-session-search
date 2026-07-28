"""Session-view lazy-render behavior + persisted settings (default per-page, lazy-render).

Covers CHANGE A-D: explicit per-page disables lazy, default view honors saved
default_lim/lazy_render, and the /api/settings endpoint persists+reloads."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


def build_big_fixture_root(n_pairs=150):
    """A session with n_pairs user/assistant turns — big enough to cross INIT_CHUNK (120)."""
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-big")
    os.makedirs(proj)
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    lines = [{"type": "ai-title", "aiTitle": "big session"}]
    for i in range(n_pairs):
        lines.append({"type": "user", "timestamp": "2026-06-30T01:00:00Z", "cwd": "/Users/x/demo",
                      "message": {"role": "user", "content": f"question {i}"}})
        lines.append({"type": "assistant", "cwd": "/Users/x/demo",
                      "message": {"role": "assistant", "model": "claude-opus-4-8",
                                  "content": [{"type": "text", "text": f"answer {i}"}]}})
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl")


class LazyRenderGate(unittest.TestCase):
    """HTTP-level checks for the lazy gate: explicit lim, default settings."""

    @classmethod
    def setUpClass(cls):
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        cls.root, cls.session_path = build_big_fixture_root()
        app.configure(cls.root)
        app.DEFAULT_ROOTS = [cls.root]
        app.SAVED_ROOTS = []
        app.ROOTS[:] = [cls.root]
        app.ROOT = cls.root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = cls._cfg

    def setUp(self):
        # reset in-memory settings to defaults before each test
        app._SETTINGS = {}

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_explicit_lim_all_disables_lazy(self):
        # CHANGE A: an explicit per-page choice in the URL (lim=all) must render everything —
        # no #loadfwd sentinel — even though the session is well over INIT_CHUNK.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertNotIn("id=loadfwd", body)

    def test_explicit_lim_number_disables_lazy(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=5000")
        self.assertEqual(status, 200)
        self.assertNotIn("id=loadfwd", body)

    def test_default_view_is_lazy_when_big(self):
        # no lim param at all (lim_raw=="") + default lazy_render=True + big session → lazy on.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path))
        self.assertEqual(status, 200)
        self.assertIn("id=loadfwd", body)

    def test_lazy_render_false_disables_lazy_even_on_default(self):
        # CHANGE D: default view (lim_raw=="") but lazy_render explicitly off → no sentinel.
        app.set_settings(lazy_render=False)
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path))
        self.assertEqual(status, 200)
        self.assertNotIn("id=loadfwd", body)

    def test_default_lim_all_with_lazy_render_true_still_lazy(self):
        # settings default_lim="all" + lazy_render=true still lazy-loads (fast open).
        app.set_settings(default_lim="all", lazy_render=True)
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path))
        self.assertEqual(status, 200)
        self.assertIn("id=loadfwd", body)

    def test_default_lim_honored_when_lim_raw_empty(self):
        # CHANGE C: a saved default_lim applies when the URL carries no explicit lim, using the
        # classic (non-continuous) human-filtered page to make the resulting window size visible.
        app.set_settings(default_lim=50)
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&filter=human")
        self.assertEqual(status, 200)
        self.assertIn("50/150", body)

    def test_explicit_lim_still_overrides_saved_default(self):
        app.set_settings(default_lim=50)
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path)
                                 + "&filter=human&lim=2000")
        self.assertEqual(status, 200)
        self.assertIn("150/150", body)


class SettingsEndpoint(unittest.TestCase):
    """/api/settings persists to CONFIG_DIR/settings.json and reloads via configure()."""

    def setUp(self):
        self._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        self.root, _ = build_big_fixture_root(n_pairs=1)
        app.configure(self.root)
        self.srv = app.make_server(port=0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = self._cfg

    def get(self, path):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_settings_persist_and_reload(self):
        status, d = self.get("/api/settings?default_lim=5000&lazy_render=0")
        self.assertEqual(status, 200)
        self.assertEqual(d["settings"]["default_lim"], 5000)
        self.assertEqual(d["settings"]["lazy_render"], False)
        # persisted to disk
        with open(app.SETTINGS_FILE, encoding="utf-8") as fh:
            on_disk = json.load(fh)
        self.assertEqual(on_disk["default_lim"], 5000)
        self.assertEqual(on_disk["lazy_render"], False)
        # a fresh configure() (as at process startup) reloads them
        app._SETTINGS = {}
        app.configure(self.root)
        self.assertEqual(app._SETTINGS.get("default_lim"), 5000)
        self.assertEqual(app._SETTINGS.get("lazy_render"), False)

    def test_settings_default_lim_all(self):
        status, d = self.get("/api/settings?default_lim=all")
        self.assertEqual(status, 200)
        self.assertEqual(d["settings"]["default_lim"], "all")
        self.assertIsNone(app.get_default_lim())

    def test_cross_site_settings_write_rejected(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/settings?default_lim=200")
        req.add_header("Sec-Fetch-Site", "cross-site")
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("expected HTTP 403")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)
            d = json.loads(e.read().decode("utf-8"))
        self.assertIn("error", d)


if __name__ == "__main__":
    unittest.main()
