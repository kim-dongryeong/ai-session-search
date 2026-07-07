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
    ]
    with open(os.path.join(proj, sid + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, sid + ".jsonl")


class HttpSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.session_path = build_fixture_root()
        app.configure(cls.root)
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

    def test_session_attribution(self):
        status, body = self.get("/session?p=" + urllib.parse.quote(self.session_path) + "&lim=all")
        self.assertEqual(status, 200)
        self.assertEqual(body.count("🧑 You"), 2)          # header count chip + the one human bubble
        self.assertIn("⚙ Tool result", body)
        self.assertIn("ⓘ System / injected", body)              # task-notification never rendered as 나
        self.assertIn("&lt;b&gt;계획&lt;/b&gt;", body)     # user HTML is escaped
        self.assertIn("session-id", body)

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


if __name__ == "__main__":
    unittest.main()
