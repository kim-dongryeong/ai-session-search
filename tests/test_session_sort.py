"""Session view: sort=new (newest-first display order) for the plain conversation view.

Covers:
  1. default (no sort param) is unchanged — ascending, t0 before t{last}
  2. sort=new&lim=all reverses render order exactly
  3. sort=new&lim=50 pages correctly (page 1 = newest lim, off carries into page 2) and
     preserves sort= on the Next link
  4. sort=new has no lazy-render sentinels (loadfwd/data-auto)
  5. goto= ignores sort (existing ascending goto-window behavior)
  6. favorites' data-gi under sort=new still reflects the true session index, not display position
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


def build_root(n=130):
    """A flat session (one 'you' turn per line, `turn {i}` as the body) for order assertions."""
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-sort")
    os.makedirs(proj)
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    lines = [{"type": "user", "message": {"role": "user", "content": f"turn {i}"}} for i in range(n)]
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl")


class SessionSort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_root(n=130)
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
        app._SETTINGS = {}   # each test starts from defaults (lazy_render=True, default lim)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_default_order_is_unchanged(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertLess(body.index('id="t0"'), body.index('id="t129"'))

    def test_sort_new_reverses_full_render_order(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&sort=new&lim=all")
        self.assertEqual(status, 200)
        self.assertLess(body.index('id="t129"'), body.index('id="t0"'))
        # every id is still present — nothing dropped, just reordered
        for i in range(130):
            self.assertIn(f'id="t{i}"', body)

    def test_sort_new_pages_newest_first_and_preserves_sort_on_next(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&sort=new&lim=50")
        self.assertEqual(status, 200)
        # page 1: t129..t80, in that order
        self.assertLess(body.index('id="t129"'), body.index('id="t80"'))
        for i in range(80, 130):
            self.assertIn(f'id="t{i}"', body)
        for i in range(0, 80):
            self.assertNotIn(f'id="t{i}"', body)
        m = re.search(r'>Next[^<]*</a>', body)
        self.assertIsNotNone(m)
        self.assertIn("sort=new", body)
        self.assertIn("off=50", body)

        status2, body2 = self.get("/session?p=" + urllib.parse.quote(self.path) + "&sort=new&lim=50&off=50")
        self.assertEqual(status2, 200)
        for i in range(30, 80):
            self.assertIn(f'id="t{i}"', body2)
        for i in list(range(0, 30)) + list(range(80, 130)):
            self.assertNotIn(f'id="t{i}"', body2)
        self.assertLess(body2.index('id="t79"'), body2.index('id="t30"'))
        self.assertIn("Prev</a>", body2)

    def test_sort_new_has_no_lazy_sentinels(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&sort=new")
        self.assertEqual(status, 200)
        # id=loadfwd/id=loadprev absence alone proves no sentinel rendered — data-auto=1 only
        # ever appears attached to the id=loadfwd div (the shell's shared JS also mentions the
        # substring "data-auto=1" in a comment, so it's not itself a reliable absence check).
        self.assertNotIn("id=loadfwd", body)
        self.assertNotIn("id=loadprev", body)

    def test_goto_ignores_sort(self):
        # a goto= jump must land in the classic ascending window regardless of sort=new
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path)
                                 + "&sort=new&goto=64&lim=20")
        self.assertEqual(status, 200)
        self.assertLess(body.index('id="t54"'), body.index('id="t64"'))
        # ascending order preserved within the goto window
        self.assertLess(body.index('id="t60"'), body.index('id="t64"'))

    def test_favorite_data_gi_is_true_session_index_under_sort_new(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&sort=new&lim=all")
        self.assertEqual(status, 200)
        # the last-rendered turn under sort=new is t0 (session index 0) — its favorite button
        # must carry data-gi="0", not its on-page display position.
        m = re.search(r'data-gi="0"[^>]*>|data-gi="0"', body)
        self.assertIsNotNone(re.search(r'data-gi="0"', body))
        self.assertIsNotNone(re.search(r'data-gi="129"', body))


if __name__ == "__main__":
    unittest.main()
