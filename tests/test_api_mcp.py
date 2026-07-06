"""Agent-access layer: data API, JSON HTTP endpoints, MCP (dispatch + stdio
protocol) and the one-shot CLI (--search/--get/--sessions). All hit the same
engine the web UI uses, so we assert the shape agents actually consume."""
import io
import json
import os
import sys
import tempfile
import threading
import types
import unittest
import urllib.parse
import urllib.request
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402

SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def build_root():
    root = tempfile.mkdtemp()
    proj = os.path.join(root, "-Users-x-proj")
    os.makedirs(proj)
    lines = [
        {"type": "ai-title", "aiTitle": "API demo"},
        {"type": "user", "timestamp": "2026-06-30T01:00:00Z", "cwd": "/Users/x/proj",
         "message": {"role": "user", "content": "how do I fix the pyinstaller locales bug"}},
        {"type": "assistant", "cwd": "/Users/x/proj", "message": {
            "role": "assistant", "model": "claude-opus-4-8",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": "pyinstaller --add-data locales --name zzcmdtoken"}},
                {"type": "text", "text": "use --add-data for the locales dir"}]}},
        {"type": "user", "message": {"role": "user", "content": "<task-notification>machine</task-notification>"}},
    ]
    with open(os.path.join(proj, SID + ".jsonl"), "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    return root, os.path.join(proj, SID + ".jsonl")


def pin(root):
    """Isolate tests from the machine's real roots: aggregate APIs cross ALL
    roots, and configure() auto-discovers ~/.claude, ~/.codex, ~/.gemini +
    saved roots. Pin to just the fixture so results are deterministic + fast."""
    app.configure(root)
    app.DEFAULT_ROOTS = [root]
    app.SAVED_ROOTS = []
    app.ROOTS[:] = [root]
    app.ROOT = root


class DataApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_root()
        pin(cls.root)

    def test_search_all_returns_dicts(self):
        res = app.search_all("pyinstaller locales", "all", 10)
        self.assertTrue(res)
        r = res[0]
        for k in ("sid", "provider", "title", "workspace", "path", "match", "snippets", "score"):
            self.assertIn(k, r)
        self.assertNotIn("mtime", r)               # internal sort key stripped from output
        self.assertEqual(r["provider"], "claude")

    def test_search_scope_human_excludes_tool_output(self):
        # 'zzcmdtoken' lives ONLY in the Bash command (a tool_use), not the human's words
        self.assertTrue(app.search_all("zzcmdtoken", "tool", 10))
        self.assertFalse(app.search_all("zzcmdtoken", "human", 10))
        self.assertTrue(app.search_all("fix", "human", 10))       # the human did type "fix"

    def test_search_field_cmd(self):
        self.assertTrue(app.search_all("cmd:pyinstaller", "all", 10))

    def test_sessions_api(self):
        s = app.sessions_api(self.root, 10)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["sid"], SID)
        self.assertEqual(s[0]["title"], "API demo")

    def test_find_by_sid_prefix(self):
        self.assertEqual(app.find_by_sid(SID[:8]), self.path)
        self.assertIsNone(app.find_by_sid("nope-nope"))

    def test_session_api_by_sid(self):
        d = app.session_api(None, SID, 400)
        self.assertIsNotNone(d)
        self.assertEqual(d["provider"], "claude")
        roles = [t["role"] for t in d["turns"]]
        self.assertIn("you", roles)
        self.assertIn("assistant", roles)
        you = next(t for t in d["turns"] if t["role"] == "you")
        self.assertIn("fix", you["text"])          # the human's actual words are returned verbatim
        self.assertTrue(d.get("tokens"))

    def test_session_api_missing(self):
        self.assertIsNone(app.session_api(None, "does-not-exist", 400))

    def test_roots_api(self):
        rs = app.roots_api()
        self.assertTrue(any(r["provider"] == "claude" for r in rs))


class McpDispatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_root()
        pin(cls.root)

    def test_search_tool(self):
        out = app._mcp_call("search_sessions", {"query": "pyinstaller", "limit": 5})
        self.assertTrue(out and out[0]["sid"] == SID)

    def test_get_tool(self):
        out = app._mcp_call("get_session", {"sid": SID})
        self.assertEqual(out["provider"], "claude")

    def test_get_tool_missing(self):
        out = app._mcp_call("get_session", {"sid": "nope"})
        self.assertIn("error", out)

    def test_list_recent_tool(self):
        out = app._mcp_call("list_recent_sessions", {"limit": 5})
        self.assertTrue(any(s["sid"] == SID for s in out))

    def test_list_recent_provider_filter(self):
        self.assertTrue(app._mcp_call("list_recent_sessions", {"provider": "claude"}))
        self.assertEqual(app._mcp_call("list_recent_sessions", {"provider": "codex"}), [])

    def test_unknown_tool(self):
        self.assertIn("error", app._mcp_call("bogus", {}))


