"""Per-snippet timestamps in search results: _rows_from_turns() carries each turn's ts
onto every row it produces (shared object, no dupes), H.search renders it next to the
role chip as %m/%d %H:%M with a full-year tooltip, and stale search-v*.sqlite3 cache
files (left behind by a _CACHE_SCHEMA/_FTS_SCHEMA bump) get swept exactly once per
process when the current-schema DB is opened."""
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


def build_fixture_root():
    """One session with a timestamped human turn ('안녕하세요' at a known instant) and a
    timestamp-less assistant turn ('타임스탬프없음') — Codex/Gemini turns can lack a ts,
    and the snippet must render cleanly (no empty span, no broken markup) in that case."""
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-tsdemo")
    os.makedirs(proj)
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    lines = [
        {"type": "user", "timestamp": "2026-03-14T09:41:00Z", "cwd": "/Users/x/tsdemo",
         "message": {"role": "user", "content": "안녕하세요 타임스탬프테스트"}},
        # no "timestamp" key at all on this one → turn ts == ""
        {"type": "assistant", "cwd": "/Users/x/tsdemo",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "타임스탬프없음 응답"}]}},
    ]
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl")


class SearchSnippetTimestampsHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.session_path = build_fixture_root()
        cls.tmpcfg = tempfile.mkdtemp()          # never touch the real ~/.config/ai-session-search
        cls._orig_cfg = app.CONFIG_DIR
        app.CONFIG_DIR = cls.tmpcfg
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
        try:
            if app._FTS["con"]:
                app._FTS["con"].close()
        except Exception:
            pass
        app._FTS["con"] = None
        app._FTS["cleaned"] = False
        app.CONFIG_DIR = cls._orig_cfg
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.tmpcfg, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_snippet_shows_short_timestamp(self):
        # 2026-03-14T09:41:00Z rendered in local time as %m/%d %H:%M — check the date part,
        # which is timezone-stable (03/14 in every zone UTC-... the hour could shift a day
        # only near midnight UTC, which 09:41Z is nowhere near).
        status, body = self.get("/search?q=" + urllib.parse.quote("타임스탬프테스트"))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)
        expect_short = app.fmt_ts_short("2026-03-14T09:41:00Z")
        self.assertIn(expect_short, body)

    def test_snippet_tooltip_has_full_year_timestamp(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("타임스탬프테스트"))
        self.assertEqual(status, 200)
        expect_full = app.fmt_ts("2026-03-14T09:41:00Z")
        self.assertIn(f'title="{app.esc(expect_full)}"', body)

    def test_snippet_without_timestamp_renders_cleanly(self):
        # the assistant turn has no "timestamp" key → ts == "" → no hint span at all,
        # just the role chip immediately followed by the highlighted text.
        status, body = self.get("/search?q=" + urllib.parse.quote("타임스탬프없음"))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)
        self.assertNotIn('<span class=hint title=""', body)   # no empty/bogus hint span
        self.assertNotIn("<span class=hint></span>", body)


class RowsFromTurnsTs(unittest.TestCase):
    """Unit-level: _rows_from_turns() must stamp every row with its turn's ts, and rows
    from the SAME turn must share the identical string object (bloat guard on the pickled
    cache payload — see the comment at app.py's _rows_from_turns)."""

    def test_multiple_rows_same_turn_share_ts_object(self):
        # tool_use seg text format is "ToolName\n{json input}" (see app._toolinput)
        turns = [
            {"role": "assistant", "tags": set(), "ts": "2026-01-02T03:04:05Z",
             "segs": [("text", "hello world"),
                      ("tool_use", "Bash\n" + json.dumps({"command": "ls"}))]},
        ]
        rows = app._rows_from_turns(turns)
        self.assertGreaterEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["ts"], "2026-01-02T03:04:05Z")
        # identical object, not just equal value — this is what keeps the pickle small
        self.assertIs(rows[0]["ts"], rows[1]["ts"])

    def test_missing_ts_defaults_to_empty_string(self):
        turns = [{"role": "you", "tags": set(), "segs": [("text", "no ts here")]}]
        rows = app._rows_from_turns(turns)
        self.assertEqual(rows[0]["ts"], "")

    def test_code_row_carries_its_turn_ts(self):
        turns = [
            {"role": "assistant", "tags": set(), "ts": "2026-05-06T07:08:09Z",
             "segs": [("text", "here is code:\n```python\nprint('hi')\n```")]},
        ]
        rows = app._rows_from_turns(turns)
        code_rows = [r for r in rows if r["kind"] & app.K_CODE]
        self.assertTrue(code_rows)
        self.assertEqual(code_rows[0]["ts"], "2026-05-06T07:08:09Z")


class StaleFtsCacheCleanup(unittest.TestCase):
    """Opening the current-schema FTS DB must sweep OTHER search-v*.sqlite3 files (and
    their -wal/-shm siblings) left behind by older _CACHE_SCHEMA/_FTS_SCHEMA versions —
    those otherwise accumulate forever since nothing else ever deletes them."""

    def setUp(self):
        self.tmpcfg = tempfile.mkdtemp()
        self._orig_cfg = app.CONFIG_DIR
        app.CONFIG_DIR = self.tmpcfg
        self._orig_con = app._FTS["con"]
        self._orig_cleaned = app._FTS["cleaned"]
        app._FTS["con"] = None
        app._FTS["cleaned"] = False
        os.makedirs(os.path.join(self.tmpcfg, "cache"), exist_ok=True)

    def tearDown(self):
        try:
            if app._FTS["con"]:
                app._FTS["con"].close()
        except Exception:
            pass
        app._FTS["con"] = self._orig_con
        app._FTS["cleaned"] = self._orig_cleaned
        app.CONFIG_DIR = self._orig_cfg
        shutil.rmtree(self.tmpcfg, ignore_errors=True)

    @unittest.skipUnless(app.fts_capable(), "SQLite build lacks FTS5 trigram/contentless_delete")
    def test_old_schema_files_removed_current_kept(self):
        cache_dir = os.path.join(self.tmpcfg, "cache")
        stale = os.path.join(cache_dir, "search-v2-c5.sqlite3")
        stale_wal = stale + "-wal"
        stale_shm = stale + "-shm"
        for p in (stale, stale_wal, stale_shm):
            with open(p, "w") as fh:
                fh.write("stale")
        current_name = os.path.basename(app._fts_db_path())

        con = app._fts_conn()   # opens the current DB, sweeping the stale files as a side effect
        self.assertIsNotNone(con)

        self.assertFalse(os.path.exists(stale))
        self.assertFalse(os.path.exists(stale_wal))
        self.assertFalse(os.path.exists(stale_shm))
        self.assertTrue(os.path.exists(os.path.join(cache_dir, current_name)))


if __name__ == "__main__":
    unittest.main()
