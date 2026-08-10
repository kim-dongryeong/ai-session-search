"""Project timeline (/timeline): merges every session in a project into one chronological
message stream, plus the folder-only search form's new scope selector (Feature A).

Covers:
  - merged ordering across >=2 synthetic sessions, both sort directions
  - slice/paging correctness (off/lim boundaries, Prev/Next presence)
  - the source badge links to the right session (path) + turn index (goto=gi)
  - category chips render with counts
  - the folder-only search form on the project page carries a scope select
  - no IntersectionObserver anywhere in the timeline HTML
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402

PROJ_CWD = "/Users/x/timelineproj"


def _write_session(proj_dir, sid, msgs):
    """msgs: list of (timestamp-or-'', role, text). role is 'user' or 'assistant'."""
    path = os.path.join(proj_dir, sid + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for ts, role, text in msgs:
            o = {"type": role, "cwd": PROJ_CWD,
                 "message": {"role": role,
                             "content": text if role == "user" else [{"type": "text", "text": text}]}}
            if ts:
                o["timestamp"] = ts
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return path


def build_two_session_root():
    """Two sessions in the same project, interleaved in time, so a correct merge must
    weave them together rather than list one session fully before the other."""
    root = tempfile.mkdtemp()
    proj_dir = os.path.join(root, "-Users-x-timelineproj")
    os.makedirs(proj_dir)
    sid_a = "aaaaaaaa-1111-2222-3333-444444444444"
    sid_b = "bbbbbbbb-1111-2222-3333-444444444444"
    _write_session(proj_dir, sid_a, [
        ("2026-01-01T00:00:00Z", "user", "s1 msg1"),
        ("2026-01-01T00:01:00Z", "assistant", "s1 reply1"),
        ("2026-01-01T00:05:00Z", "user", "s1 msg2 latest"),
    ])
    _write_session(proj_dir, sid_b, [
        ("2026-01-01T00:02:00Z", "user", "s2 msg1"),
        ("2026-01-01T00:03:00Z", "assistant", "s2 reply1"),
    ])
    return root, proj_dir, sid_a, sid_b


def build_many_message_root(n=12):
    """One session with n user/assistant pairs, for paging boundary tests."""
    root = tempfile.mkdtemp()
    proj_dir = os.path.join(root, "-Users-x-timelineproj")
    os.makedirs(proj_dir)
    sid = "cccccccc-1111-2222-3333-444444444444"
    msgs = []
    for i in range(n):
        msgs.append((f"2026-01-01T00:{i:02d}:00Z", "user", f"msg {i}"))
        msgs.append((f"2026-01-01T00:{i:02d}:30Z", "assistant", f"reply {i}"))
    _write_session(proj_dir, sid, msgs)
    return root, proj_dir, sid


class TimelineBase(unittest.TestCase):
    root = None

    @classmethod
    def _start(cls, root):
        cls._cfg = app.CONFIG_DIR
        app.CONFIG_DIR = tempfile.mkdtemp()
        app.configure(root)
        app._SETTINGS = {}
        app.DEFAULT_ROOTS = [root]
        app.SAVED_ROOTS = []
        app.ROOTS[:] = [root]
        app.ROOT = root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(app.CONFIG_DIR, ignore_errors=True)
        app.CONFIG_DIR = cls._cfg
        if cls.root:
            shutil.rmtree(cls.root, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")


class MergedOrdering(TimelineBase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.proj_dir, cls.sid_a, cls.sid_b = build_two_session_root()
        cls._start(cls.root)

    def _first_msg_text(self, body):
        m = re.search(r'<div class=tlentry>.*?class="seg md">(.*?)</div>', body, re.S)
        return m.group(1) if m else None

    def test_merged_stream_interleaves_both_sessions(self):
        # a correct chronological merge must contain messages from BOTH sessions on one page,
        # not session A in full followed by session B in full
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertEqual(status, 200)
        self.assertIn("s1 msg1", body)
        self.assertIn("s2 msg1", body)
        self.assertIn("s1 reply1", body)
        self.assertIn("s2 reply1", body)

    def test_newest_first_default(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertEqual(status, 200)
        # the latest message overall is s1's 00:05:00 one
        self.assertIn("s1 msg2 latest", self._first_msg_text(body))

    def test_oldest_first(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&sort=old")
        self.assertEqual(status, 200)
        self.assertIn("s1 msg1", self._first_msg_text(body))

    def test_sort_directions_give_different_first_message(self):
        _, new_body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&sort=new")
        _, old_body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&sort=old")
        self.assertNotEqual(self._first_msg_text(new_body), self._first_msg_text(old_body))

    def test_source_badge_links_session_and_turn(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertEqual(status, 200)
        # session A's first turn (gi=0) must be reachable via goto=0 back into /session
        # matches this file's existing convention (see session()'s crumb links): hrefs built
        # from urlencode() are embedded as-is, not further html-escaped
        path_a = os.path.join(self.proj_dir, self.sid_a + ".jsonl")
        expected_href = "/session?" + urllib.parse.urlencode({"p": path_a, "goto": 0})
        self.assertIn(expected_href, body)

    def test_distinct_session_links_present(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        links = set(re.findall(r'/session\?p=([^&"]+)&(?:amp;)?goto=\d+', body))
        self.assertGreaterEqual(len(links), 2)

    def test_category_chips_render_with_counts(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertIn("class=chip-f", body)
        self.assertIn('data-cat="*"', body)
        self.assertIn('data-cat="you"', body)
        self.assertIn("class=cnt", body)

    def test_no_intersection_observer(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertNotIn("new IntersectionObserver", body)

    def test_sort_toggle_present(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertIn("sort=new", body)
        self.assertIn("sort=old", body)


class Paging(TimelineBase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.proj_dir, cls.sid = build_many_message_root(n=12)  # 24 messages total
        cls._start(cls.root)

    def test_lim_slices_correctly(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&lim=5")
        self.assertEqual(status, 200)
        self.assertEqual(body.count("class=tlentry"), 5)

    def test_next_present_when_more_remain(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&lim=5&off=0")
        self.assertIn(">Next", body)
        self.assertIn("off=5", body)

    def test_prev_absent_on_first_page(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&lim=5&off=0")
        self.assertNotIn("Prev</a>", body)

    def test_prev_present_on_later_page(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&lim=5&off=5")
        self.assertIn("Prev</a>", body)
        self.assertIn("off=0", body)

    def test_last_page_has_no_next(self):
        # 24 messages, lim=5 -> pages at off 0,5,10,15,20 (last has 4 items)
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&lim=5&off=20")
        self.assertEqual(status, 200)
        self.assertEqual(body.count("class=tlentry"), 4)
        self.assertNotIn(">Next", body)

    def test_total_count_shown(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote(PROJ_CWD) + "&lim=5")
        self.assertIn("24", body)


class IncrementalCache(unittest.TestCase):
    """Per-session cache (_session_timeline_entries) + merged k-way merge
    (_project_timeline_entries): an unchanged session's entries are never rebuilt, a changed
    session reparses only itself, and the merge order matches the old whole-project
    concatenate-then-stable-sort approach exactly."""

    def setUp(self):
        self.root, self.proj_dir, self.sid_a, self.sid_b = build_two_session_root()
        # isolate from whatever other test modules/classes left behind in these module-level caches
        app._TIMELINE_SESSION_CACHE["by_path"].clear()
        app._TIMELINE_MERGED_CACHE["by_key"].clear()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _item(self, sid):
        path = os.path.join(self.proj_dir, sid + ".jsonl")
        st = os.stat(path)
        return {"path": path, "sid": sid, "title": sid, "mtime": st.st_mtime}

    def test_unchanged_session_reuses_cache(self):
        it = self._item(self.sid_a)
        entries1, key1 = app._session_timeline_entries(it)
        entries2, key2 = app._session_timeline_entries(it)
        self.assertEqual(key1, key2)
        # same cached list object came back — it was not rebuilt the second time
        self.assertIs(entries1, entries2)

    def test_changed_session_reparses_only_itself(self):
        it_a, it_b = self._item(self.sid_a), self._item(self.sid_b)
        entries_a1, key_a1 = app._session_timeline_entries(it_a)
        entries_b1, key_b1 = app._session_timeline_entries(it_b)
        # append one more message to session A only (simulates Claude Code actively writing)
        with open(it_a["path"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "timestamp": "2026-01-01T00:06:00Z", "cwd": PROJ_CWD,
                                  "message": {"role": "user", "content": "s1 msg3 new"}}) + "\n")
        it_a2, it_b2 = self._item(self.sid_a), self._item(self.sid_b)  # refreshed mtime/size
        entries_a2, key_a2 = app._session_timeline_entries(it_a2)
        entries_b2, key_b2 = app._session_timeline_entries(it_b2)
        # session A: cache key changed and it was actually reparsed (one more entry)
        self.assertNotEqual(key_a1, key_a2)
        self.assertEqual(len(entries_a2), len(entries_a1) + 1)
        # session B: untouched — same key, same cached list object (never rebuilt)
        self.assertEqual(key_b1, key_b2)
        self.assertIs(entries_b1, entries_b2)

    def test_merge_order_matches_naive_full_sort(self):
        items = [self._item(self.sid_a), self._item(self.sid_b)]
        ordered = app._project_timeline_entries(("test", "merge-order"), items)
        # reference: the old whole-project approach — concatenate each session's own (already
        # carry-forward-filled) entries in `items` order, then one stable sort by ts
        naive = []
        for it in items:
            entries, _ = app._session_timeline_entries(it)
            naive.extend(entries)
        naive.sort(key=lambda en: en["ts"])
        self.assertEqual([(en["path"], en["gi"]) for en in ordered],
                         [(en["path"], en["gi"]) for en in naive])
        self.assertGreaterEqual(len(ordered), 5)   # sanity: both sessions actually contributed

    def test_merged_list_reused_when_nothing_changed(self):
        items = [self._item(self.sid_a), self._item(self.sid_b)]
        key = ("test", "merge-cache")
        ordered1 = app._project_timeline_entries(key, items)
        ordered2 = app._project_timeline_entries(key, items)
        self.assertIs(ordered1, ordered2)   # cache hit — not re-merged

    def test_merged_list_rebuilt_when_one_session_changes(self):
        items = [self._item(self.sid_a), self._item(self.sid_b)]
        key = ("test", "merge-cache-2")
        ordered1 = app._project_timeline_entries(key, items)
        with open(items[0]["path"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "timestamp": "2026-01-01T00:06:00Z", "cwd": PROJ_CWD,
                                  "message": {"role": "user", "content": "s1 msg3 new"}}) + "\n")
        items2 = [self._item(self.sid_a), self._item(self.sid_b)]
        ordered2 = app._project_timeline_entries(key, items2)
        self.assertIsNot(ordered1, ordered2)
        self.assertEqual(len(ordered2), len(ordered1) + 1)


class MissingProject(TimelineBase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.proj_dir, cls.sid = build_many_message_root(n=1)
        cls._start(cls.root)

    def test_missing_proj_param_does_not_500(self):
        status, body = self.get("/timeline")
        self.assertEqual(status, 200)

    def test_unknown_proj_returns_empty_but_ok(self):
        status, body = self.get("/timeline?proj=" + urllib.parse.quote("/nowhere/at/all"))
        self.assertEqual(status, 200)
        self.assertNotIn("class=tlentry", body)


class ProjectPageEntryPoints(TimelineBase):
    """Feature A (scope select on the folder-only search form) + the new timeline link,
    both on the project (folder-filtered) index page."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.proj_dir, cls.sid = build_many_message_root(n=1)
        cls._start(cls.root)

    def test_project_page_has_timeline_link(self):
        status, body = self.get("/?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertEqual(status, 200)
        self.assertIn("/timeline?", body)

    def test_folder_search_form_has_scope_select(self):
        status, body = self.get("/?proj=" + urllib.parse.quote(PROJ_CWD))
        self.assertEqual(status, 200)
        # the folder-only search form (action=/search, hidden proj=) must now carry a
        # scope <select> with the same option set as the header search form
        m = re.search(r'<form class=ssearch method=get action=/search[^>]*>.*?</form>', body, re.S)
        self.assertIsNotNone(m)
        form_html = m.group(0)
        self.assertIn("name=scope", form_html)
        for scope_key in app.SCOPES:
            self.assertIn(f'value="{scope_key}"', form_html)


if __name__ == "__main__":
    unittest.main()
