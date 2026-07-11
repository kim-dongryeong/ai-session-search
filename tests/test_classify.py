"""Attribution ruleset regression tests — the core guarantee of ai-session-search:
nothing machine-authored may ever be classified as the human ("you")."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from ai_session_search import app  # noqa: E402


def user_line(content, **extra):
    o = {"type": "user", "message": {"role": "user", "content": content}}
    o.update(extra)
    return o


def asst_line(blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


class ClassifyLine(unittest.TestCase):
    # ---- genuine human ----
    def test_human_string(self):
        role, segs = app.classify_line(user_line("이게 무슨 말이야?"))
        self.assertEqual(role, "you")
        self.assertEqual(segs, [("text", "이게 무슨 말이야?")])

    def test_human_with_ide_marker_sibling(self):
        content = [
            {"type": "text", "text": "<ide_opened_file>The user opened x.md</ide_opened_file>"},
            {"type": "text", "text": "진짜 질문"},
        ]
        role, segs = app.classify_line(user_line(content))
        self.assertEqual(role, "you")
        self.assertIn(("text", "진짜 질문"), segs)
        self.assertTrue(any(k == "injected" for k, _ in segs))  # marker folded, not lost

    def test_human_image_paste(self):
        content = [{"type": "text", "text": "[Image #1] 봐줘"}, {"type": "image", "source": {}}]
        role, _ = app.classify_line(user_line(content))
        self.assertEqual(role, "you")

    # ---- machine text that must NEVER be "you" ----
    def test_tool_result_block(self):
        content = [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]
        role, _ = app.classify_line(user_line(content))
        self.assertEqual(role, "tool-result")

    def test_tool_use_result_field(self):
        role, _ = app.classify_line(user_line(
            [{"type": "tool_result", "tool_use_id": "t", "content": "x"}], toolUseResult="stdout here"))
        self.assertEqual(role, "tool-result")

    def test_is_meta(self):
        role, _ = app.classify_line(user_line("Base directory for this skill: /x", isMeta=True))
        self.assertEqual(role, "system")

    def test_compact_summary(self):
        role, _ = app.classify_line(user_line("This session is being continued...", isCompactSummary=True))
        self.assertEqual(role, "system")

    def test_task_notification_string(self):
        role, _ = app.classify_line(user_line("<task-notification>\n<task-id>x</task-id>"))
        self.assertEqual(role, "system")

    def test_slash_command_wrapper(self):
        role, _ = app.classify_line(user_line("<command-name>/model</command-name>"))
        self.assertEqual(role, "system")

    def test_local_command_stdout(self):
        role, _ = app.classify_line(user_line("<local-command-stdout>ok</local-command-stdout>"))
        self.assertEqual(role, "system")

    def test_autonomous_loop_persona(self):
        role, _ = app.classify_line(user_line(
            "You are CLAUDE in an AUTONOMOUS turn-by-turn build loop with CODEX. ..."))
        self.assertEqual(role, "system")

    def test_loop_persona_not_substring_matched(self):
        # a human message merely MENTIONING the loop must stay human
        role, _ = app.classify_line(user_line("어제 build loop 돌린 결과 봤어?"))
        self.assertEqual(role, "you")

    def test_sidechain_user_is_not_you(self):
        role, _ = app.classify_line(user_line("You are implementing X...", isSidechain=True))
        self.assertEqual(role, "subagent")

    def test_sidechain_sub_mode_is_orchestrator(self):
        role, _ = app.classify_line(user_line("You are implementing X...", isSidechain=True), sub=True)
        self.assertEqual(role, "orchestrator")

    def test_prompt_source_system(self):
        role, _ = app.classify_line(user_line("anything", promptSource="system"))
        self.assertEqual(role, "system")

    def test_channel_message_is_not_system(self):
        # Telegram/plugin-relayed human message: harness flags it isMeta/system, but it
        # is genuine person text and must NOT land in ⓘ 시스템·주입.
        content = ('<channel source="plugin:telegram:telegram" chat_id="42" message_id="9" '
                   'user="kdr11" user_id="42" ts="2026-07-03T15:22:05.000Z">\n안녕\n</channel>')
        role, segs = app.classify_line(user_line(content, isMeta=True, promptSource="system"))
        self.assertEqual(role, "channel")
        self.assertEqual(segs, [("channel", content)])

    def test_parse_channel_and_label(self):
        content = '<channel source="plugin:telegram:telegram" user="kdr11">\n본문\n</channel>'
        attrs, body = app.parse_channel(content)
        self.assertEqual(body, "본문")
        self.assertEqual(attrs["user"], "kdr11")
        self.assertIn("Telegram", app.channel_label(attrs))
        self.assertIn("@kdr11", app.channel_label(attrs))
        self.assertIsNone(app.parse_channel("<system-reminder>hi</system-reminder>"))

    # ---- assistant ----
    def test_assistant_text_thinking_tooluse(self):
        role, segs = app.classify_line(asst_line([
            {"type": "thinking", "thinking": "hmm", "signature": "s"},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
            {"type": "text", "text": "결과입니다"},
        ]))
        self.assertEqual(role, "assistant")
        self.assertEqual([k for k, _ in segs], ["thinking", "tool_use", "text"])

    def test_api_error_banner(self):
        role, _ = app.classify_line(
            {"type": "assistant", "isApiErrorMessage": True, "message": {"content": "rate limited"}})
        self.assertEqual(role, "system")

    # ---- skip noise ----
    def test_skip_types(self):
        for t in ("mode", "attachment", "queue-operation", "file-history-snapshot", "system",
                  "ai-title", "custom-title", "last-prompt"):
            self.assertIsNone(app.classify_line({"type": t}), t)


class SummarizeAndTags(unittest.TestCase):
    def _write_session(self, lines):
        d = tempfile.mkdtemp()
        proj = os.path.join(d, "-Users-x-proj")
        os.makedirs(proj)
        p = os.path.join(proj, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            for o in lines:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
        return d, p

    def test_titles_and_counts_and_loop(self):
        _, p = self._write_session([
            {"type": "ai-title", "aiTitle": "AI가 붙인 제목"},
            {"type": "custom-title", "customTitle": "내가 붙인 제목"},
            user_line("질문", timestamp="2026-06-30T01:00:00Z"),
            asst_line([{"type": "text", "text": "답"}]),
        ])
        s = app.summarize_file(p)
        self.assertEqual(s["title"], "내가 붙인 제목")  # custom > ai
        self.assertEqual(s["n"]["you"], 1)
        self.assertEqual(s["n"]["assistant"], 1)
        self.assertFalse(s["loop"])

    def test_loop_detection(self):
        _, p = self._write_session([
            user_line("You are CLAUDE in an AUTONOMOUS turn-by-turn build loop with CODEX. go"),
            asst_line([{"type": "text", "text": "working"}]),
        ])
        s = app.summarize_file(p)
        self.assertTrue(s["loop"])
        self.assertEqual(s["n"]["you"], 0)

    def test_turn_tags_error_and_edit(self):
        o = user_line([{"type": "tool_result", "tool_use_id": "t", "content": "Traceback (most recent call last)"}])
        r = app.classify_line(o)
        tags = app.turn_tags(o, r[0], r[1])
        self.assertIn("error", tags)
        o2 = asst_line([{"type": "tool_use", "id": "t", "name": "Edit",
                         "input": {"file_path": "/x/y.py", "old_string": "a", "new_string": "b"}}])
        r2 = app.classify_line(o2)
        self.assertIn("edit", app.turn_tags(o2, r2[0], r2[1]))

    def test_get_index_incremental_refresh(self):
        d, p = self._write_session([user_line("첫 질문")])
        app.configure(d)
        items = app.get_index(d)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["n"]["you"], 1)
        # append a new line -> index must pick it up without restart
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(user_line("둘째 질문"), ensure_ascii=False) + "\n")
        items = app.get_index(d)
        self.assertEqual(items[0]["n"]["you"], 2)


class Cli(unittest.TestCase):
    def test_nonexistent_root_exits_2_not_silent_fallback(self):
        with self.assertRaises(SystemExit) as cm:
            app.main(["/definitely-not-a-real-dir-xyz"])
        self.assertEqual(cm.exception.code, 2)

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as cm:
            app.main(["--version"])
        self.assertEqual(cm.exception.code, 0)


class Helpers(unittest.TestCase):
    def test_fmt_size(self):
        self.assertEqual(app.fmt_size(512), "512B")
        self.assertEqual(app.fmt_size(2048), "2.0KB")
        self.assertEqual(app.fmt_size(44 * 1024 * 1024), "44.0MB")

    def test_normalize_root_variants(self):
        d = tempfile.mkdtemp()
        proj = os.path.join(d, ".claude", "projects", "-Users-x")
        os.makedirs(proj)
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        expect = os.path.join(d, ".claude", "projects")
        self.assertEqual(app.normalize_root(d), expect)                    # parent of .claude
        self.assertEqual(app.normalize_root(os.path.join(d, ".claude")), expect)
        self.assertEqual(app.normalize_root(expect), expect)               # projects dir itself
        self.assertIsNone(app.normalize_root("/nonexistent-xyz"))

    def test_root_containment(self):
        d = tempfile.mkdtemp()
        proj = os.path.join(d, "-p")
        os.makedirs(proj)
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        app.configure(d)
        self.assertEqual(app.root_for_path(os.path.join(proj, "s.jsonl")), d)
        self.assertIsNone(app.root_for_path("/etc/passwd"))

    def test_esc(self):
        self.assertEqual(app.esc('<a b="c">'), "&lt;a b=&quot;c&quot;&gt;")

    def test_parse_query(self):
        self.assertEqual(app.parse_query('foo bar "exact phrase"'), ["foo", "bar", "exact phrase"])
        self.assertEqual(app.parse_query("“한글 구문” 단어"), ["한글 구문", "단어"])
        self.assertEqual(app.parse_query("  "), [])

    def test_active_roots_multi_select(self):
        import tempfile
        r1 = tempfile.mkdtemp(); os.makedirs(os.path.join(r1, "-a"))
        r2 = tempfile.mkdtemp(); os.makedirs(os.path.join(r2, "-b"))
        app.configure(r1, [r2])
        app.ROOTS[:] = [r1, r2]; app.ROOT = r1   # pin: configure() also discovers real roots
        self.assertEqual(app.active_roots(None), [r1, r2])          # no param → all
        self.assertEqual(app.active_roots(""), [r1, r2])
        self.assertEqual(app.active_roots("*"), [r1, r2])
        self.assertEqual(app.active_roots(r2), [r2])                 # single (back-compat)
        self.assertEqual(app.active_roots(f"{r2},{r1}"), [r1, r2])   # comma list, ROOTS order
        self.assertEqual(app.active_roots("/bogus-xyz"), [r1, r2])   # unknown → all
        self.assertEqual(app.root_param([r1, r2]), "")               # all → no param
        self.assertEqual(app.root_param([r1]), r1)

    def test_rootbar_has_all_chip_and_toggle_links(self):
        import tempfile
        import urllib.parse
        r1 = tempfile.mkdtemp(); os.makedirs(os.path.join(r1, "-a"))
        r2 = tempfile.mkdtemp(); os.makedirs(os.path.join(r2, "-b"))
        r3 = tempfile.mkdtemp(); os.makedirs(os.path.join(r3, "-c"))
        app.configure(r1, [r2, r3])
        app.ROOTS[:] = [r1, r2, r3]; app.ROOT = r1   # pin: configure() also discovers real roots
        html = app.shell("t", "body", root="")               # All selected
        self.assertIn("🗂", html)                            # the All chip
        # a subset selection renders another folder as an "add" link (comma list)…
        html = app.shell("t", "body", root=r1)
        self.assertIn(urllib.parse.quote(f"{r1},{r2}"), html)
        # …and adding the last missing folder collapses back to All (no root param)
        html = app.shell("t", "body", root=f"{r1},{r2}")
        self.assertNotIn(urllib.parse.quote(f"{r1},{r2},{r3}"), html)

    def test_search_folder_link_preserves_query(self):
        import tempfile
        r1 = tempfile.mkdtemp(); os.makedirs(os.path.join(r1, "-a"))
        r2 = tempfile.mkdtemp(); os.makedirs(os.path.join(r2, "-b"))
        app.configure(r1, [r2])                       # >1 root → folder switcher shown
        html = app.shell("t", "body", q="hello world", scope="claude", root=r1)
        self.assertIn("/search?", html)              # folder links keep the search
        self.assertIn("q=hello", html)
        self.assertIn("scope=claude", html)

    def test_adjacent_sessions(self):
        import tempfile
        root = tempfile.mkdtemp()
        proj = os.path.join(root, "-p")
        os.makedirs(proj)
        paths = []
        for i in range(3):
            p = os.path.join(proj, f"{i:08d}-0000-0000-0000-000000000000.jsonl")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "ai-title", "aiTitle": f"S{i}"}) + "\n")
                fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")
            os.utime(p, (1000 + i, 1000 + i))       # chronological by mtime
            paths.append(p)
        app.configure(root)
        prev, nxt = app.adjacent_sessions(root, paths[1])
        self.assertEqual(prev["path"], paths[0])
        self.assertEqual(nxt["path"], paths[2])
        prev0, nxt0 = app.adjacent_sessions(root, paths[0])
        self.assertIsNone(prev0)
        self.assertEqual(nxt0["path"], paths[1])

    def test_parse_search_query(self):
        sq = app.parse_search_query('file:app.py -flaky "exact one" foo')
        self.assertEqual(sq["terms"], ["foo"])
        self.assertEqual(sq["phrases"], ["exact one"])
        self.assertEqual(sq["fields"], {"file": ["app.py"]})
        self.assertEqual(sq["neg"], ["flaky"])
        # unknown field prefix (URL) stays a plain term
        self.assertIn("http://x.com/a", app.parse_search_query("http://x.com/a")["terms"])
        self.assertEqual(app.parse_search_query("cmd:pytest role:me")["fields"],
                         {"cmd": ["pytest"], "role": ["me"]})

    def test_best_window_proximity(self):
        # term A at turns [2], term B at turns [5, 30] → smallest window spans 2..5 (=3)
        span, gis = app._best_window({"a": [2], "b": [5, 30]}, ["a", "b"])
        self.assertEqual(span, 3)
        self.assertEqual(gis, [2, 5])

    def test_search_rows_include_code_body(self):
        turns = app.classify_turns  # sanity: build rows from a Write with content
        import tempfile
        lines = [{"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "w", "name": "Write",
             "input": {"file_path": "/a.py", "content": "def ZZNEEDLE(): pass"}}]}}]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            for o in lines:
                fh.write(json.dumps(o) + "\n")
            path = fh.name
        try:
            rows = app.search_rows(path)
            code = [r for r in rows if r["kind"] & app.K_CODE]
            self.assertTrue(any("ZZNEEDLE" in r["text"] for r in code))
            # back-compat search_turns EXCLUDES code rows (preserves old default corpus)
            self.assertFalse(any("ZZNEEDLE" in txt for _, _, txt in app.search_turns(path)))
        finally:
            os.unlink(path)

    def test_i18n(self):
        app.load_locales()
        self.assertIn("ko", app.available_langs())        # shipped Korean locale loads
        app.set_lang("en")
        self.assertEqual(app.tr("Search"), "Search")      # English is the identity/base
        self.assertEqual(app.tr("__no_such_key__"), "__no_such_key__")
        app.set_lang("ko")
        self.assertEqual(app.tr("Search"), "검색")         # translated
        self.assertEqual(app.tr("Tokens"), "토큰")
        self.assertEqual(app.tr("__no_such_key__"), "__no_such_key__")  # missing → English fallback
        app.set_lang("zz")                                # unknown code → English
        self.assertEqual(app.cur_lang(), "en")
        self.assertEqual(app.tr("Search"), "Search")
        app.set_lang("en")

    def test_hl_multi_color(self):
        out = app.hl("foo and bar", "foo bar")
        self.assertIn('<mark class="hl0">foo</mark>', out)   # term 0 → color 0
        self.assertIn('<mark class="hl1">bar</mark>', out)   # term 1 → color 1
        # overlapping terms merge instead of double-wrapping
        out = app.hl("abcd", "abc bcd")
        self.assertEqual(out, '<mark class="hl0">abcd</mark>')

    def test_word_re(self):
        self.assertTrue(app.word_re("oss").search("this is OSS software"))
        self.assertIsNone(app.word_re("oss").search("OSSEAN ossea"))   # substring only → no whole-word match
        self.assertTrue(app.word_re("open source").search("free/open source stuff"))

    def test_date_ts(self):
        self.assertIsNone(app._date_ts(""))
        self.assertIsNone(app._date_ts("not-a-date"))
        a = app._date_ts("2026-07-01")
        b = app._date_ts("2026-07-01", end=True)
        self.assertAlmostEqual(b - a, 86400, delta=3700)   # ~1 day (DST tolerance)

    def test_token_helpers(self):
        self.assertEqual(app.fmt_tok(842), "842")
        self.assertEqual(app.fmt_tok(2500), "2.5k")
        self.assertEqual(app.fmt_tok(2_186_900), "2.2M")
        self.assertEqual(app.model_short("claude-opus-4-8"), "Opus 4.8")
        self.assertEqual(app.model_short("claude-sonnet-4-6"), "Sonnet 4.6")
        self.assertEqual(app.model_short("<synthetic>"), "")     # skipped
        u = app.usage_tok({"input_tokens": 10, "output_tokens": 5,
                           "cache_creation_input_tokens": 2, "cache_read_input_tokens": 99})
        self.assertEqual(u, {"in": 10, "out": 5, "cw": 2, "cr": 99})
        self.assertIsNone(app.usage_tok({"input_tokens": 0}))     # all-zero → None

    def test_summarize_tokens_and_models(self):
        import tempfile
        lines = [
            {"type": "user", "message": {"role": "user", "content": "hi"}},
            {"type": "assistant", "message": {"role": "assistant", "model": "claude-opus-4-8",
                "usage": {"input_tokens": 100, "output_tokens": 50,
                          "cache_creation_input_tokens": 10, "cache_read_input_tokens": 900},
                "content": [{"type": "text", "text": "a"}]}},
            {"type": "assistant", "message": {"role": "assistant", "model": "claude-fable-5",
                "usage": {"input_tokens": 20, "output_tokens": 8,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100},
                "content": [{"type": "text", "text": "b"}]}},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            for o in lines:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
            path = fh.name
        try:
            s = app.summarize_file(path)
            self.assertEqual(s["tok"], {"in": 120, "out": 58, "cw": 10, "cr": 1000})
            self.assertEqual(s["models"], {"claude-opus-4-8": 1, "claude-fable-5": 1})
        finally:
            os.unlink(path)

    def test_looks_ref(self):
        self.assertTrue(app._looks_ref("40b92137-2ff9-4461-90c3-21729c2b3bee"))
        self.assertTrue(app._looks_ref("606730d3"))        # hex fragment
        self.assertFalse(app._looks_ref("commit"))         # normal word
        self.assertFalse(app._looks_ref("abc"))            # too short

    def test_summarize_captures_workspace_launchdir_and_fork(self):
        import tempfile
        lines = [
            {"type": "user", "cwd": "/a/launch", "gitBranch": "main",
             "forkedFrom": {"sessionId": "aaaa1111-bbbb-2222-cccc-333344445555", "messageUuid": "m"},
             "message": {"role": "user", "content": "hi"}, "timestamp": "2026-07-05T00:00:00Z"},
            {"type": "assistant", "cwd": "/a/work",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            for o in lines:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
            path = fh.name
        try:
            s = app.summarize_file(path)
            self.assertEqual(s["cwd"], "/a/work")          # last cwd = current workspace
            self.assertEqual(s["start_cwd"], "/a/launch")  # first cwd = launch dir
            self.assertEqual(s["forked"], "aaaa1111-bbbb-2222-cccc-333344445555")
        finally:
            os.unlink(path)


class Codex(unittest.TestCase):
    def _msg(self, role, text, ptype="message"):
        return {"type": "response_item", "timestamp": "2026-03-24T00:00:00Z",
                "payload": {"type": ptype, "role": role,
                            "content": [{"type": "input_text", "text": text}]}}

    def test_provider_detection(self):
        self.assertEqual(app.provider_of("/Users/x/.codex/sessions/2026/03/24/rollout-a-019c.jsonl"), "codex")
        self.assertEqual(app.provider_of("/Users/x/.claude/projects/-p/uuid.jsonl"), "claude")
        self.assertTrue(app.is_codex_root("/Users/x/.codex/sessions"))
        self.assertEqual(app._codex_sid("rollout-2026-03-24T20-53-57-019d1fb1-c72f-74e1-8a6b-37ff9c7386ad.jsonl"),
                         "019d1fb1-c72f-74e1-8a6b-37ff9c7386ad")

    def test_codex_attribution(self):
        # genuine human
        self.assertEqual(app.classify_codex_line(self._msg("user", "how do I resize windows?"))[0], "you")
        # injected user context must NOT be human
        self.assertEqual(app.classify_codex_line(self._msg("user", "# Context from my IDE setup:\n..."))[0], "system")
        self.assertEqual(app.classify_codex_line(self._msg("user", "<environment_context>\n<cwd>/x</cwd>"))[0], "system")
        self.assertEqual(app.classify_codex_line(self._msg("developer", "instructions"))[0], "system")
        self.assertEqual(app.classify_codex_line(self._msg("assistant", "here you go"))[0], "assistant")

    def test_codex_tools_and_reasoning(self):
        fc = {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
              "arguments": '{"cmd":"pwd"}', "call_id": "c1"}}
        r = app.classify_codex_line(fc)
        self.assertEqual(r[0], "assistant")
        self.assertEqual(r[1][0][0], "tool_use")
        self.assertIn("exec_command", r[1][0][1])
        fo = {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": "ok"}}
        self.assertEqual(app.classify_codex_line(fo)[0], "tool-result")
        rs = {"type": "response_item", "payload": {"type": "reasoning",
              "summary": [{"type": "summary_text", "text": "thinking..."}]}}
        self.assertEqual(app.classify_codex_line(rs)[1][0][0], "thinking")
        # event_msg mirrors are ignored (no double-counting)
        self.assertIsNone(app.classify_codex_line({"type": "event_msg", "payload": {"type": "agent_message", "message": "x"}}))

    def test_codex_load_meta(self):
        import tempfile
        lines = [
            {"type": "session_meta", "payload": {"id": "019c8b6e-2595-7111-aaaa-bbbbccccdddd",
             "cwd": "/Users/x/dev/proj", "model_provider": "openai"}},
            {"type": "turn_context", "payload": {"model": "gpt-5.3-codex"}},
            self._msg("user", "what does this do?"),
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "it does X"}]}},
        ]
        d = tempfile.mkdtemp()
        p = os.path.join(d, "rollout-2026-02-24T01-56-17-019c8b6e-2595-7111-aaaa-bbbbccccdddd.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            for o in lines:
                fh.write(json.dumps(o) + "\n")
        m = app.summarize_file(p)
        self.assertEqual(m["cwd"], "/Users/x/dev/proj")
        self.assertEqual(m["title"], "what does this do?")
        self.assertEqual(m["models"], {"gpt-5.3-codex": 1})
        self.assertEqual(m["n"]["you"], 1)
        self.assertEqual(m["n"]["assistant"], 1)


class Gemini(unittest.TestCase):
    def test_provider_detection(self):
        self.assertEqual(app.provider_of("/Users/x/.gemini/tmp/proj/chats/session-2026-04-30T05-15-405ac996.jsonl"), "gemini")
        self.assertTrue(app.is_gemini_root("/Users/x/.gemini/tmp"))

    def test_gemini_classify(self):
        self.assertEqual(app.classify_gemini_line({"type": "user", "content": [{"text": "check git"}]})[0], "you")
        self.assertEqual(app.classify_gemini_line({"type": "info", "content": "Request cancelled."})[0], "system")
        g = {"type": "gemini", "content": "done", "model": "gemini-3-flash-preview",
             "thoughts": [{"subject": "Plan", "description": "think"}],
             "toolCalls": [{"name": "run_shell_command", "args": {"command": "git status"},
                            "result": [{"functionResponse": {"response": {"output": "on branch main"}}}]}]}
        role, segs = app.classify_gemini_line(g)
        self.assertEqual(role, "assistant")
        kinds = [k for k, _ in segs]
        self.assertEqual(kinds, ["thinking", "text", "tool_use", "tool_result"])   # tool result is embedded
        self.assertIn("on branch main", dict((k, v) for k, v in [(s[0], s[1]) for s in segs])["tool_result"])

    def test_gemini_load_meta_and_tokens(self):
        import tempfile
        lines = [
            {"sessionId": "405ac996-4058-4604-9f22-67ab43e46735", "kind": "main", "startTime": "2026-04-30T05:15:11Z"},
            {"type": "user", "content": [{"text": "please check git"}], "timestamp": "2026-04-30T05:19:40Z"},
            {"type": "gemini", "content": "ok", "model": "gemini-3-flash-preview",
             "tokens": {"input": 100, "output": 20, "cached": 5}},
        ]
        d = tempfile.mkdtemp()
        cdir = os.path.join(d, "myproj", "chats")
        os.makedirs(cdir)
        p = os.path.join(cdir, "session-2026-04-30T05-15-405ac996.jsonl")
        with open(p, "w", encoding="utf-8") as fh:
            for o in lines:
                fh.write(json.dumps(o) + "\n")
        m = app.summarize_file(p)
        self.assertEqual(m["title"], "please check git")
        self.assertEqual(m["models"], {"gemini-3-flash-preview": 1})
        self.assertEqual(m["tok"], {"in": 100, "out": 20, "cw": 0, "cr": 5})   # Gemini records tokens
        self.assertEqual(app._gemini_sid(p), "405ac996-4058-4604-9f22-67ab43e46735")


class Markdown(unittest.TestCase):
    def test_table_renders_with_alignment(self):
        md = "| A | B |\n|:--|--:|\n| 1 | 2 |"
        h = app.md_to_html(md)
        self.assertIn("<table", h)
        self.assertIn("<th", h)
        self.assertIn('style="text-align:right"', h)
        self.assertIn("<td", h)

    def test_raw_html_is_escaped_not_executed(self):
        h = app.md_to_html("hi <script>alert(1)</script> **bold**")
        self.assertIn("&lt;script&gt;", h)
        self.assertNotIn("<script>", h)
        self.assertIn("<strong>bold</strong>", h)

    def test_snake_case_survives_underscore_emphasis(self):
        h = app.md_to_html("call some_long_name here")
        self.assertIn("some_long_name", h)
        self.assertNotIn("<em>", h)

    def test_fenced_code_block(self):
        h = app.md_to_html("```python\nx = a < b\n```")
        self.assertIn('<pre class="md-code">', h)
        self.assertIn("a &lt; b", h)          # escaped inside code
        self.assertIn("python", h)            # language label

    def test_inline_code_and_link(self):
        h = app.md_to_html("see `foo()` at [docs](https://x.com)")
        self.assertIn('<code class="md-ic">foo()</code>', h)
        self.assertIn('href="https://x.com"', h)

    def test_nested_list(self):
        h = app.md_to_html("- a\n  - b\n- c")
        self.assertEqual(h.count("<ul"), 2)   # one nested

    def test_highlight_only_in_text_nodes(self):
        h = app.md_html("a **table** row", "table")
        self.assertIn('<mark class="hl0">table</mark>', h)
        # the tag/attribute stream must stay intact (no mark injected into a tag)
        self.assertIn("<strong>", h)
        self.assertNotIn("<st<mark", h)

    def test_md_html_falls_back_on_error(self):
        # md_html must never raise — worst case returns escaped+highlighted text
        self.assertIsInstance(app.md_html("plain text", ""), str)


class ToolRender(unittest.TestCase):
    def test_bash_use_shows_command_and_desc(self):
        txt = 'Bash\n{"command": "git commit -m x", "description": "commit it"}'
        h = app.tool_use_html(txt)
        self.assertIn('class="tk-cmd"', h)
        self.assertIn("git commit -m x", h)
        self.assertIn("commit it", h)
        name, prev = app._tool_use_summary(txt)
        self.assertEqual(name, "Bash")
        self.assertEqual(prev, "git commit -m x")

    def test_edit_use_shows_diff(self):
        txt = 'Edit\n{"file_path": "/a/b.py", "old_string": "foo\\nx", "new_string": "bar\\nx"}'
        h = app.tool_use_html(txt)
        self.assertIn("tk-diff", h)
        self.assertIn("d-del", h)
        self.assertIn("d-add", h)
        self.assertIn("b.py", h)

    def test_edit_result_structuredpatch_becomes_diff(self):
        txt = json.dumps({
            "filePath": "/a/b.md", "oldString": "x", "newString": "x\ny",
            "structuredPatch": [{"oldStart": 1, "oldLines": 1, "newStart": 1, "newLines": 2,
                                 "lines": [" x", "+y"]}],
            "userModified": False,
        }, ensure_ascii=False, indent=2)
        h = app.tool_result_html(txt)
        self.assertIn('class="tk-diff"', h)
        self.assertIn("d-hunk", h)
        self.assertIn("d-add", h)
        self.assertIn("b.md", h)
        self.assertNotIn("structuredPatch", h)     # raw JSON envelope must be gone

    def test_multiedit_use_renders_each_hunk(self):
        txt = 'MultiEdit\n' + json.dumps({"file_path": "/a/c.py", "edits": [
            {"old_string": "a", "new_string": "b"}, {"old_string": "x", "new_string": "y"}]})
        self.assertEqual(app.tool_use_html(txt).count("tk-diff"), 2)

    def test_tool_use_search_text_indexes_args_not_json_keys(self):
        txt = ('Bash\n' + json.dumps(
            {"command": "git commit -m zzq", "description": "do it", "run_in_background": False}))
        s = app._tool_use_search_text(txt)
        self.assertIn("Bash", s)
        self.assertIn("git commit -m zzq", s)     # command is findable
        self.assertIn("do it", s)                  # description too
        self.assertNotIn("run_in_background", s)   # raw JSON keys are NOT indexed
        # Edit → file path findable; big blobs excluded
        edit = 'Edit\n' + json.dumps({"file_path": "/a/uniquename.py",
                                       "old_string": "SECRETBLOB", "new_string": "SECRETBLOB2"})
        se = app._tool_use_search_text(edit)
        self.assertIn("/a/uniquename.py", se)
        self.assertNotIn("SECRETBLOB", se)         # content blob left to the tool_result diff

    def test_search_turns_finds_bash_command(self):
        import tempfile
        session = [
            {"type": "user", "message": {"role": "user", "content": "커밋해줘"},
             "timestamp": "2026-07-05T00:00:00Z"},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": "git commit -m zzquniquecmd", "description": "commit"}}]},
             "timestamp": "2026-07-05T00:00:01Z"},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            for o in session:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
            path = fh.name
        try:
            rows = app.search_turns(path)
            blob = " ".join(txt for _, _, txt in rows)
            self.assertIn("zzquniquecmd", blob)     # command now in the search corpus
        finally:
            os.unlink(path)

    def test_bash_result_splits_stdout_stderr(self):
        txt = json.dumps({"stdout": "done", "stderr": "\noops", "interrupted": False},
                         ensure_ascii=False, indent=2)
        h = app.tool_result_html(txt)
        self.assertIn("done", h)
        self.assertIn("stderr", h)
        self.assertIn("oops", h)

    def test_plain_string_result(self):
        self.assertIn("hello world", app.tool_result_html("hello world"))

    def test_unparseable_tool_use_does_not_crash(self):
        h = app.tool_use_html("Weird\nnot json {")
        self.assertIn("not json", h)

    def _turn(self, role, segs):
        return {"role": role, "segs": segs, "ts": "", "tags": set()}

    def test_bash_call_and_result_open_by_default(self):
        use = app.render_turn(0, self._turn("assistant", [("tool_use", 'Bash\n{"command":"ls"}')]))
        self.assertIn('<details class="fold" open>', use)
        res = app.render_turn(1, self._turn("tool-result", [("tool_result", '{"stdout":"x","stderr":""}')]))
        self.assertIn('<details class="fold" open>', res)
        self.assertIn("Run result", res)

    def test_edit_call_opens_but_edit_result_stays_folded(self):
        use = app.render_turn(0, self._turn("assistant",
            [("tool_use", 'Edit\n{"file_path":"/a.py","old_string":"a\\nb","new_string":"a\\nc"}')]))
        self.assertIn('<details class="fold" open>', use)     # the diff opens
        result_json = json.dumps({"filePath": "/a.py", "structuredPatch": [
            {"oldStart": 1, "oldLines": 2, "newStart": 1, "newLines": 2, "lines": [" a", "-b", "+c"]}]})
        res = app.render_turn(1, self._turn("tool-result", [("tool_result", result_json)]))
        self.assertNotIn(' open>', res)                       # paired result folded
        self.assertIn("Edit result", res)

    def test_thinking_stays_folded(self):
        h = app.render_turn(0, self._turn("assistant", [("thinking", "some reasoning")]))
        self.assertIn("<details class=fold>", h)
        self.assertNotIn(" open>", h)


if __name__ == "__main__":
    unittest.main()
