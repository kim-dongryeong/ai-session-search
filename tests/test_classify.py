"""Attribution ruleset regression tests — the core guarantee of claude-viewer:
nothing machine-authored may ever be classified as the human ("you")."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from claude_viewer import app  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