class McpProtocol(unittest.TestCase):
    """Drive run_mcp() over fake stdio: newline-delimited JSON-RPC 2.0."""
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_root()
        pin(cls.root)

    def _roundtrip(self, requests):
        inp = "".join(json.dumps(r) + "\n" for r in requests)
        out = io.StringIO()
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(inp), out
        try:
            app.run_mcp()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        return [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]

    def test_full_session(self):
        replies = self._roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},   # no reply expected
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "search_sessions", "arguments": {"query": "pyinstaller"}}},
        ])
        self.assertEqual([r.get("id") for r in replies], [1, 2, 3])   # notification got no reply
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "ai-session-search")
        names = [t["name"] for t in replies[1]["result"]["tools"]]
        self.assertEqual(set(names), {"search_sessions", "get_session", "list_recent_sessions"})
        payload = json.loads(replies[2]["result"]["content"][0]["text"])
        self.assertTrue(payload and payload[0]["sid"] == SID)

    def test_unknown_method_errors(self):
        replies = self._roundtrip([{"jsonrpc": "2.0", "id": 9, "method": "resources/list"}])
        self.assertEqual(replies[0]["error"]["code"], -32601)

    def test_bad_json_line_ignored(self):
        replies = self._roundtrip([{"jsonrpc": "2.0", "id": 5, "method": "tools/list"}])
        # (bad line injected manually)
        inp = "not json\n" + json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/list"}) + "\n"
        out = io.StringIO()
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(inp), out
        try:
            app.run_mcp()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        got = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(got), 1)                 # garbage line skipped, valid one answered


class Cli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_root()
        pin(cls.root)

    def _run(self, **kw):
        args = types.SimpleNamespace(search=None, get=None, sessions=False,
                                     scope="all", limit=20, json=False)
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app._run_cli(args)
        return rc, buf.getvalue()

    def test_search_json(self):
        rc, out = self._run(search="pyinstaller", json=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(data and data[0]["sid"] == SID)

    def test_search_human_readable(self):
        rc, out = self._run(search="pyinstaller")
        self.assertEqual(rc, 0)
        self.assertIn(SID, out)
        self.assertIn("API demo", out)

    def test_search_empty(self):
        rc, out = self._run(search="zzz-nothing-matches-qqq")
        self.assertEqual(rc, 0)
        self.assertIn("no matching", out.lower())

    def test_get_json(self):
        rc, out = self._run(get=SID, json=True)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["sid"], SID)

    def test_get_missing_returns_1(self):
        rc, out = self._run(get="does-not-exist")
        self.assertEqual(rc, 1)

    def test_sessions_json(self):
        rc, out = self._run(sessions=True, json=True)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)[0]["sid"], SID)


class JsonHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.path = build_root()
        pin(cls.root)
        cls.srv = app.make_server(port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))

    def test_api_roots(self):
        status, body = self.get("/api/roots")
        self.assertEqual(status, 200)
        self.assertTrue(any(r["provider"] == "claude" for r in body["roots"]))

    def test_api_search(self):
        status, body = self.get("/api/search?q=" + urllib.parse.quote("pyinstaller") + "&limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], len(body["results"]))
        self.assertTrue(body["results"] and body["results"][0]["sid"] == SID)

    def test_search_format_json(self):
        status, body = self.get("/search?format=json&q=" + urllib.parse.quote("pyinstaller"))
        self.assertEqual(status, 200)
        self.assertIn("results", body)

    def test_api_sessions(self):
        status, body = self.get("/api/sessions?limit=10")
        self.assertEqual(status, 200)
        self.assertTrue(any(s["sid"] == SID for s in body["sessions"]))

    def test_api_session_by_sid(self):
        status, body = self.get("/api/session?sid=" + SID)
        self.assertEqual(status, 200)
        self.assertEqual(body["sid"], SID)
        self.assertTrue(body["turns"])

    def test_api_session_missing_404(self):
        try:
            self.get("/api/session?sid=nope-nope-nope")
            self.fail("expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
            e.close()


if __name__ == "__main__":
    unittest.main()
