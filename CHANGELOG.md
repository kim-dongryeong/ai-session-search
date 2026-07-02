# Changelog

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

- **Packaging**: proper Python package (`src/claude_viewer/`), `pyproject.toml`,
  `claude-viewer` console entry point, `python -m claude_viewer`, pipx/uvx installable
  from the private git repo. Root `claude-viewer.py` kept as a compatibility shim.
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
