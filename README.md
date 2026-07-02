# claude-viewer

A **read-only, stdlib-only** local web viewer for browsing **Claude Code** session
transcripts (the JSONL files under `~/.claude/projects/`). No dependencies, no build
step, no database — just Python ≥ 3.10.

It exists to answer one question reliably: **who actually said what?** In Claude Code's
transcript format, ~95% of `type:"user"` lines are *not* the human — they are tool
results, system reminders, IDE notices, slash-command output, task-notifications,
autonomous-loop prompts, or subagent briefs. This viewer uses an empirically audited +
adversarially verified ruleset so only genuinely human-typed text is labelled **🧑 나
(You)**; everything else gets its own category, folded by default.

## Install & run

**Run from a checkout (no install):**

```bash
python3 claude-viewer.py                 # compatibility shim at the repo root
# or
python3 -m claude_viewer                 # with src/ on PYTHONPATH
```

**Install as a command (pipx / uv / pip):**

```bash
pipx install git+ssh://git@github.com/kim-dongryeong/claude-viewer.git
# or: uvx --from git+ssh://git@github.com/kim-dongryeong/claude-viewer.git claude-viewer
# or: pip install .

claude-viewer                            # browse ~/.claude/projects
claude-viewer ~/Downloads/.claude/projects --port 8778 --open
claude-viewer --version
```

**macOS app:** `./scripts/make-macos-app.sh` builds `dist/Claude Viewer.app` (icon in
Dock/Finder, double-click, no lingering terminal); add `--dmg` for a draggable
`dist/claude-viewer.dmg`. It doesn't bundle Python — it just launches the installed
`claude-viewer`. Or use the plain `claude-viewer.command` (starts server + opens browser).

### Which distribution form?

| Form | Command | When |
|---|---|---|
| **pipx / uvx** (recommended) | `pipx install git+ssh://…/claude-viewer.git` | Any OS. One command, `pipx upgrade` to update. Target already has Python + git. |
| **macOS .app / .dmg** | `./scripts/make-macos-app.sh --dmg` | Want a Dock icon + double-click on a Mac. Thin wrapper over the installed CLI. |
| **`.command` double-click** | ship `claude-viewer.py` + `.command` | Zero-build, copy the folder. |

A `.dmg` here is just the thin `.app` (≈90 KB) — it is **not** a self-contained binary,
because every machine that has Claude Code transcripts already has Python. A full
PyInstaller/py2app bundle (to run without Python) is intentionally avoided: it needs
per-OS builds and macOS code-signing/notarization for a tool that only opens a local
`127.0.0.1` page.

Defaults: binds `127.0.0.1` only (never exposed to the network; `--host` warns if you
change it), reads `$CLAUDE_CONFIG_DIR/projects` or `~/.claude/projects`, and
auto-discovers `~/Downloads/.claude/projects` (copied-from-another-machine data) in the
in-app **📁 folder switcher**. Add any other folder at runtime by pasting its path
(persisted in `~/.config/claude-viewer/roots.txt`), remove with ✕. Strictly read-only —
it never writes to your transcripts.

## Features

- **Correct attribution** — 🧑 나 / ✦ Claude / 💭 추론 / 🔧 도구 호출 / ⚙ 도구 결과 /
  ⓘ 시스템·주입 / 📋 지시 / 🤖 서브에이전트; tooltips + an in-app legend (❓) explain
  each; technical blocks folded by default.
- **Index** — real titles (`ai-title`/`custom-title`), project filter (by real `cwd`),
  sort by 날짜/내 메시지/제목/용량 with direction toggle, per-session counts,
  **session-id** per row, **🔁 자율 빌드루프 chips** for autonomous-loop sessions.
- **Per-project stats** — sessions, my-participated sessions, my message count, total
  size, my-session size, loop count; overview table + per-folder detail card.
- **Full-text search** across all sessions, scope 전체 ↔ 내 말만, highlighted snippets.
- **Session view** — per-message timestamps, 🧑 내 말만 filter, **답변 스레드** links,
  page size 100…10000/전체 with render timing, `session-id` + `claude --resume` line,
  dark mode.
- **Event/error chips** — ⚠️ 에러 / ✏️ 편집 / ❯ 명령 / ⎇ 커밋 / 🧪 테스트 / 🔗 URL filters.
- **Structure minimap** — right-edge rail (you/error/edit/command density), click to jump.
- **Extracted-fact digest** — files touched, commands, tests, commits, PR links.
  Deterministic, no LLM.
- **Code/diff extraction** (`🧩 코드만`) — all generated code blocks + file edits with
  one-click copy.
- **Subagent threads** — sidechain/Task transcripts (incl. workflow agents) listed per
  session and openable, orchestrator briefs clearly labelled 📋 (never "you").

## Keyboard

- `/` focus search · `Esc` blur
- `j` / `k` (or `n` / `p`) jump between **my** messages · `Enter` open that question's
  answer thread

## Development

```bash
python3 -m unittest discover -s tests -v   # 33 tests: attribution regression, HTTP smoke
```

CI runs the suite on Ubuntu/macOS/Windows × Python 3.10/3.14, then installs the package
and checks the `claude-viewer` entry point. The attribution tests are the contract:
**no machine-authored line may ever be classified as 🧑 나.**

Layout: the whole app is one module (`src/claude_viewer/app.py`) by design — stdlib
only, no framework. `claude-viewer.py` at the repo root is a thin shim for
`python3 claude-viewer.py` muscle memory.

## How attribution works

See `classify_line` in `src/claude_viewer/app.py`. A genuine human message is a
`type:"user"` line that is **not** a tool result (`toolUseResult`/`tool_result` block),
**not** `isMeta`/`isCompactSummary`/`promptSource==system`, **not** a
`<task-notification>`/`<command-*>`/`<system-reminder>`/`Caveat:` wrapper, **not** an
autonomous build-loop persona (start-anchored match), and **not** `isSidechain`.
Co-located `<ide_opened_file>`/`<system-reminder>` blocks are folded away so the human's
actual text still renders.

## Non-goals

No embeddings/semantic search, no LLM summarization, no heavy client-side syntax
highlighters (they freeze on 20k-line sessions), no database. Bookmarks/aliases, if
added, will use `localStorage` only.
