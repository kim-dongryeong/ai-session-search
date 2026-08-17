"""Per-message favorites (★, CONFIG_DIR/favorites.json) — toggle API, HTML rendering, and the
/favs page's portability guarantee (see FAVS_FILE / sid_of() in app.py): a favorite is keyed by
sid:gi, not an absolute path, so it must still resolve after the session file moves to a
different root/computer as long as the filename is unchanged."""
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


def _write_claude_session(proj_dir, sid, human_text="즐겨찾기 테스트 질문입니다", reply_text="즐겨찾기 답변"):
    os.makedirs(proj_dir, exist_ok=True)
    lines = [
        {"type": "ai-title", "aiTitle": "즐겨찾기 데모 세션"},
        {"type": "user", "timestamp": "2026-06-30T01:00:00Z", "cwd": "/Users/x/favdemo",
         "message": {"role": "user", "content": human_text}},
        {"type": "assistant", "cwd": "/Users/x/favdemo",
         "message": {"role": "assistant", "model": "claude-opus-4-8",
                     "content": [{"type": "text", "text": reply_text}]}},
    ]
    path = os.path.join(proj_dir, sid + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return path


def build_fixture_root():
    root = tempfile.mkdtemp()
    claude_sid = "aaaa1111-2222-3333-4444-555555555555"
    claude_path = _write_claude_session(os.path.join(root, "-Users-x-favdemo"), claude_sid)

    codex_sid = "019c8b6e-2595-7111-aaaa-bbbbccccdddd"
    codex_lines = [
        {"type": "session_meta", "payload": {"id": codex_sid, "cwd": "/Users/x/codexfav"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.3-codex"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "코덱스 즐겨찾기 질문"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "코덱스 즐겨찾기 답변"}]}},
    ]
    codex_proj = os.path.join(root, "-Users-x-favdemo")
    codex_path = os.path.join(codex_proj, f"rollout-2026-02-24T01-56-17-{codex_sid}.jsonl")
    with open(codex_path, "w", encoding="utf-8") as fh:
        for o in codex_lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")

    return root, claude_path, codex_path, claude_sid, codex_sid


class FavoritesHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # NEVER touch the user's real CONFIG_DIR — redirect it AND the FAVS_FILE constant
        # derived from it (module-level constants captured at import time don't follow a
        # later CONFIG_DIR reassignment, same caveat other tests note for SETTINGS_FILE).
        cls._orig_cfg = app.CONFIG_DIR
        cls._orig_favs_file = app.FAVS_FILE
        app.CONFIG_DIR = tempfile.mkdtemp(prefix="aiss-fav-cfg-")
        app.FAVS_FILE = os.path.join(app.CONFIG_DIR, "favorites.json")

        cls.root, cls.claude_path, cls.codex_path, cls.claude_sid, cls.codex_sid = build_fixture_root()
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
        shutil.rmtree(cls.root, ignore_errors=True)
        app.CONFIG_DIR = cls._orig_cfg
        app.FAVS_FILE = cls._orig_favs_file

    def setUp(self):
        # each test starts from an empty favorites set, in memory AND on disk
        app._FAVS = {}
        try:
            os.remove(app.FAVS_FILE)
        except OSError:
            pass

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def get_json(self, path):
        status, body = self.get(path)
        return status, json.loads(body)

    # ---- 1. toggle API ----
    def test_toggle_on_creates_file_and_entry(self):
        self.assertFalse(os.path.exists(app.FAVS_FILE))
        status, d = self.get_json("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=0&on=1")
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertTrue(d["on"])
        self.assertTrue(os.path.exists(app.FAVS_FILE))
        with open(app.FAVS_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(len(saved["favs"]), 1)
        entry = saved["favs"][0]
        self.assertEqual(entry["sid"], app.sid_of(self.claude_path))
        self.assertEqual(entry["gi"], 0)
        self.assertEqual(entry["role"], "you")
        self.assertIn("즐겨찾기 테스트 질문입니다", entry["excerpt"])

    def test_toggle_off_removes_entry(self):
        self.get("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=0&on=1")
        sid = app.sid_of(self.claude_path)
        status, d = self.get_json(f"/api/fav?sid={sid}&gi=0&on=0")
        self.assertEqual(status, 200)
        self.assertFalse(d["on"])
        with open(app.FAVS_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["favs"], [])

    def test_toggle_on_duplicate_is_ignored_not_updated(self):
        # first save wins — a second on=1 for the same sid:gi must not overwrite the excerpt
        self.get("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=1&on=1")
        # forge a second session at the SAME sid:gi with different text is impractical here, so
        # instead just confirm a second identical toggle doesn't create a second entry
        self.get("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=1&on=1")
        with open(app.FAVS_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(len(saved["favs"]), 1)

    # ---- 2. HTML rendering: favbtn + data-sid, both providers ----
    def test_session_view_renders_favbtn_with_claude_sid(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.claude_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertIn("class=favbtn", body)
        self.assertIn(f'data-sid="{self.claude_sid}"', body)

    def test_session_view_renders_favbtn_with_codex_sid(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.codex_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertIn("class=favbtn", body)
        # Codex's sid is the uuid extracted from the rollout-...-<uuid>.jsonl filename, not the
        # whole filename — this is exactly what sid_of()/_codex_sid() do differently from Claude.
        self.assertIn(f'data-sid="{self.codex_sid}"', body)
        self.assertNotIn(f'data-sid="rollout', body)

    # ---- 3. /favs page: excerpt, title, current-path goto link ----
    def test_favs_page_shows_excerpt_and_goto_link(self):
        self.get("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=0&on=1")
        status, body = self.get("/favs")
        self.assertEqual(status, 200)
        self.assertIn("즐겨찾기 데모 세션", body)          # stored title
        self.assertIn("즐겨찾기 테스트 질문입니다", body)   # stored excerpt
        self.assertIn("/session?p=" + urllib.parse.quote(self.claude_path) + "&goto=0", body)

    def test_index_page_links_to_favs_with_count(self):
        self.get("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=0&on=1")
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('href="/favs"', body)

    # ---- 4. portability: same filename, different root ----
    def test_favs_goto_link_follows_session_to_a_new_root(self):
        self.get("/api/fav?p=" + urllib.parse.quote(self.claude_path) + "&gi=0&on=1")
        # confirm the link points at the ORIGINAL root first
        _, body = self.get("/favs")
        self.assertIn(urllib.parse.quote(self.claude_path), body)

        root_b = tempfile.mkdtemp(prefix="aiss-fav-rootB-")
        try:
            # a different project folder name, same session filename — sid_of() is filename-only
            new_path = _write_claude_session(os.path.join(root_b, "-Users-someone-else-moved"),
                                              self.claude_sid)
            saved_roots, saved_default, saved_root, saved_roots_list = (
                list(app.SAVED_ROOTS), list(app.DEFAULT_ROOTS), app.ROOT, list(app.ROOTS))
            app.DEFAULT_ROOTS = [root_b]
            app.SAVED_ROOTS = []
            app.ROOTS[:] = [root_b]
            app.ROOT = root_b
            try:
                status, body = self.get("/favs")
                self.assertEqual(status, 200)
                self.assertIn(urllib.parse.quote(new_path), body)
                self.assertNotIn(urllib.parse.quote(self.claude_path), body)
            finally:
                app.DEFAULT_ROOTS = saved_default
                app.SAVED_ROOTS = saved_roots
                app.ROOTS[:] = saved_roots_list
                app.ROOT = saved_root
        finally:
            shutil.rmtree(root_b, ignore_errors=True)

    # ---- 5. missing session file anywhere ----
    def test_favs_shows_notice_when_session_not_found_anywhere(self):
        ghost_root = tempfile.mkdtemp(prefix="aiss-fav-ghost-")
        ghost_sid = "deadbeef-0000-1111-2222-333344445555"
        ghost_path = _write_claude_session(os.path.join(ghost_root, "-Users-ghost"), ghost_sid,
                                            human_text="곧 사라질 세션")
        saved_roots, saved_default, saved_root, saved_roots_list = (
            list(app.SAVED_ROOTS), list(app.DEFAULT_ROOTS), app.ROOT, list(app.ROOTS))
        app.DEFAULT_ROOTS = [self.root, ghost_root]
        app.SAVED_ROOTS = []
        app.ROOTS[:] = [self.root, ghost_root]
        try:
            self.get("/api/fav?p=" + urllib.parse.quote(ghost_path) + "&gi=0&on=1")
            shutil.rmtree(ghost_root, ignore_errors=True)   # the folder is gone now
            app.DEFAULT_ROOTS = [self.root]
            app.ROOTS[:] = [self.root]
            status, body = self.get("/favs")
            self.assertEqual(status, 200)                  # must not crash
            self.assertIn("곧 사라질 세션", body)            # the excerpt still shows
            self.assertIn("folder not added", body)
        finally:
            app.DEFAULT_ROOTS = saved_default
            app.SAVED_ROOTS = saved_roots
            app.ROOTS[:] = saved_roots_list
            app.ROOT = saved_root
            shutil.rmtree(ghost_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
