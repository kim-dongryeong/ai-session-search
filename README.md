# claude-viewer

A **read-only, single-file, stdlib-only** local web viewer for browsing **Claude Code**
session transcripts (the JSONL files under `~/.claude/projects/`). No dependencies, no
build step, no database — just `python3`.

It exists to answer one question reliably: **who actually said what?** In Claude Code's
transcript format, ~95% of `type:"user"` lines are *not* the human — they are tool
results, system reminders, IDE notices, slash-command output, task-notifications,
autonomous-loop prompts, or subagent briefs. This viewer uses an empirically audited +
adversarially verified ruleset so only genuinely human-typed text is labelled **🧑 나
(You)**; everything else gets its own category, folded by default.

## Run

```bash
python3 claude-viewer.py [PROJECTS_DIR] [--port 8777]
```

- No argument → defaults to `~/Downloads/.claude/projects`.
- On macOS you can just **double-click `claude-viewer.command`** (opens Terminal + browser).
- Binds to `127.0.0.1` only — never exposed to the network. Read-only; it never writes
  to your transcripts.

The app auto-discovers known roots (`~/.claude/projects` and
`~/Downloads/.claude/projects`) and lets you **switch between them in-app** (folder bar at
the top). Add more with `--roots=/path/a,/path/b`.

## Features

- **Correct attribution** — 🧑 나 / ✦ Claude / 💭 추론 / 🔧 도구 호출 / ⚙ 도구 결과 /
  ⓘ 시스템·주입 / 📋 지시 / 🤖 서브에이전트, each distinct; technical blocks folded.
- **Index** — real titles (from `ai-title`/`custom-title`), project filter (by real `cwd`),
  sort by **날짜 / 내 메시지 수 / 제목 / 용량** with **direction toggle**, per-session
  counts (hover for tooltips), and **session-id** per row.
- **Full-text search** across all sessions, scope **전체 ↔ 내 말만**, highlighted snippets.
- **Session view** — per-message timestamps; **🧑 내 말만** filter; **답변 스레드** links
  (a question + the replies up to the next question); configurable **page size**
  (100…10000 / 전체) with server+browser render timing; dark mode.
- **Event/error chips** — filter to ⚠️ 에러 / ✏️ 편집 / ❯ 명령 / ⎇ 커밋 / 🧪 테스트 / 🔗 URL.
- **Structure minimap** — right-edge rail visualizing message/error/edit density; click to jump.
- **Session digest** — extracted facts (files touched, commands, tests, commits, PR links)
  to decide *is this the right session?* before reading. Deterministic, no LLM.
- **Code/diff extraction** (`🧩 코드만`) — collect generated code blocks + file edits with
  one-click copy.
- **Subagent threads** — sidechain/Task transcripts listed per session and openable.
- **session-id + `claude --resume <id>`** shown on each session.

## Keyboard

- `/` focus search · `Esc` blur
- `j` / `k` (or `n` / `p`) jump between **my** messages · `Enter` open that question's answer thread

## How attribution works

See `docs/` and the inline ruleset in `claude-viewer.py` (`classify_line`). A genuine
human message is a `type:"user"` line that is **not** a tool result (`toolUseResult` /
`tool_result` block), **not** `isMeta`/`isCompactSummary`/`promptSource==system`, **not**
a `<task-notification>`/`<command-*>`/`<system-reminder>`/`Caveat:` wrapper, **not** an
autonomous build-loop persona, and **not** `isSidechain`. Co-located `<ide_opened_file>` /
`<system-reminder>` blocks are folded away so the human's actual text still renders.

## Notes / non-goals

By design this stays a single stdlib file. No embeddings/semantic search, no LLM
summarization, no heavy client-side syntax highlighters (they freeze on 20k-line
sessions). Bookmarks/aliases, if added, use `localStorage` only.
