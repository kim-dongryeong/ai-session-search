# Changelog

## 3.1.0 — 2026-07-06

- **Agent access — your past sessions become a memory your coding agent can query.**
  The same search engine (correct attribution, all three providers) is now reachable
  four ways, all local + read-only + stdlib-only:
  - **MCP server** — `aiss --mcp` speaks stdio JSON-RPC 2.0 (`initialize` / `tools/list`
    / `tools/call`). Tools: `search_sessions(query, scope?, limit?)`,
    `get_session(sid | path, limit?)`, `list_recent_sessions(provider?, limit?)`.
    Add to Claude Code with `claude mcp add ai-session-search -- aiss --mcp`.
  - **CLI** — one-shot `aiss --search '<query>'` (with `--scope`, `--limit`, `--json`),
    `aiss --get <sid|path>`, `aiss --sessions`. No server needed — ideal for an agent's
    Bash tool.
  - **JSON HTTP API** — `/api/search`, `/api/session`, `/api/sessions`, `/api/roots`,
    plus `/search?format=json`, on the running web server.
  - **Skill** — `skills/search-past-sessions/SKILL.md` teaches an agent *when* to look
    up prior work (before re-solving something) and how to query it.
- The full field/scope query language (`file:` `cmd:` `code:` `error:` `role:me`
  `id:`, `-exclude`, `"phrases"`, scopes `all|human|claude|chat|code|tool`) works
  identically across all four.

## 3.0.0 — 2026-07-06

- **Renamed to `ai-session-search` (command `aiss`, short alias `ass`).** Now that it
  reads Claude Code + Codex + Gemini, "Claude Code History" was too narrow — the name is
  provider-neutral and says what it does: search your AI coding-session history. The
  Python package is `ai_session_search`; the UI title, repo, PyPI name, launchers, and
  bundle artifacts all follow. (References to **Claude Code** the *agent* are unchanged.)
  Config moved to `~/.config/ai-session-search/` — folders are auto-discovered, so you
  don't lose anything; re-add any custom folders once.

## 2.4.0 — 2026-07-06

- **Per-provider folder glyphs** in the switcher: ✴️ Claude, 🌀 Codex, ✨ Gemini — by
  folder kind or by "claude"/"codex"/"gemini" appearing in a user-added path. Session
  badges match.
