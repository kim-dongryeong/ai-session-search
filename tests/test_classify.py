"""Attribution ruleset regression tests — the core guarantee of claude-code-history:
nothing machine-authored may ever be classified as the human ("you")."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from claude_code_history import app  # noqa: E402


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
        self.assertIn("실행 결과", res)

    def test_edit_call_opens_but_edit_result_stays_folded(self):
        use = app.render_turn(0, self._turn("assistant",
            [("tool_use", 'Edit\n{"file_path":"/a.py","old_string":"a\\nb","new_string":"a\\nc"}')]))
        self.assertIn('<details class="fold" open>', use)     # the diff opens
        result_json = json.dumps({"filePath": "/a.py", "structuredPatch": [
            {"oldStart": 1, "oldLines": 2, "newStart": 1, "newLines": 2, "lines": [" a", "-b", "+c"]}]})
        res = app.render_turn(1, self._turn("tool-result", [("tool_result", result_json)]))
        self.assertNotIn(' open>', res)                       # paired result folded
        self.assertIn("편집 결과", res)

    def test_thinking_stays_folded(self):
        h = app.render_turn(0, self._turn("assistant", [("thinking", "some reasoning")]))
        self.assertIn("<details class=fold>", h)
        self.assertNotIn(" open>", h)


if __name__ == "__main__":
    unittest.main()
