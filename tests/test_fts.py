"""FTS candidate-index correctness: the SQLite trigram pre-filter must be a pure
performance layer — for every query, searching WITH the candidate index must return
exactly the same results (paths + scores) as the classic full scan. Recall 100%,
no false negatives. Also covers the capability probe and the incremental lifecycle."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


def _session(path, turns, cwd="/Users/x/proj"):
    """turns: list of (role, text). role 'user' or 'assistant'."""
    lines = [{"type": "user", "cwd": cwd, "timestamp": "2026-07-01T00:00:00Z",
              "message": {"role": "user", "content": "session start"}}]
    for role, text in turns:
        if role == "user":
            lines.append({"type": "user", "cwd": cwd,
                          "message": {"role": "user", "content": text}})
        else:
            lines.append({"type": "assistant",
                          "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}})
    with open(path, "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")


def build_corpus():
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-proj")
    os.makedirs(proj)
    def sid(n): return f"{n:08d}-1111-2222-3333-444444444444"
    # A: cross-turn AND — 'alphaword' and 'betaword' in different turns
    _session(os.path.join(proj, sid(1) + ".jsonl"),
             [("user", "alphaword appears here"), ("assistant", "unrelated middle"),
              ("user", "and betaword appears later")])
    # B: Korean agglutinated — contains 검색해줘 (so '검색해' 3-char and '검색' 2-char both should find it)
    _session(os.path.join(proj, sid(2) + ".jsonl"),
             [("user", "저는 검색해줘 라고 입력했고 최적화 이야기를 했다")])
    # C: metadata-only — the term 'zulu' is only in the workspace path, not the body
    _session(os.path.join(proj, sid(3) + ".jsonl"),
             [("user", "ordinary body without the special token")], cwd="/Users/x/zulu-workspace")
    # D: paths and URLs
    _session(os.path.join(proj, sid(4) + ".jsonl"),
             [("user", "edited src/app.py and opened https://github.com/foo/bar/pull/42")])
    # E: contiguous phrase
    _session(os.path.join(proj, sid(5) + ".jsonl"),
             [("user", "the quick brown fox jumps"), ("assistant", "hello world contiguous here")])
    # F: distractor with none of the above
    _session(os.path.join(proj, sid(6) + ".jsonl"),
             [("user", "totally different content nothing shared")])
    return root


QUERIES = [
    "alphaword betaword",          # cross-turn AND (both >=3 → FTS anchored)
    "검색해",                       # 3-char Korean substring (FTS anchored)
    "검색",                         # 2-char Korean → must fall back, still find B
    "검색해줘 최적화",              # two Korean tokens, cross concept
    "zulu",                        # metadata-only (in cwd path, not body)
    "app.py",                      # path fragment
    "hello world",                 # phrase-ish
    '"hello world"',               # quoted phrase
    "quick brown fox",             # implicit 3-word phrase
    "pull",                        # short-ish common word
    "nonexistent-term-xyz",        # no hits
    "brown alphaword",             # spans two different sessions → no session has both → empty
    "file:app.py",                 # field query
    "betaword -alphaword",         # negation (excludes A → empty)
    "junkabsent quick fox hello contiguous world",   # 6-word, one absent → pigeonhole OR branch
]


class FtsEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpcfg = tempfile.mkdtemp()
        cls._orig_cfg = app.CONFIG_DIR
        app.CONFIG_DIR = cls.tmpcfg          # keep the FTS DB out of the real cache
        cls.root = build_corpus()
        app.configure(cls.root)              # non-exclusive → FTS active
        app.ROOTS[:] = [cls.root]; app.ROOT = cls.root
        app.DEFAULT_ROOTS = [cls.root]; app.SAVED_ROOTS = []
        cls.assertTrue_ = app.fts_capable()
        app.fts_warm(cls.root)               # build the index up front

    @classmethod
    def tearDownClass(cls):
        try:
            if app._FTS["con"]: app._FTS["con"].close()
        except Exception:
            pass
        app._FTS["con"] = None; app._FTS["disabled"] = False
        app._FTS_ENABLED = True
        app.CONFIG_DIR = cls._orig_cfg
        shutil.rmtree(cls.root, ignore_errors=True)
        shutil.rmtree(cls.tmpcfg, ignore_errors=True)

    def _results(self, q):
        return {(r["path"], r["score"]) for r in app.search_api(self.root, q, "all", "", 100)}

    def test_capable(self):
        self.assertTrue(app.fts_capable(), "SQLite build lacks FTS5/trigram/contentless_delete")

    def test_equivalence_fts_on_vs_off(self):
        for q in QUERIES:
            app._FTS_ENABLED = True
            on = self._results(q)
            app._FTS_ENABLED = False
            off = self._results(q)
            app._FTS_ENABLED = True
            self.assertEqual(on, off, f"FTS changed results for query {q!r}: on={on} off={off}")

    def test_candidate_used_for_anchored_query(self):
        # a >=3-char query should actually go through the FTS path (return a set, not None)
        c = app.fts_candidates(self.root, ["alphaword", "betaword"], [], {}, [])
        self.assertIsNotNone(c)
        self.assertTrue(all(isinstance(p, str) for p in c))

    def test_two_char_query_falls_back(self):
        # all positive terms 1-2 chars → cannot narrow safely → None (full scan)
        self.assertIsNone(app.fts_candidates(self.root, ["검", "색"], [], {}, []))

    def test_incremental_pickup_of_new_session(self):
        # a brand-new session must be found immediately (dirty/new → force-included candidate)
        proj = os.path.join(self.root, "-Users-x-proj")
        newp = os.path.join(proj, "99999999-9999-9999-9999-999999999999.jsonl")
        _session(newp, [("user", "freshly added uniquetoken content")])
        app._INDEX["by_root"].pop(self.root, None)   # force index refresh to see the file
        res = {r["path"] for r in app.search_api(self.root, "uniquetoken", "all", "", 100)}
        self.assertIn(newp, res)

    def test_appended_session_found_before_reindex(self):
        # Codex 3차 correctness blocker: a session appended-to AFTER indexing, but NOT yet
        # reindexed, must still be found — the stale DB key marks it dirty → exact-matched.
        proj = os.path.join(self.root, "-Users-x-proj")
        target = os.path.join(proj, "00000002-1111-2222-3333-444444444444.jsonl")  # session B
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user",
                     "message": {"role": "user", "content": "laggedterm appended after indexing"}}) + "\n")
        # deliberately do NOT call fts_warm — the index still holds the old (shorter) version
        app._INDEX["by_root"].pop(self.root, None)
        res = {r["path"] for r in app.search_api(self.root, "laggedterm", "all", "", 100)}
        self.assertIn(target, res, "appended term lost while the background index lagged")

    def test_cold_search_uses_db_payload_not_bulk_load(self):
        # after the index is built, wiping the in-RAM row cache must NOT force a full reparse:
        # a selective search loads only its candidates' payloads from the DB, and results match.
        app.fts_warm(self.root)
        with app._SEARCH["lock"]:
            app._SEARCH["by_path"].clear()          # simulate a cold restart
        with app._DISK["lock"]:
            app._DISK["rows_loaded"].discard(self.root)
        res = {r["path"] for r in app.search_api(self.root, "uniquetoken freshly", "all", "", 100)}
        loaded = len(app._SEARCH["by_path"])
        # only a tiny subset of the corpus should have been deserialized (candidate-only)
        self.assertLess(loaded, len(app.session_files(self.root)))
        # and the payload round-trip is byte-identical → same results as a fresh parse
        app._FTS_ENABLED = False
        with app._SEARCH["lock"]:
            app._SEARCH["by_path"].clear()
        parsed = {r["path"] for r in app.search_api(self.root, "uniquetoken freshly", "all", "", 100)}
        app._FTS_ENABLED = True
        self.assertEqual(res, parsed)

    def test_forgiving_paste_with_absent_words_is_found_via_fts(self):
        # a pasted sentence with junk words that appear NOWHERE must still find the passage,
        # and the FTS fast path must agree with the full scan (OR-of-subphrases candidate).
        proj = os.path.join(self.root, "-Users-x-proj")
        newp = os.path.join(proj, "cccc2222-2222-2222-2222-222222222222.jsonl")
        _session(newp, [("user", "Credits\nInspired by and building on the ideas of the "
                                 "original folder plugin by someone.\n==> keep this?")])
        app._INDEX["by_root"].pop(self.root, None)
        app.fts_warm(self.root)
        q = "junkone junktwo building on the ideas of the original folder plugin by someone"
        app._FTS_ENABLED = True
        on = {r["path"] for r in app.search_api(self.root, q, "all", "", 100)}
        app._FTS_ENABLED = False
        off = {r["path"] for r in app.search_api(self.root, q, "all", "", 100)}
        app._FTS_ENABLED = True
        self.assertIn(newp, on, "forgiving paste didn't find the passage via FTS")
        self.assertEqual(on, off, "FTS fast path diverged from the full scan on a fuzzy paste")

    def test_payload_round_trips(self):
        app.fts_warm(self.root)
        p = app.session_files(self.root)[0]
        st = os.stat(p); key = (st.st_mtime_ns, st.st_size)
        rows, blob, tokens = app._rows_blob(p)
        got = app._fts_load_payload(p, key)
        self.assertIsNotNone(got)
        self.assertEqual((got[0], got[1]), (rows, blob))     # rows + blob identical
        self.assertEqual(list(got[2]), list(tokens))         # packed token array identical

    def test_deleted_session_excluded_despite_stale_fts_row(self):
        proj = os.path.join(self.root, "-Users-x-proj")
        victim = os.path.join(proj, "00000004-1111-2222-3333-444444444444.jsonl")  # session D (app.py)
        self.assertTrue(os.path.exists(victim))
        os.remove(victim)                             # FTS row for it still exists in the DB
        app._INDEX["by_root"].pop(self.root, None)
        res = {r["path"] for r in app.search_api(self.root, "app.py", "all", "", 100)}
        self.assertNotIn(victim, res)


class FtsPigeonhole(unittest.TestCase):
    """The generalized FTS candidate selector: pigeonhole OR of the most-selective terms
    (replacing OR-of-contiguous-windows), its doc-count cache, and the retightened
    slot-count pre-filter. Each test gets its own isolated root + FTS db."""

    def setUp(self):
        self.tmpcfg = tempfile.mkdtemp()
        self._orig_cfg = app.CONFIG_DIR
        app.CONFIG_DIR = self.tmpcfg
        self.root = build_corpus()
        app.configure(self.root)
        app.ROOTS[:] = [self.root]; app.ROOT = self.root
        app.DEFAULT_ROOTS = [self.root]; app.SAVED_ROOTS = []
        app.fts_warm(self.root)

    def tearDown(self):
        try:
            if app._FTS["con"]: app._FTS["con"].close()
        except Exception:
            pass
        app._FTS["con"] = None; app._FTS["disabled"] = False
        app._FTS_ENABLED = True
        app.CONFIG_DIR = self._orig_cfg
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.tmpcfg, ignore_errors=True)

    def _proj(self):
        return os.path.join(self.root, "-Users-x-proj")

    def _reindex(self):
        app._INDEX["by_root"].pop(self.root, None)
        app.fts_warm(self.root)

    def test_pigeonhole_candidate_is_superset_with_missing_word(self):
        # a session holding 6 of a 7-word query (one word absent entirely) must still be a
        # candidate, and FTS-on must equal FTS-off for that query.
        sid = "eeee1111-1111-1111-1111-111111111111"
        _session(os.path.join(self._proj(), sid + ".jsonl"),
                 [("user", "alpha beta gamma delta epsilon zeta present here")])
        self._reindex()
        terms = ["missingword", "alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        cand = app.fts_candidates(self.root, terms, [], {}, [])
        self.assertIsNotNone(cand)
        target = os.path.join(self._proj(), sid + ".jsonl")
        self.assertIn(target, cand)
        q = " ".join(terms)
        app._FTS_ENABLED = True
        on = {(r["path"], r["score"]) for r in app.search_api(self.root, q, "all", "", 100)}
        app._FTS_ENABLED = False
        off = {(r["path"], r["score"]) for r in app.search_api(self.root, q, "all", "", 100)}
        app._FTS_ENABLED = True
        self.assertEqual(on, off)
        self.assertIn(target, {p for p, _ in on})

    def test_pigeonhole_picks_rare_terms(self):
        # 30 sessions share one common word; only ONE session also holds 4 rare words.
        # The pigeonhole OR must pick the rare terms (fewest candidates), not the common one.
        proj = self._proj()
        for i in range(30):
            _session(os.path.join(proj, f"cccc{i:04d}-0000-0000-0000-000000000000.jsonl"),
                     [("user", "commonword appears in every extra session here")])
        rare_sid = "dddd0000-0000-0000-0000-000000000000"
        _session(os.path.join(proj, rare_sid + ".jsonl"),
                 [("user", "commonword raretokenone raretokentwo raretokenthree "
                           "raretokenfour appears here")])
        self._reindex()
        con = app._fts_conn()
        common_count = app._fts_doc_count(con, self.root, "commonword")
        rare_count = app._fts_doc_count(con, self.root, "raretokenone")
        self.assertLess(rare_count, common_count)
        terms = ["commonword", "raretokenone", "raretokentwo", "raretokenthree", "raretokenfour"]
        cand = app.fts_candidates(self.root, terms, [], {}, [])
        self.assertIsNotNone(cand)
        self.assertLessEqual(len(cand), common_count)
        self.assertIn(os.path.join(proj, rare_sid + ".jsonl"), cand)

    def test_doc_count_cached_bounded_and_invalidated(self):
        proj = self._proj()
        for i in range(6):
            _session(os.path.join(proj, f"bbbb{i:04d}-0000-0000-0000-000000000000.jsonl"),
                     [("user", "sharedword appears in this extra session too")])
        self._reindex()
        con = app._fts_conn()
        orig_cap = app._DOCCOUNT_CAP
        app._DOCCOUNT_CAP = 3                     # small cap so a common term visibly saturates
        try:
            c1 = app._fts_doc_count(con, self.root, "sharedword")
            self.assertEqual(c1, 3)                # saturates at the (lowered) cap
            key = (app._FTS_GEN[0], self.root, "sharedword")
            self.assertIn(key, app._FTS_DOCCOUNT)
            app._FTS_DOCCOUNT[key] = -1            # sentinel: proves the 2nd call reads the cache
            c2 = app._fts_doc_count(con, self.root, "sharedword")
            self.assertEqual(c2, -1)
            app._FTS_DOCCOUNT[key] = c1
        finally:
            app._DOCCOUNT_CAP = orig_cap
        # a no-op fts_warm (nothing on disk changed) must NOT invalidate the cache
        gen_before, size_before = app._FTS_GEN[0], len(app._FTS_DOCCOUNT)
        app.fts_warm(self.root)
        self.assertEqual(app._FTS_GEN[0], gen_before)
        self.assertEqual(len(app._FTS_DOCCOUNT), size_before)
        # a REAL delta must bump the generation and clear the cache
        _session(os.path.join(proj, "newdelta0-0000-0000-0000-000000000000.jsonl"),
                 [("user", "another brand new session")])
        self._reindex()
        self.assertGreater(app._FTS_GEN[0], gen_before)
        self.assertNotIn(key, app._FTS_DOCCOUNT)
        # _fts_reset also unconditionally bumps + clears
        gen_before2 = app._FTS_GEN[0]
        app._fts_doc_count(app._fts_conn(), self.root, "sharedword")
        app._fts_reset()
        self.assertGreater(app._FTS_GEN[0], gen_before2)
        self.assertEqual(len(app._FTS_DOCCOUNT), 0)

    def test_prefilter_slot_gate_skips_cheaply(self):
        # FTS off (full-scan root): a 4-word query with only 1 term present anywhere in the
        # session must be dropped by the cheap slot gate before match_session ever runs.
        app._FTS_ENABLED = False
        calls = []
        orig = app.match_session
        def spy(*a, **k):
            calls.append(1)
            return orig(*a, **k)
        app.match_session = spy
        try:
            res = app.search_api(self.root, "alphaword neverpresent1 neverpresent2 neverpresent3",
                                  "all", "", 100)
        finally:
            app.match_session = orig
            app._FTS_ENABLED = True
        target = os.path.join(self._proj(), "00000001-1111-2222-3333-444444444444.jsonl")
        self.assertNotIn(target, {r["path"] for r in res})
        self.assertEqual(calls, [])

    def test_fts_on_equals_off_missing_words(self):
        # N>=5-word query with one word absent entirely from the corpus: FTS-on must equal
        # FTS-off (the pigeonhole branch must not lose the session with the absent word).
        q = "junkabsent quick fox hello contiguous world"
        app._FTS_ENABLED = True
        on = {(r["path"], r["score"]) for r in app.search_api(self.root, q, "all", "", 100)}
        app._FTS_ENABLED = False
        off = {(r["path"], r["score"]) for r in app.search_api(self.root, q, "all", "", 100)}
        app._FTS_ENABLED = True
        self.assertEqual(on, off)
        self.assertTrue(on)      # session E (quick brown fox / hello world contiguous) is found

    def test_too_few_long_terms_falls_back(self):
        # only one >=3-char term for a 3-word query (need_or=2 > 1 available) → full scan.
        sq = app.parse_search_query("ab cd effective")
        self.assertIsNone(app.fts_candidates(self.root, sq["terms"], [], {}, []))
        # all content 1-2 chars → the existing has_content-and-not-anchors guard.
        sq2 = app.parse_search_query("xy")
        self.assertIsNone(app.fts_candidates(self.root, sq2["terms"], [], {}, []))


if __name__ == "__main__":
    unittest.main()
