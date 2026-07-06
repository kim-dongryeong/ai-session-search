# claude-code-history  (`cch`)

A **read-only, stdlib-only** local web viewer for browsing and searching your **Claude
Code**, **Codex**, and **Gemini CLI** session transcripts (the JSONL under
`~/.claude/projects/`, `~/.codex/sessions/`, and `~/.gemini/tmp/`). No dependencies, no
build step, no database — just Python ≥ 3.9.

It exists to answer one question reliably: **who actually said what?** In both agents'
transcript formats, most `role:"user"` lines are *not* the human — they are tool
results, system reminders, IDE/environment context, slash-command output,
task-notifications, agent-history, autonomous-loop prompts, or subagent briefs. This
viewer uses an empirically audited + adversarially verified ruleset (per provider) so
only genuinely human-typed text is labelled **🧑 You**; everything else gets its own
category, folded by default.

## Download (no Python needed)

Grab a double-click bundle from the [**latest release**](https://github.com/kim-dongryeong/claude-code-history/releases/latest) — it starts the local server and opens the app in your browser. Nothing is uploaded; it reads your transcripts on your machine.

| OS | File | Notes |
|---|---|---|
| macOS (Apple Silicon) | `…-macos-arm64.dmg` | open the dmg, drag to Applications |
| macOS (Intel) | `…-macos-x86_64.dmg` | |
| Windows | `…-windows-x64.zip` | unzip, run `claude-code-history.exe` |
| Linux | `…-linux-x86_64.tar.gz` | `tar xzf …`, run `./claude-code-history` |

> Unsigned builds trip Gatekeeper/SmartScreen: on macOS right-click → **Open** the first time; on Windows click **More info → Run anyway**. (Signed/notarized macOS builds ship once the signing cert is configured.)

## Install & run (with Python)

**Run from a checkout (no install):**

```bash
python3 claude-code-history.py                 # compatibility shim at the repo root
# or
python3 -m claude_code_history                 # with src/ on PYTHONPATH
```

**Install as a command (pipx / uv / pip):**

```bash
pipx install git+ssh://git@github.com/kim-dongryeong/claude-code-history.git
# or: uvx --from git+ssh://git@github.com/kim-dongryeong/claude-code-history.git claude-code-history
# or: pip install .

claude-code-history                            # browse ~/.claude/projects
claude-code-history ~/Downloads/.claude/projects --port 8778 --open
claude-code-history --version
```

**macOS app:** `./scripts/make-macos-app.sh` builds `dist/Claude Code History.app` (icon in
Dock/Finder, double-click, no lingering terminal); add `--dmg` for a draggable
`dist/claude-code-history.dmg`. It doesn't bundle Python — it just launches the installed
`claude-code-history`. Or use the plain `claude-code-history.command` (starts server + opens browser).

**Windows:** everything is stdlib-only and cross-platform (config lives in
`%APPDATA%\claude-code-history`, the default root is `%USERPROFILE%\.claude\projects`).
Install with `pip install .` (or pipx) and run `claude-code-history --open`, **or**
double-click **`claude-code-history.cmd`** in a checkout — it uses the installed command if
present, else falls back to `python`/`py` on the repo shim, and passes an optional port
(`claude-code-history.cmd 9000`). The Windows build is covered by CI (`windows-latest`).

### Which distribution form?

| Form | Command | When |
|---|---|---|
| **pipx / uvx** (recommended) | `pipx install git+ssh://…/claude-code-history.git` | Any OS with Python 3.9+ and git. One command, `pipx upgrade` to update. |
| **macOS .app / .dmg** | `./scripts/make-macos-app.sh --dmg` | Want a Dock icon + double-click on a Mac. Thin wrapper over the installed CLI. |
| **`.command` double-click** (macOS) | ship `claude-code-history.py` + `.command` | Zero-build, copy the folder. |
| **`.cmd` double-click** (Windows) | ship `claude-code-history.py` + `.cmd` | Zero-build on Windows; falls back to `python`/`py`. |

**Requirement:** Python **3.9+**. Note Claude Code itself is a *Node* app, so a machine
with transcripts does **not** necessarily have Python — Windows has none by default, and
macOS only ships `python3` (3.9) if the Xcode Command Line Tools are installed. On such a
machine, install Python once (`brew install python`, python.org, or `xcode-select
--install`) before `pipx`.

The `scripts/make-macos-app.sh` `.dmg` above is a thin `.app` (≈90 KB) that execs an
*installed* `claude-code-history` — it needs Python. For **zero-Python, double-click**
distribution, use the self-contained bundles from [Releases](#download-no-python-needed)
instead — built with PyInstaller by the `release` workflow on tag push (per-OS,
macOS signed/notarized when the signing secrets are configured).

Defaults: binds `127.0.0.1` only (never exposed to the network; `--host` warns if you
change it), reads `$CLAUDE_CONFIG_DIR/projects` or `~/.claude/projects`, and
auto-discovers `~/Downloads/.claude/projects` (copied-from-another-machine data) in the
in-app **📁 folder switcher**. Add any other folder at runtime by pasting its path
(persisted in `~/.config/claude-code-history/roots.txt`), remove with ✕. Strictly read-only —
it never writes to your transcripts.

## Features

- **Claude Code + Codex + Gemini CLI** — auto-discovers `~/.claude/projects`,
  `~/.codex/sessions` (🤖), and `~/.gemini/tmp` (♊). Each provider's schema is parsed
  with the same attribution rigor (injected IDE/environment/agent-history context is
  never shown as You), grouped by workspace, with a provider badge and resume command.
  (agy/antigravity-cli's SQLite trajectory DBs are not yet supported.)
- **Correct attribution** — 🧑 You / ✦ Claude / 💭 Thinking / 🔧 Tool call / ⚙ Tool result /
  ⓘ System / 📋 Instruction / 🤖 Subagent; tooltips + an in-app legend (❓) explain
  each; technical blocks folded by default.
- **Markdown rendering** — message text renders as Markdown: GFM tables (with
  alignment), fenced/inline code, headings, nested lists, blockquotes, bold/italic,
  clickable links. Dependency-free renderer; raw HTML is always escaped (never
  executed); `snake_case` survives; search highlighting stays inside text nodes.
- **Pretty tool blocks** — `🔧 Bash` shows the command in a shell block + its
  description; `Edit` shows a red/green old→new diff; `Read`/`Grep`/`Write` show the
  file/pattern; a tool result splits `stdout`/`stderr` (stderr in red) instead of raw
  JSON. Each fold summary previews the command/file so you can scan without expanding.
- **Index** — real titles (`ai-title`/`custom-title`), project filter (by real `cwd`),
  sort by date/my-messages/title/size (with direction toggle), per-session counts,
  output-token totals + model mix, **session-id** per row, **🔁 build-loop chips**.
- **Per-project stats** — sessions, my-participated sessions, my message count, total
  size, my-session size, loop count; overview table + per-folder detail card.
- **Full-text search** across all sessions — relevance-ranked, per-term colors,
  highlighted snippets. Matches **within a turn**, **nearby turns** (proximity), or
  **anywhere in a session** — so clues spread across turns are still found. Searches
  message text, tool-call args (Bash commands, file paths), and **code bodies** (a
  `Write`'s content, an `Edit`'s diff). Scopes: all / only-me / Claude / chat /
  🧩 code / 🔧 commands. **Field queries** `file: cmd: code: error: role: id:`, plus
  `-exclude` and `"exact phrase"`. **Search by session-id / reference** (UUID,
  branched-from id, workspace path) too — exact id matches rank to the top.
- **Session view** — per-message timestamps + per-turn tokens/model, 🧑 only-me filter,
  in-session search, ⭐ star (browser-local), ◄ prev/next session, 🔗 per-message
  permalink, **answer-thread** links, page size 100…10000/all, dark mode, and a
  **📍 Session Reference card**: Workspace / Started-in / file / session-id /
  Branched-from (linked) / `claude --resume`.
- **Event/error chips** — ⚠️ errors / ✏️ edits / ❯ commands / ⎇ commits / 🧪 tests / 🔗 URL filters.
- **Structure minimap** — right-edge rail (you/error/edit/command density), click to jump.
- **Extracted-fact digest** — files touched, commands, tests, commits, PR links.
  Deterministic, no LLM.
- **Code/diff extraction** (`🧩 Code only`) — all generated code blocks + file edits with
  one-click copy.
- **Subagent threads** — sidechain/Task transcripts (incl. workflow agents) listed per
  session and openable, orchestrator briefs clearly labelled 📋 (never "you").

## Keyboard

- `/` focus search · `Esc` blur
- `j` / `k` (or `n` / `p`) jump between **my** messages · `Enter` open that question's
  answer thread

## Language

The UI is **English by default** and fully translatable — switch live with the 🌐 picker
in the header (it remembers your choice via a cookie). A **Korean (한국어)** locale ships
built in.

**Add your own language** (no rebuild): copy `src/claude_code_history/locales/ko.json` to
`<code>.json` (e.g. `ja.json`, `fr.json`) and translate the values — the keys are the
English UI strings; leave a value unchanged or omit a key to fall back to English. Drop
the file into either:

- the package's `locales/` directory, or
- your config dir — `~/.config/claude-code-history/locales/` (macOS/Linux) or
  `%APPDATA%\claude-code-history\locales\` (Windows).

Pick a default with `--lang ja` or `CCH_LANG=ja`. PRs adding locales are welcome.

## Development

```bash
python3 -m unittest discover -s tests -v   # 97 tests: attribution + markdown/tools + i18n + HTTP smoke
```

CI runs the suite on Ubuntu/macOS/Windows × Python 3.9/3.14, then installs the package
and checks the `claude-code-history` entry point. The attribution tests are the contract:
**no machine-authored line may ever be classified as 🧑 You.**

Layout: the whole app is one module (`src/claude_code_history/app.py`) by design — stdlib
only, no framework. `claude-code-history.py` at the repo root is a thin shim for
`python3 claude-code-history.py` muscle memory.

## How attribution works

See `classify_line` in `src/claude_code_history/app.py`. A genuine human message is a
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

## Contributing

Issues and PRs welcome — especially new UI locales (see [Language](#language)) and
attribution edge cases (attach a redacted JSONL line). Keep it **stdlib-only**: no runtime
dependencies, ever. Run `python3 -m unittest discover -s tests` before opening a PR.

## License

[GPL-3.0-or-later](LICENSE). This is a finished end-user tool, distributed free — copyleft
keeps every fork and derivative open too (you can use, modify, sell, and self-host it, but
if you distribute a modified version you must share its source under the GPL). Ideas and
algorithms aren't covered by copyright — only the code is.
