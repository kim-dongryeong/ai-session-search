---
name: search-past-sessions
description: >-
  Search the user's OWN past AI coding sessions (Claude Code, Codex, Gemini CLI)
  before re-solving something. Use when the user says "like last time", "we did
  this before", "how did I fix…", "what was that command/error/decision", or when
  you're about to reinvent something they've likely already worked out. Recalls
  their real prompts, prior answers, tool commands, file paths, and code.
---

# Search past sessions

The user has months of past AI coding sessions on this machine — across Claude Code,
Codex, and Gemini CLI. `ai-session-search` (`aiss`) indexes them all with correct
speaker attribution (only genuinely human-typed text counts as the user). Before you
re-derive something, **check whether they already solved it.**

## When to reach for this

- The user references the past: *"like we did last time"*, *"the same setup as the
  other project"*, *"what was that flag/command/env var"*, *"how did I fix this
  before"*, *"didn't we already decide this"*.
- You're about to re-solve a non-trivial problem (a tricky build config, a migration,
  a regex, an API integration) that the user has plausibly hit before.
- You need a decision or its rationale that isn't in the current repo or its history.
- You want an exact command/error string the user ran previously.

**Don't** use it for facts that live in the current repo (read the code/git log
instead), or for general knowledge.

## How to search

Prefer the MCP tools if this project's MCP server is connected (`search_sessions`,
`get_session`, `list_recent_sessions`). Otherwise use the CLI or JSON API below — all
three hit the same engine.

### Query language

- Multiple words are **AND**-ed and matched within the same turn/nearby (proximity).
- `"quoted phrase"` for exact phrases.
- Field filters: `file:app.py` `cmd:pyinstaller` `code:ThreadingHTTPServer`
  `error:"Address already in use"` `role:me` (the user's own words) `id:<uuid>`.
- `-word` excludes.
- Scopes: `all` (default), `human`, `claude`, `chat`, `code`, `tool`.

### CLI (no server needed)

```bash
aiss --search 'pyinstaller --add-data locales' --scope tool --limit 10
aiss --search 'role:me windows encoding' --json      # raw JSON for parsing
aiss --get <session-id>                               # full session as text
```

### JSON API (if a server is running on :8777)

```bash
curl -s 'http://127.0.0.1:8777/api/search?q=windows+encoding&scope=all&limit=10'
curl -s 'http://127.0.0.1:8777/api/session?sid=<session-id>'
curl -s 'http://127.0.0.1:8777/api/sessions?limit=20'
```

## Workflow

1. **Search** with a few distinctive words (an error string, a filename, a command).
   Widen (drop a word, `scope:all`) if empty; narrow (`role:me`, `cmd:`) if noisy.
2. **Read the hits** — each result has `sid`, `provider`, `title`, `workspace`, and
   snippets. Pick the most relevant `sid`.
3. **Open it** with `get_session` / `--get` / `/api/session` to see the full exchange:
   what the user asked, what worked, what didn't.
4. **Apply** what you learned — cite it briefly ("last time you solved this by …")
   so the user can confirm. Don't blindly repeat a past command; verify it still fits.

## Notes

- Everything is local and read-only; nothing is uploaded.
- Attribution is trustworthy: `role:me` / `scope:human` is *only* text the user
  actually typed, never tool output or injected context.
- If a search returns nothing, say so — don't invent a past session.
