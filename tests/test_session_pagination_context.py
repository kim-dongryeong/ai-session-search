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
import re
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

    def test_forward_sentinel_is_bounded_and_autofills(self):
        # (a) default view (no lim → DEFAULT_LIM=1000 window over a 1300-turn session, lazy
        # render on by default): the forward sentinel must be bounded to the PAGE end (1000),
        # never the session end (1300) — that's the "per page 5000 leaks the next page" bug —
        # and it must render as an auto-filling spinner row, not a click-required button, and
        # the auto-observer that used to drive it on scroll must be gone.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
        self.assertEqual(status, 200)
        self.assertIn("id=loadfwd", body)
        self.assertIn('data-end="1000"', body)     # bounded to the page end, not len(turns)=1300
        self.assertIn("data-auto=1", body)
        self.assertNotIn("Load 100 more messages", body)   # no click-required button when lazy
        self.assertIn("class=searching", body)              # existing spinner-row affordance
        self.assertIn('id=loadfwd class=loadmore', body)
        self.assertNotIn("fo=new IntersectionObserver", body)
        self.assertNotIn("po=new IntersectionObserver", body)
        # the loop-driven loaders (g/Shift+G/Home/Cmd+Up) must still be wired in
        self.assertIn("loadAllThenTop", body)
        self.assertIn("loadAllThenBottom", body)

    def test_forward_sentinel_button_when_lazy_off(self):
        # with lazy render off, a page beyond INIT_CHUNK still needs manual paging via Prev/
        # Next rather than a progressive fill — but since the whole page renders up front
        # (server-side), there's nothing left within the page to load: no sentinel at all.
        self.assertEqual(self.get("/api/settings?lazy_render=0")[0], 200)
        try:
            status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
            self.assertEqual(status, 200)
            self.assertNotIn("id=loadfwd", body)
            self.assertNotIn("id=loadprev", body)
        finally:
            self.get("/api/settings?lazy_render=1")

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


class PageBoundedLoaders(unittest.TestCase):
    """A page means exactly `lim` messages: the forward/backward sentinels may never spill
    into a neighboring page, lazy fill converges to exactly the page size, lazy-off already
    renders the full page up front with no sentinel, and g/Shift+G resolve to the page
    holding the session's true first/last message."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_long_root(n=1300)
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        app.configure(cls.root)
        app._SETTINGS = {}
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

    def setUp(self):
        app._SETTINGS = {}   # each test starts from the default (lazy_render=True)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def get_json(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_forward_sentinel_end_never_exceeds_page_end(self):
        # off=200, lim=500 over a 1300-turn session -> page is [200,700); the forward sentinel's
        # data-end must be the PAGE end (700), never len(turns) (1300).
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&off=200&lim=500")
        self.assertEqual(status, 200)
        m = re.search(r'id=loadfwd[^>]*data-end="(\d+)"', body)
        # lim=500 is explicit -> lazy is off -> the whole page renders up front -> no sentinel at
        # all (nothing left within the page to stream). Confirms the bound the other way: there
        # is definitely nothing to load past 700.
        self.assertIsNone(m)
        self.assertNotIn("id=loadfwd", body)

    def test_forward_sentinel_end_bounded_when_lazy(self):
        # default view (no explicit lim) over 1300 turns -> DEFAULT_LIM=1000, lazy on -> the
        # sentinel's data-end must be the page end (1000), never the session end (1300).
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
        self.assertEqual(status, 200)
        m = re.search(r'id=loadfwd[^>]*data-end="(\d+)"', body)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 1000)
        self.assertLess(int(m.group(1)), 1300)

    def test_backward_sentinel_never_before_page_start(self):
        # off=200, lim=500 -> the page start IS 200; there is nothing earlier to load *within
        # the page*, so #loadprev (which used to walk back past the page boundary) must be gone.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&off=200&lim=500")
        self.assertEqual(status, 200)
        self.assertNotIn("id=loadprev", body)

    def test_fully_rendered_page_has_neither_sentinel(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&off=200&lim=500")
        self.assertEqual(status, 200)
        self.assertNotIn("id=loadfwd", body)
        self.assertNotIn("id=loadprev", body)
        # and it really did render the whole 500-message page, not just a first chunk
        self.assertEqual(len(re.findall(r'id="t\d+"', body)), 500)

    def test_lazy_fill_converges_to_exactly_lim(self):
        # default view: DEFAULT_LIM=1000, lazy on -> INIT_CHUNK(120) painted immediately, then
        # the client streams further /api/session_tail chunks. Drive that same loop server-side
        # and confirm it terminates at exactly the page end (1000), never past it.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
        self.assertEqual(status, 200)
        since = int(re.search(r'id=loadfwd[^>]*data-since="(\d+)"', body).group(1))
        end = int(re.search(r'id=loadfwd[^>]*data-end="(\d+)"', body).group(1))
        self.assertEqual(since, 120)   # INIT_CHUNK
        rendered = len(re.findall(r'id="t\d+"', body))   # the initial chunk already on the page
        while since < end:
            take = min(100, end - since)
            _, d = self.get_json("/api/session_tail?p=" + urllib.parse.quote(self.path)
                                  + f"&since={since}&limit={take}")
            self.assertLessEqual(d["end"], end)   # the loop's own range never exceeds the page
            rendered += len(re.findall(r'id="t\d+"', d["html"]))
            since = d["end"]
        self.assertEqual(since, end)
        self.assertEqual(rendered, 1000)   # converges to exactly `lim`, no more, no less

    def test_lazy_off_first_response_already_has_lim_messages_no_sentinel(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&lim=500")
        self.assertEqual(status, 200)
        self.assertNotIn("id=loadfwd", body)
        self.assertNotIn("id=loadprev", body)
        self.assertEqual(len(re.findall(r'id="t\d+"', body)), 500)

    def test_g_and_shiftg_targets_resolve_to_first_and_last_page(self):
        # on the (default) first page: no earlier page to jump to, but Shift+G must point at
        # the last page (off=1000, the page holding turn 1299, the session's true last message).
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path))
        self.assertEqual(status, 200)
        self.assertIn('data-firstpage=""', body)
        m = re.search(r'data-lastpage="([^"]*)"', body)
        self.assertIsNotNone(m)
        self.assertIn("off=1000", urllib.parse.unquote(m.group(1)))
        # on the last page: g must point back at the first page (off=0); no further last page.
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&off=1000")
        self.assertEqual(status, 200)
        self.assertIn('data-lastpage=""', body)
        m = re.search(r'data-firstpage="([^"]*)"', body)
        self.assertIsNotNone(m)
        self.assertIn("off=0", urllib.parse.unquote(m.group(1)))


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

    def test_sq_view_has_category_filter_chips(self):
        # the in-session search results get the same 0/1..9 category chip bar as the full
        # conversation, with counts taken over the matched messages only (here: 1 'you' turn).
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path)
                                 + "&sq=UNIQUEMARKER")
        self.assertEqual(status, 200)
        self.assertIn('class=chip-f data-cat="*"', body)
        self.assertIn('class=chip-f data-cat="you"', body)
        self.assertIn("My messages<span class=cnt>1</span>", body)

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
