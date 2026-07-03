# Changelog

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

- **Renamed `claude-viewer` → `claude-code-history`** (repo, package
  `claude_code_history`, command). The tool views specifically *Claude Code* session
  transcripts, not claude.ai/API — the name now says so. A short **`cch`** console alias
  is installed alongside `claude-code-history`. GitHub redirects the old repo URL; update
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
  `Claude Code History.app` (no bundled Python — execs the installed `claude-code-history`) and
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

- **Packaging**: proper Python package (`src/claude_code_history/`), `pyproject.toml`,
  `claude-code-history` console entry point, `python -m claude_code_history`, pipx/uvx installable
  from the private git repo. Root `claude-code-history.py` kept as a compatibility shim.
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
