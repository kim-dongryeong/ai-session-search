"""Session view: explicit load-more buttons + Prev/Next paging instead of infinite scroll
(CHANGE 1), and in-session-search context expansion (CHANGE 2).

Covers:
  (a) the default session view has a clickable forward-load button, not auto-observer wiring
  (b) the default (filt=all) view gets classic Prev/Next paging when it exceeds one page
  (c) an sq= view renders before/after context buttons for a match
  (d) /api/session_tail returns a correct earlier-direction (backward) fragment
"""
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


def build_long_root(n=1300, marker_at=None, marker="UNIQUEMARKER"):
    """A long, flat session (one 'you' turn per line) — optionally with a uniquely searchable
    turn spliced in at `marker_at` so in-session search (sq=) has exactly one hit with context
    on both sides."""
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-long2")
    os.makedirs(proj)
    sid = "dddddddd-eeee-ffff-0000-111122223333"
    lines = []
    for i in range(n):
        content = f"look for {marker} here" if i == marker_at else f"turn {i}"
        lines.append({"type": "user", "message": {"role": "user", "content": content}})
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl")


class SessionPagingButtons(unittest.TestCase):
    """CHANGE 1: explicit buttons instead of scroll-triggered auto-load, plus Prev/Next paging."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_long_root(n=1300)
        # isolate CONFIG_DIR/settings.json so a persisted default_lim on this machine (or from
        # another test module) can't change how many turns land on one page here
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        app.configure(cls.root)
        app._SETTINGS = {}   # SETTINGS_FILE is a module-level constant captured at import,
        # so reassigning CONFIG_DIR alone doesn't redirect it — force a clean in-memory default
        app.DEFAULT_ROOTS = [cls.root]; app.SAVED_ROOTS = []
        app.ROOTS[:] = [cls.root]; app.ROOT = cls.root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = cls._cfg

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_forward_sentinel_is_a_button_not_an_observer(self):
        # (a) default view (no lim → DEFAULT_LIM=1000 window over a 1300-turn session): the
        # forward sentinel must render as a clickable button, and the auto-observer that used
        # to drive it on scroll must be gone.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
        self.assertEqual(status, 200)
        self.assertIn("id=loadfwd", body)
        self.assertIn("Load 100 more messages", body)
        self.assertIn('id=loadfwd class=loadmore', body)
        self.assertNotIn("fo=new IntersectionObserver", body)
        self.assertNotIn("po=new IntersectionObserver", body)
        # the loop-driven loaders (g/Shift+G/Home/Cmd+Up) must still be wired in
        self.assertIn("loadAllThenTop", body)
        self.assertIn("loadAllThenBottom", body)

    def test_default_view_has_prev_next_paging(self):
        # (b) 1300 turns > DEFAULT_LIM(1000) → the first page must offer a Next link, using the
        # same off/lim URL scheme as the filtered view's classic paging.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
        self.assertEqual(status, 200)
        self.assertIn("class=pg", body)
        self.assertIn(">Next", body)   # Next label appears before its count/arrow: ">Next NNN →"
        self.assertIn("off=1000", body)
        # top AND bottom placement — the pg bar is rendered twice around the message list
        self.assertGreaterEqual(body.count("class=pg"), 2)

    def test_second_page_has_prev_link(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&off=1000")
        self.assertEqual(status, 200)
        self.assertIn("Prev</a>", body)
        self.assertIn("off=0", body)


class SessionSearchContext(unittest.TestCase):
    """CHANGE 2: in-session search (sq=) result context expansion."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_long_root(n=300, marker_at=150)
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        app.configure(cls.root)
        app._SETTINGS = {}   # SETTINGS_FILE is a module-level constant captured at import,
        # so reassigning CONFIG_DIR alone doesn't redirect it — force a clean in-memory default
        app.DEFAULT_ROOTS = [cls.root]; app.SAVED_ROOTS = []
        app.ROOTS[:] = [cls.root]; app.ROOT = cls.root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = cls._cfg

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_sq_view_has_before_after_context_buttons(self):
        # (c) the sole match (at gi=150, with plenty of turns on both sides) must get both a
        # "before" and an "after" context-expansion control, without losing the jump link.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path)
                                 + "&sq=UNIQUEMARKER")
        self.assertEqual(status, 200)
        self.assertIn("1 messages matched in this session", body)
        self.assertIn("▲ Load 100 before", body)
        self.assertIn("▼ Load 100 after", body)
        self.assertIn('data-before="150"', body)
        self.assertIn('data-after="150"', body)
        self.assertIn("class=ctxbtn", body)
        # the matched turn itself is still rendered with its permalink id
        self.assertIn('id="t150"', body)

    def test_sq_view_omits_context_button_at_session_edge(self):
        # a match at turn 0 has nothing earlier to load — no "before" control should render.
        root, path = build_long_root(n=50, marker_at=0)
        app.configure(root)
        app.ROOTS[:] = [root]; app.ROOT = root
        status, body = self.get("/session?p=" + urllib.parse.quote(path) + "&sq=UNIQUEMARKER")
        self.assertEqual(status, 200)
        self.assertNotIn("▲ Load 100 before", body)
        self.assertIn("▼ Load 100 after", body)


class SessionTailBackward(unittest.TestCase):
    """(d) /api/session_tail already supports an earlier-direction fragment: the caller just
    picks `since` below the current window (used by the sq= context 'before' expander with
    ctx=1, which additionally flags the rendered turns as de-emphasized context)."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_long_root(n=300)
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        app.configure(cls.root)
        app._SETTINGS = {}   # SETTINGS_FILE is a module-level constant captured at import,
        # so reassigning CONFIG_DIR alone doesn't redirect it — force a clean in-memory default
        app.DEFAULT_ROOTS = [cls.root]; app.SAVED_ROOTS = []
        app.ROOTS[:] = [cls.root]; app.ROOT = cls.root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = cls._cfg

    def get_json(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_backward_fragment_returns_the_earlier_range(self):
        # ask for the 10 turns immediately before gi=150 (i.e. [140,150))
        status, d = self.get_json("/api/session_tail?p=" + urllib.parse.quote(self.path)
                                   + "&since=140&limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(d["end"], 150)
        self.assertIn("turn 140", d["html"])
        self.assertIn("turn 149", d["html"])
        self.assertNotIn("turn 150", d["html"])
        self.assertNotIn("turn 139", d["html"])

    def test_ctx_flag_marks_turns_as_context(self):
        status, d = self.get_json("/api/session_tail?p=" + urllib.parse.quote(self.path)
                                   + "&since=140&limit=10&ctx=1")
        self.assertEqual(status, 200)
        self.assertIn("ctxmsg", d["html"])

    def test_no_ctx_flag_omits_context_class(self):
        status, d = self.get_json("/api/session_tail?p=" + urllib.parse.quote(self.path)
                                   + "&since=140&limit=10")
        self.assertEqual(status, 200)
        self.assertNotIn("ctxmsg", d["html"])


if __name__ == "__main__":
    unittest.main()
