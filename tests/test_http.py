"""HTTP smoke tests: spin the real server on an ephemeral port against a
synthetic transcript tree and assert the core guarantees end-to-end."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # don't follow — so we can inspect the 302 + Set-Cookie


def build_fixture_root():
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-demo")
    os.makedirs(proj)
    sid = "11111111-2222-3333-4444-555555555555"
    lines = [
        {"type": "ai-title", "aiTitle": "데모 세션"},
        {"type": "user", "timestamp": "2026-06-30T01:00:00Z", "cwd": "/Users/x/launchdir",
         "gitBranch": "main", "forkedFrom": {"sessionId": "99999999-8888-7777-6666-555555555555",
                                             "messageUuid": "m1"},
         "message": {"role": "user", "content": "안녕 <b>계획</b> 알려줘"}},
        {"type": "assistant", "cwd": "/Users/x/demo", "message": {
            "role": "assistant", "model": "claude-opus-4-8",
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 200, "cache_read_input_tokens": 5000},
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "git commit -m 'x'"}},
                {"type": "text", "text": "커밋했습니다 ```python\nprint(1)\n```"}]}},
        {"type": "user", "toolUseResult": "done",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t1", "content": "Traceback: boom"}]}},
        {"type": "user", "message": {"role": "user", "content": "<task-notification>machine</task-notification>"}},
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-06-30T01:00:03Z",
         "content": ("<task-notification><task-id>audit-1</task-id><status>completed</status>"
                     "<summary>Agent &quot;Audit&quot; finished</summary>"
                     "<result>## Ranked audit\n\nLifecycle finding that must remain visible.</result>"
                     "</task-notification>")},
        {"type": "queue-operation", "operation": "remove", "timestamp": "2026-06-30T01:00:04Z",
         "content": ("<task-notification><task-id>audit-1</task-id><status>completed</status>"
                     "<summary>Agent &quot;Audit&quot; finished</summary>"
                     "<result>## Ranked audit\n\nLifecycle finding that must remain visible.</result>"
                     "</task-notification>")},
    ]
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")

    # a Codex transcript alongside the Claude one — provider_of() keys off the "rollout-" filename
    # alone (not the folder), so this can live in the same synthetic root as the Claude fixture.
    codex_sid = "019c8b6e-2595-7111-aaaa-bbbbccccdddd"
    codex_lines = [
        {"type": "session_meta", "payload": {"id": codex_sid, "cwd": "/Users/x/codexdemo"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.3-codex"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "코덱스한테 물어봄"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": "코덱스가 답함"}]}},
    ]
    codex_path = os.path.join(proj, f"rollout-2026-02-24T01-56-17-{codex_sid}.jsonl")
    with open(codex_path, "w", encoding="utf-8") as fh:
        for o in codex_lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")

    return root, os.path.join(proj, sid + ".jsonl"), codex_path


class HttpSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.session_path, cls.codex_session_path = build_fixture_root()
        # pin to the fixture: "/" with no root param now browses ALL roots, and
        # configure() auto-discovers the machine's real ~/.claude, ~/.codex, ~/.gemini
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

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_index(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("데모 세션", body)
        self.assertIn("Project stats", body)

    def test_html_pages_are_never_cached(self):
        # After a self-update the process serving pages is a different build, so a browser-cached
        # page (Back button / bfcache) would show the OLD version badge. HTML must be no-store,
        # and the pageshow fallback must be wired for browsers that restore it regardless.
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10) as r:
            self.assertIn("no-store", (r.headers.get("Cache-Control") or ""))
            body = r.read().decode("utf-8")
        self.assertIn("addEventListener('pageshow'", body)

    def test_session_attribution(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertEqual(body.count("🧑 You"), 2)          # header count chip + the one human bubble
        self.assertIn("⚙ Tool result", body)
        self.assertIn("ⓘ System / injected", body)              # task-notification never rendered as 나
        self.assertEqual(body.count("Lifecycle finding that must remain visible."), 1)
        self.assertIn('Agent &quot;Audit&quot; finished', body)
        self.assertIn('<details class="fold tasknote" open>', body)
        self.assertIn("&lt;b&gt;계획&lt;/b&gt;", body)     # user HTML is escaped
        self.assertIn("session-id", body)

    def test_codex_assistant_label_not_claude(self):
        # a Codex session's assistant turn must say "Codex", never the hardcoded "✦ Claude" that
        # used to be baked into ROLE_LABEL regardless of which agent actually wrote the transcript
        status, body = self.get("/session?p=" + urllib.parse.quote(self.codex_session_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertIn("🌀 Codex", body)
        self.assertNotIn("✦ Claude", body)

    def test_search_scopes(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("계획"))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)
        status, body = self.get("/search?q=Traceback&scope=human")
        self.assertEqual(status, 200)
        self.assertIn("No results.", body)                   # tool output is not "my words"

    def test_search_multi_term_and(self):
        # both words in the same turn → match
        status, body = self.get("/search?q=" + urllib.parse.quote("안녕 계획"))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)
        # one word matches, the other doesn't → no result (AND semantics)
        status, body = self.get("/search?q=" + urllib.parse.quote("안녕 없는단어졸라"))
        self.assertEqual(status, 200)
        self.assertIn("No results.", body)

    def test_search_phrase(self):
        # fixture text: "안녕 <b>계획</b> 알려줘" — exact contiguous phrase matches
        status, body = self.get("/search?q=" + urllib.parse.quote('"<b>계획</b> 알려줘"'))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)
        status, body = self.get("/search?q=" + urllib.parse.quote('"알려줘 계획"'))  # wrong order
        self.assertEqual(status, 200)
        self.assertIn("No results.", body)

    def test_search_scope_claude(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("커밋했습니다") + "&scope=claude")
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)

    def test_search_result_links_carry_goto(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("계획"))
        self.assertEqual(status, 200)
        self.assertIn("&goto=", body)

    def test_session_goto_scrolls_to_match(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&goto=1")
        self.assertEqual(status, 200)
        self.assertIn('document.getElementById("t1")', body)

    def test_favicon(self):
        status, body = self.get("/favicon.svg")
        self.assertEqual(status, 200)
        self.assertIn("<svg", body)

    def test_search_code_scope(self):
        # fixture assistant text has a ```python\nprint(1)\n``` fence → a CODE row
        status, body = self.get("/search?q=" + urllib.parse.quote("print(1)") + "&scope=code")
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)

    def test_search_cross_turn_session_level(self):
        # '안녕' is in the human turn, '커밋했습니다' in the later assistant turn (different turns)
        status, body = self.get("/search?q=" + urllib.parse.quote("안녕 커밋했습니다"))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)         # same-turn AND would have missed this
        self.assertTrue(("nearby" in body) or ("in session" in body))

    def test_search_neg_excludes(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("안녕 -커밋했습니다"))
        self.assertEqual(status, 200)
        self.assertIn("No results.", body)                # session has 커밋했습니다 → excluded

    def test_search_field_cmd(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("cmd:commit"))
        self.assertEqual(status, 200)
        self.assertIn("1 sessions matched", body)         # git commit is a Bash command

    def test_query_length_cap_no_crash(self):
        status, _ = self.get("/search?q=" + ("a" * 500))
        self.assertEqual(status, 200)

    def test_permalink_and_star_present(self):
        _, sv = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=all")
        self.assertIn("class=permalink", sv)
        self.assertIn("starbtn", sv)                # star on the session header
        _, idx = self.get("/")
        self.assertIn("starbtn", idx)               # and on index rows

    def test_nosniff_header(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10) as r:
            self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")

    def test_webmanifest_for_install_as_app(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/manifest.webmanifest", timeout=10) as r:
            self.assertEqual(r.status, 200)
            man = json.loads(r.read().decode())
        self.assertEqual(man["display"], "standalone")     # opens as its own window
        self.assertEqual(man["name"], "AI Session Search")
        _, body = self.get("/")
        self.assertIn('rel="manifest"', body)
        self.assertIn('id=installbtn', body)                # one-click install button

    def test_language_switch(self):
        # default is English UI, with a 🌐 language switcher
        status, en = self.get("/")
        self.assertIn("Project stats", en)
        self.assertNotIn("프로젝트별 통계", en)
        self.assertIn("langsw", en)
        # a Korean cookie flips the UI to Korean (data like "데모 세션" is unchanged either way)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/")
        req.add_header("Cookie", "cchlang=ko")
        with urllib.request.urlopen(req, timeout=10) as r:
            ko = r.read().decode("utf-8")
        self.assertIn("프로젝트별 통계", ko)
        self.assertNotIn("Project stats", ko)

    def test_lang_query_sets_cookie_and_redirects(self):
        try:
            urllib.request.build_opener(_NoRedirect()).open(
                f"http://127.0.0.1:{self.port}/?lang=ko", timeout=10)
            self.fail("expected a 302 redirect")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertIn("cchlang=ko", e.headers.get("Set-Cookie", ""))
            self.assertEqual(e.headers.get("Location"), "/")   # clean redirect, lang param stripped
            e.close()

    def test_search_by_session_id(self):
        sid = "11111111-2222-3333-4444-555555555555"
        status, body = self.get("/search?q=" + sid + "&scope=all")
        self.assertEqual(status, 200)
        self.assertIn("데모 세션", body)        # the session is found by its own id
        self.assertIn(">ref<", body)             # reference-match chip / label

    def test_search_by_branched_from_id(self):
        status, body = self.get("/search?q=99999999-8888-7777-6666-555555555555&scope=all")
        self.assertEqual(status, 200)
        self.assertIn("데모 세션", body)        # found via its forkedFrom (Branched from) id

    def test_search_by_workspace_path(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("launchdir") + "&scope=all")
        self.assertEqual(status, 200)
        self.assertIn("데모 세션", body)        # findable by the launch dir in metadata

    def test_token_and_model_in_session(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertIn("<b>Tokens</b>", body)          # session token summary
        self.assertIn("Opus 4.8", body)              # model badge (claude-opus-4-8 → Opus 4.8)
        self.assertIn("tokb qtok", body)             # per-question token badge on the 🧑 turn

    def test_token_column_in_index(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Out tokens", body)              # project-stats token column
        self.assertIn("class=mdlcell", body)         # model-mix column

    def test_in_session_search(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path)
                                + "&sq=" + urllib.parse.quote("계획"))
        self.assertEqual(status, 200)
        self.assertIn("messages matched in this session", body)           # in-session result bar
        self.assertIn("1 messages matched in this session", body)        # the one human turn matches "계획"
        self.assertIn("← full conversation", body)

    def test_in_session_search_bash_command(self):
        # tool-call text is searchable in-session too (git commit lives in a tool_use)
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path)
                                + "&sq=" + urllib.parse.quote("git commit"))
        self.assertIn("1 messages matched in this session", body)

    def test_session_metadata_card(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertIn("Session Reference", body)
        self.assertIn("Workspace", body)
        self.assertIn("/Users/x/demo", body)                  # workspace = last cwd
        self.assertIn("Started in", body)
        self.assertIn("/Users/x/launchdir", body)             # launch dir = first cwd (differs)
        self.assertIn("Branched from", body)
        self.assertIn("99999999-8888-7777-6666-555555555555", body)

    def test_search_multicolor_key(self):
        status, body = self.get("/search?q=" + urllib.parse.quote("안녕 계획"))
        self.assertEqual(status, 200)
        self.assertIn('hlkey hl0', body)      # per-term color key in header
        self.assertIn('hlkey hl1', body)

    def test_search_custom_date_range_excludes_old(self):
        # fixture session mtime is "now"; a past-only window must exclude it
        status, body = self.get("/search?q=" + urllib.parse.quote("계획") + "&from=2000-01-01&to=2000-12-31")
        self.assertEqual(status, 200)
        self.assertIn("No results.", body)

    def test_code_view(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&view=code")
        self.assertEqual(status, 200)
        self.assertIn("print(1)", body)

    def test_path_traversal_rejected(self):
        status, body = self.get("/session?p=/etc/hosts")
        self.assertEqual(status, 200)
        self.assertIn("Session not found.", body)

    def test_addroot_rejects_garbage(self):
        status, body = self.get("/addroot?path=/definitely-not-real")
        self.assertEqual(status, 200)
        self.assertIn("Could not add that folder.", body)

    def test_404(self):
        try:
            self.get("/nope")
            self.fail("expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            e.close()

    def test_dns_rebinding_host_rejected(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/")
        req.add_header("Host", "evil.example.com")
        try:
            urllib.request.urlopen(req, timeout=10).close()
            self.fail("expected 403")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)
            e.close()

    def test_malformed_off_param_no_crash(self):
        status, _ = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&off=abc")
        self.assertEqual(status, 200)

    def test_search_ajax_returns_bare_fragment(self):
        # &ajax=1 returns just the results fragment (for the client-side swap), not the full shell
        status, frag = self.get("/search?q=" + urllib.parse.quote("계획") + "&ajax=1")
        self.assertEqual(status, 200)
        self.assertNotIn("<head>", frag)
        self.assertNotIn("<form", frag)                    # no header/shell chrome
        self.assertIn("sessions matched", frag)            # the real results content
        # same query without ajax is the full page (has the shell + search form)
        _, full = self.get("/search?q=" + urllib.parse.quote("계획"))
        self.assertIn("<form", full)
        self.assertIn("sessions matched", full)


def build_phrase_root():
    """A root whose one session contains a distinctive sentence verbatim in a late turn,
    while its individual words also scatter across an earlier turn (the trap)."""
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-phrase")
    os.makedirs(proj)
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    sentence = "Inspired by and building on the ideas of the original folder plugin."
    lines = [
        {"type": "user", "timestamp": "2026-07-01T00:00:00Z",
         "message": {"role": "user", "content": "by and on the of building ideas folder plugin original"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}},
    ]
    # pad so the verbatim sentence lands well past the first page → goto must page to it
    for i in range(30):
        lines.append({"type": "user", "message": {"role": "user", "content": f"filler {i}"}})
    lines.append({"type": "user", "timestamp": "2026-07-01T00:05:00Z",
                  "message": {"role": "user", "content": f"Credits\n{sentence}\n==> keep this?"}})
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl"), sentence


class ImplicitPhraseHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path, cls.sentence = build_phrase_root()
        app.configure(cls.root)
        app.DEFAULT_ROOTS = [cls.root]; app.SAVED_ROOTS = []
        app.ROOTS[:] = [cls.root]; app.ROOT = cls.root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def _target_gi(self):
        rows = app.search_rows(self.path)
        return next(r["gi"] for r in rows if self.sentence.lower() in r["text"].lower())

    def test_unquoted_sentence_jumps_to_verbatim_turn(self):
        status, body = self.get("/search?q=" + urllib.parse.quote(self.sentence))
        self.assertEqual(status, 200)
        self.assertIn(f"goto={self._target_gi()}", body)      # not the early word-scatter turn

    def test_fallback_note_when_no_exact_phrase(self):
        # three words that never appear contiguously anywhere
        status, body = self.get("/search?q=" + urllib.parse.quote("building plugin filler"))
        self.assertEqual(status, 200)
        self.assertIn("No session contains that as an exact phrase", body)

    def test_no_fallback_note_when_phrase_found(self):
        status, body = self.get("/search?q=" + urllib.parse.quote(self.sentence))
        self.assertNotIn("No session contains that as an exact phrase", body)

    def test_in_session_search_prefers_phrase(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path)
                                + "&sq=" + urllib.parse.quote(self.sentence))
        self.assertEqual(status, 200)
        self.assertIn("1 messages matched in this session", body)   # only the verbatim turn, not the scatter
        self.assertIn("exact phrase", body)


def build_long_root():
    """A session long enough (well past DEFAULT_LIM=1000 turns) that a goto deep inside it
    lands on an OFF-CENTER window — i.e. the rendered page does not start at turn 0 — so
    data-firstpage (the g/Home/Cmd+Up target) must point back at the first page."""
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-long")
    os.makedirs(proj)
    sid = "cccccccc-dddd-eeee-ffff-000011112222"
    lines = []
    for i in range(1300):
        lines.append({"type": "user", "message": {"role": "user", "content": f"turn {i}"}})
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl")


class LazyWindowGotoHttp(unittest.TestCase):
    """Server-side half of the g/Home/Cmd+Up 'go to true top' behavior: unit tests can only
    reach the rendered HTML, not the browser-side navigation, so this is a cheap smoke test
    that the wiring shipped — data-firstpage points at the first page (off=0) for an
    off-center goto window, and the loadAllThenTop JS function name is present to drive it."""

    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_long_root()
        app.configure(cls.root)
        app.DEFAULT_ROOTS = [cls.root]; app.SAVED_ROOTS = []
        app.ROOTS[:] = [cls.root]; app.ROOT = cls.root
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def test_offcenter_goto_window_has_loadprev_and_load_all_then_top(self):
        # goto=1000 in a 1300-turn session with an explicit lim=200 (independent of whatever
        # default_lim this machine's persisted settings.json happens to hold): the centered
        # window is turns [900,1100) — that IS the page (off=900), so there is nothing earlier
        # to load *within the page*; #loadprev must NOT appear (it would mean crossing into the
        # previous page, which is the bug this fix removes)...
        status, body = self.get("/session?p=" + urllib.parse.quote(self.path) + "&goto=1000&lim=200")
        self.assertEqual(status, 200)
        self.assertNotIn('id=loadprev', body)
        # ...instead the page carries a data-firstpage target (off=0) so g/Home/Cmd+Up navigate
        # straight to the first page instead of walking backward past the page boundary.
        self.assertIn('data-firstpage="', body)
        self.assertNotIn('data-firstpage=""', body)
        # the client-side function that drives g / Home / Cmd+Up must still be wired into the page.
        self.assertIn('loadAllThenTop', body)


if __name__ == "__main__":
    unittest.main()