- **"Install as an app" is now a big explainer popup** with two SVG illustrations —
  one showing the app in the macOS **⌘-Tab** switcher (its own icon), one showing that
  **Chrome extensions still work** inside it (it's still Chrome). Auto-opens once when the
  browser reports the app is installable; the header button reopens it; the modal's
  "Install now" fires the native prompt (with a manual-steps fallback).
- **Keyboard nav works under non-Latin layouts** — `j`/`k`/`n`/`p` (and `/`) now match on
  `event.code` (physical key), so they work with a Korean/CJK keyboard active.
- **Language switch keeps your search** — the 🌐 switcher now sets the cookie and reloads
  the same URL, so your query/scope survive an en↔ko switch (it used to reset to the index).

## 2.3.0 — 2026-07-06

- **Gemini CLI transcripts are now supported** too (three agents: Claude Code + Codex +
  Gemini). `~/.gemini/tmp/<project>/chats/session-*.jsonl` is auto-discovered (♊ in the
  switcher). Human `user` turns, `gemini` answers, `thoughts` (→ 💭 thinking),
  `toolCalls` **with their embedded results** (→ 🔧 call + ⚙ result), per-turn tokens
  (input/output/cached) and the model (`gemini-3-flash-preview`) all map through, so
  search / scopes / code search / the session view work. Workspace comes from
  `~/.gemini/projects.json` (project-name → real path); the card shows a ♊ Gemini badge.
  `run_shell_command` renders as a shell block.
- **Not** included: **agy / antigravity-cli** stores conversations as SQLite
  "trajectory" `.db` files (`~/.gemini/antigravity-cli/conversations/*.db`) with an
  opaque `step_payload` format — a separate reverse-engineering effort, deferred.
- +3 tests (106 total).

## 2.2.0 — 2026-07-06

- **Codex transcripts are now supported** alongside Claude Code. `~/.codex/sessions`
  is auto-discovered as a folder (🤖 in the switcher); Codex `rollout-*.jsonl` files
  are parsed with the same attribution rigor — a `role:user` message that is really
  injected context (`# Context from my IDE setup:`, `<environment_context>`,
  `# AGENTS.md instructions`, agent-history, `<skill>`, …) is **never** shown as 🧑 You.
  Codex messages / reasoning / `function_call` + output map to the existing
  text / thinking / tool-call / tool-result categories, so search, scopes, code search,
  the session view, tokens-where-present, and the model badge (e.g. `gpt-5.3-codex`) all
  work. Sessions group by workspace (`cwd`, since Codex has no project folders); the
  session card shows a **🤖 Codex** badge and a `codex resume <id>` command. (Codex
  transcripts don't record per-message token usage, so token totals there are omitted.)
- Provider-aware plumbing: `provider_of()`, `session_files()`, `summarize_file()`,
  `load_session()`, `classify_turns()`, and the index all dispatch by provider.
- +4 tests (103 total).

## 2.1.0 — 2026-07-06

Search 2.0, session UX, and downloadable app bundles (from Codex's review playbook).

- **Search across turns, not just within one.** Same-turn matches still rank highest,
  but when your terms are spread over a session the search now finds them too —
  labelled **nearby** (a tight window of turns, via a min-span proximity scan) or
  **in session**. Recovering "the session where I fixed X and ran the Y test" works
  even though X and Y were different turns.
- **Code & command search (closes a real gap).** The search corpus now includes the
  code bodies that the `🧩 Code only` view extracts (a `Write`'s `content`, an `Edit`'s
  `new_string`) — previously visible there but *unfindable*. New scopes **🧩 Code/edits**
  and **🔧 Commands/files**.
- **Field-aware queries:** `file:app.py`, `cmd:pytest`, `code:SearchRow`, `error:Traceback`,
  `role:me`, `id:<uuid>`, plus `-exclude` and `"exact phrase"`. Beginners keep the scope
  dropdown; power users get syntax. Ranking gained field/phrase/proximity/recency boosts.
- **Session UX:** ⭐ **star** sessions (browser-local, transcripts stay read-only),
  **◄ prev / next ►** session in the same project, and a 🔗 **permalink** on every message
  (copies a deep link to `#t<n>`).
- **Perf & hardening:** `load_session()` does one cached pass instead of parsing each
  session twice for `/session`; added `X-Content-Type-Options: nosniff` + `Referrer-Policy`,
  a query-length cap, and a results cap. Search rows are structured (kind bitmask) —
  groundwork the review calls for, without a database.
- **Downloadable app bundles.** A `release` GitHub Actions workflow builds double-click
  bundles with **PyInstaller** on tag push — `.dmg` (macOS arm64 + Intel), `.exe` (zip,
  Windows), and a Linux binary (tar.gz) — and attaches them to the Release. macOS builds
  are signed + notarized when the signing secrets are set, else ad-hoc-signed. Locally
  verified: the frozen `.app` serves and loads the bundled Korean locale.
- 97 tests (added search-engine, field-grammar, proximity, code-scope, session-nav,
  header, and i18n coverage).

## 2.0.0 — 2026-07-05

First public release. 🎉

- **Open source under GPL-3.0-or-later.** A finished end-user tool distributed free;
  copyleft keeps forks/derivatives open (you can use, modify, sell, self-host — but a
  distributed modified version must ship its source under the GPL). `LICENSE` added,
  `pyproject` license + classifiers set.
- **UI is now English by default**, and fully **internationalized**. Every user-facing
  string goes through a tiny stdlib `tr()` layer whose keys are the English text.
  Switch language live with a 🌐 header picker (remembered via a cookie); set a default
  with `--lang` / `CCH_LANG`. A **Korean (한국어)** locale ships built in.
- **Add a language with no rebuild**: drop `<code>.json` (e.g. `ja.json`) into the
  package's `locales/` or `~/.config/ai-session-search/locales/` (or `%APPDATA%\…` on
  Windows) — keys are the English strings; missing keys fall back to English.
- 86 tests (added i18n + language-switch coverage).

## 1.7.0 — 2026-07-05

- **Token usage & model, at every level.** Claude Code records `message.usage`
  (input / output / cache-creation / cache-read) and `message.model` on each assistant
  message — the viewer now surfaces all of it (reasoning **effort is *not* stored** in
  the transcript, so it is deliberately never shown/guessed):
  - **Per project** — the 📊 stats table gains an **출력토큰** column (tooltip = full
    input/output/cache breakdown) and a **모델** mix column; projects sort by output
    tokens; a note flags that cache-read is cheap re-use so totals aren't misread.
  - **Per session** — a 토큰 line + model-mix badges in the session summary, and a
    token badge + dominant model on every index row.
  - **Per question** — each 🧑 turn shows the tokens its whole answer block (tool loop
    included) consumed; each ✦ Claude turn shows its own tokens + the model it used
    (so mid-session model switches are visible).
- **Scoped search.** Search **within one folder** (a 🔎 box on the project stats card,
  scoping results to that project) and **within the current session** (a 🔎 box on every
  session; `?sq=` lists just the matching messages with a count, highlight, and a
  "← 전체 대화" toggle — and it searches the same rich corpus, so Bash commands and file
  paths are findable in-session too).
- **Windows.** Confirmed cross-platform (config in `%APPDATA%`, root under
  `%USERPROFILE%\.claude\projects`, utf-8 stdout) and covered by CI on `windows-latest`;
  added a double-click **`ai-session-search.cmd`** launcher (installed command → else
  `python`/`py` on the shim).

## 1.6.0 — 2026-07-05

- **Search by session-id / reference.** Searching a UUID like
  `40b92137-2ff9-4461-90c3-21729c2b3bee` now finds the session(s) — matched against
  each session's **session-id, branched-from id, workspace path, launch dir, file
  path and title** (a session-level match, so it works in any scope). Exact id
  matches rank to the very top with a `참조` chip; the same id living under two
  project folders (e.g. a correctly-placed copy + a stray one) both show up. Metadata
  is searchable too — find sessions by their workspace path.
- **Session metadata card** (`📍 세션 정보 / Session Reference`) at the top of each
  session, modeled on the `session-ref` skill: **Workspace** (current dir = last
  `cwd`), **Started in** (launch dir = first `cwd`, shown only when it differs — i.e.
  the transcript was moved to another workspace), **session file** path, **session-id**,
  **Branched from** (`forkedFrom.sessionId`, linked to the parent session when it
  exists in the same root), git branch, and the resume command. `summarize_file` now
  records `start_cwd` and `forked`.

## 1.5.0 — 2026-07-05

- **Tool calls are now searchable.** The search corpus previously indexed message
  text, tool *results*, thinking, injected context and channel bodies — but not the
  tool *call* itself, so a `Bash` command like `git commit -m …`, a `Read`/`Edit`
  file path, or a `Grep` pattern was invisible to search (a real gap vs viewers that
  scan the whole JSON). `search_turns` now adds, per tool_use, the tool name plus its
  identifying args (`command`, `file_path`/`path`/`notebook_path`, `pattern`, `query`,
  `url`, `description`, `prompt`). Large code blobs (`content`/`new_string`/
  `old_string`) are deliberately left out — they're already searchable via the
  tool_result diff, so indexing them again would only bloat the index and double-rank.

## 1.4.3 — 2026-07-04

- **Channel-relayed human messages get their own category** (💬 텔레그램·채널). A
  message sent into a session through a plugin (Telegram/Slack/…) arrives wrapped in
  `<channel source="plugin:telegram:…" user="…" ts="…">…</channel>` and is flagged
  `isMeta`/`promptSource=system` by the harness — so it used to render as raw XML
  inside **ⓘ 시스템·주입**. It's now recognised as genuine person-authored text: the
  envelope is parsed, the label shows **who sent it** (`💬 텔레그램 · @user` — not
  assumed to be you, since anyone paired can send), the body renders as Markdown, and
  a small caption keeps the source/chat/original-timestamp. Searchable by body only
  (no attribute noise). Legend updated.

## 1.4.2 — 2026-07-03

- **Useful tool blocks are expanded by default** — the view now reads like the live
  conversation instead of a wall of folds. `Bash`/`Edit`/`Write`/`Read`/`Grep`/`Glob`
  calls and **Bash results** open on load; short generic results (<1200 chars) too.
  Because an `Edit` call and its result are near-identical, only the **call** (the
  diff) opens — the paired result stays folded, labelled *"위 편집과 동일 — 펼치면
  diff"*. Long file reads and 추론/시스템·주입 blocks stay folded. Every block is still
  height-capped with internal scroll, so nothing blows up the page.

## 1.4.1 — 2026-07-03

- **Edit/Write results render as a GitHub-style diff** instead of a raw JSON blob.
  A tool result carrying `structuredPatch` (Claude's ready-made unified diff) is
  drawn as colored hunks — green additions, red deletions, gray context, `@@` hunk
  headers — with the file path on top; the `oldString`/`newString`/`userModified`
  envelope is gone. The `Edit` *call* now shows a real old→new diff (via stdlib
  `difflib`) rather than two stacked full-text blocks, and `MultiEdit` renders one
  diff per edit. Long diffs cap at 800 lines with a `… (diff 생략)` marker.

## 1.4.0 — 2026-07-03

Rich rendering — messages and tool blocks now read like the real conversation.

- **Markdown rendering**: assistant/human message text is rendered as Markdown —
  **GFM tables** (with column alignment), fenced & inline code, headings, ordered/
  nested lists, blockquotes, bold/italic/strikethrough, and clickable links. A
  previously-flat message with a comparison table now shows the actual table. The
  renderer is a compact, dependency-free (**stdlib only**) implementation: every
  message is `html.escape()`d *before* any transform, so raw HTML in a transcript is
  shown as text, never executed; underscore emphasis is word-boundary-gated so
  `snake_case` identifiers survive. Search highlighting is applied to the rendered
  HTML's *text nodes only* (never inside tags/attributes). `md_html()` can never
  raise — on any parse trouble it falls back to escaped+highlighted plain text.
- **Pretty tool calls & results**: a `🔧 Bash` call now shows its command in a shell
  block (with the description beneath) instead of raw JSON; `Edit` shows a red/green
  old→new diff; `Read`/`Grep`/`Write` show the file/pattern. A tool *result* splits
  `stdout` / `stderr` (stderr in red) and drops the JSON envelope noise, with plain
  results shown as-is. Each fold's summary carries a one-line preview (the command,
  the file) so you can scan without expanding.

## 1.3.0 — 2026-07-03

- **Renamed `claude-viewer` → `ai-session-search`** (repo, package
  `ai_session_search`, command). The tool views specifically *Claude Code* session
  transcripts, not claude.ai/API — the name now says so. A short **`aiss`** console alias
  is installed alongside `ai-session-search`. GitHub redirects the old repo URL; update
  local remotes and reinstall from the new URL.

## 1.2.1 — 2026-07-03

- **Python floor lowered to 3.9** (was 3.10) — verified the whole suite passes on the
  macOS system `python3` (3.9.6). CI matrix now tests 3.9/3.14. README corrected: Claude
  Code is a *Node* app, so Python is **not** guaranteed on a machine with transcripts
  (Windows has none; macOS only ships 3.9 with Xcode CLT) — install once before pipx.
- **Advanced search menu**: the 기간/날짜 range moved out of the always-on bar into a
  🔧 도구 toggle (Google-style), hidden by default and auto-opened (with a ● dot) when a
  time filter is active. The main bar is now just query + scope.

## 1.2.0 — 2026-07-03

Search relevance + colors + custom dates; app icon & favicon; macOS app/dmg.

- **Relevance ranking**: results are ordered by a score where whole-word matches
  dominate substring pollution — a doc containing the literal word "oss" now ranks
  above one that only has "ossean" (bonus when every term matches as a real word).
  Substring-only matches are marked `≈ 부분일치`.
- **Per-term highlight colors**: each query term gets its own color, with a color
  key in the search header.
- **Custom date range**: `from`/`to` date inputs (like a search engine's custom
  range), alongside the 7/30/90일 presets; explicit dates override the preset.
- **Snippets** now center on the whole-word match, not the first substring.
- **Icon & favicon**: an SVG app icon (speech bubble + person = 🧑) served at
  `/favicon.svg`; `assets/` ships PNG sizes + `icon.icns`.
- **macOS app / dmg**: `scripts/make-macos-app.sh [--dmg]` builds a lightweight
  `AI Session Search.app` (no bundled Python — execs the installed `ai-session-search`) and
  an optional `.dmg`.

## 1.1.0 — 2026-07-02

Search overhaul.

- **Jump to match**: search results and each snippet now link with `goto=<turn>` —
  the session opens on the right page, scrolls to the matched message, and outlines it.
  If the match is a non-human turn while filtered to 🧑 내 말만, the filter widens
  automatically.
- **Multi-term AND + phrases**: space-separated words must all appear in a turn;
  `"quoted phrases"` (straight or curly quotes) match as a unit. Highlighting marks
  every term (overlaps merged).
- **Speed**: per-file searchable-turn cache keyed on (mtime_ns, size) — repeat searches
  skip re-parsing unchanged files (measured on 157MB/174 sessions: 2.1s cold → ~1ms warm).
- **Filters**: scope grew to 전체 / 🧑 내 말만 / ✦ Claude만 / 대화만(도구·시스템 제외);
  period filter (7/30/90일, by session mtime); project chips over matched results.
- Search header shows parsed query, scope, elapsed ms.

## 1.0.0 — 2026-06-30

First packaged release.

- **Packaging**: proper Python package (`src/ai_session_search/`), `pyproject.toml`,
  `ai-session-search` console entry point, `python -m ai_session_search`, pipx/uvx installable
  from the private git repo. Root `ai-session-search.py` kept as a compatibility shim.
- **CLI**: argparse — positional projects dir, `--port`, `--host` (with network-exposure
  warning), `--roots`, `--open` (auto-open browser, cross-platform via `webbrowser`),
  `--version`, `--help`.
- **Behavior change**: default root is now `$CLAUDE_CONFIG_DIR/projects` or
  `~/.claude/projects` (was `~/Downloads/.claude/projects`); the Downloads copy is still
  auto-discovered in the in-app folder switcher.
- **Fix**: index cache now refreshes incrementally per request (new/changed/deleted
  sessions appear without restarting the server).
- **Fix**: search results showed a lossy project label with a hardcoded username;
  now uses the real cwd like everywhere else.
- **Fix**: workflow-subagent detection regex now handles Windows path separators;
  module import is side-effect-free (no `sys.argv` reads at import), enabling entry
  points and tests.
- **Tests**: 33 stdlib-unittest tests — attribution ruleset regression (machine text
  must never be labelled 🧑 나), summaries/tags/digest, helpers, HTTP smoke (routes,
  escaping, path-traversal rejection).
- **CI**: GitHub Actions matrix (Ubuntu/macOS/Windows × Python 3.10/3.14).

### Pre-1.0 (2026-06-29 …)

Single-file viewer: verified attribution ruleset, index/search/session views, answer
threads, keyboard nav, page-size control, event/error chips, minimap, extracted-fact
digest, code/diff extraction, subagent threads, per-project stats, autonomous
build-loop chips, in-app folder add/remove, session-ids + resume commands.
