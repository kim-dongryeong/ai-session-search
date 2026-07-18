# Design brief — make ai-session-search search faster / more accurate / more intuitive

Single-file Python app: `src/ai_session_search/app.py` (~5200 lines, **stdlib-only, zero-dependency**).
Local, read-only search over AI-CLI session transcripts (Claude/Codex/Gemini `.jsonl`).
Just landed a SQLite trigram FTS **candidate index** (commit `43f5491`): FTS narrows to a
recall-safe superset, the existing exact matcher (`match_session`/`_scope_ok`/`_fields_ok`/
`_snippet`) makes every final call. Results are provably identical to the old full scan.

## Measured reality (this machine, real data)
- **Warm search: 11–180 ms** (FTS working; `self_update` 11 ms, rare term 12 ms).
- **COLD first search: 7.96 s** ← the real problem. `search_api()` calls
  `_load_disk_cache(root, rows=True)` which loads the ENTIRE ~453 MB gzip **rows cache**
  into RAM before searching, competing with the background warm thread (GIL). Landing cold 1.36 s.
- **No feedback:** the main search box is a synchronous full-page GET `<form action=/search>`
  (`app.py:3472`). Pressing Enter shows nothing until the whole page swaps — cursor blinks,
  looks frozen. (User: "엔터 눌러도 찾는지 모름, 반응이 없음.")
- **Multi-hit gap:** `match_session()` returns only the BEST window for a cross-turn match,
  so a session with two far-apart relevant regions surfaces only ONE jump link. Same-turn
  ("row") matches already return all occurrences. The session view now has continuous scroll
  (loading the whole session), so after opening at one hit you *can* scroll to the other.

## Proposed changes — RED-TEAM THESE
### 1. Cold-start fix (highest impact)
Store per-path payload (`rows`+`blob`+`tokens`, zlib) as a BLOB column in the FTS DB's
`session_docs`. Cold search = FTS candidate select → load ONLY candidate payloads from the
DB → match. Removes the 453 MB bulk load; only the ~few candidate sessions are deserialized.
- Q: write amplification — a live-appending session rewrites its whole payload+FTS doc on
  every change. Acceptable? Mitigation (debounce, size cap)?
- Q: keep the gzip rows cache as fallback, or retire it? Two payload stores = drift risk.
- Q: correctness — rows loaded from the DB payload must be byte-identical to `_rows_blob()`
  (blob `[s,e)` offsets, stable token hashes). What breaks equivalence?
- Q: DB already ~2× source for trigram; +payload ≈ +uncompressed rows. Worth it on 256 GB SSD?

### 2. Feedback + perceived speed
Convert search to AJAX. On submit (and maybe as-you-type, ~200 ms debounce) immediately show
"Searching…", fetch results, render without a full-page reload.
- Q: client renders cards from `/search?format=json` (duplicate card HTML in JS) **vs** fetch
  `/search` and swap the server-rendered results fragment into a container (no duplicated render)?
- Q: search-as-you-type worth it, or just instant-feedback-on-Enter? As-you-type could fire
  many requests onto the 8 s cold path.
- Q: must preserve scope/date/project chips, snippet jump links, keyboard nav, back/forward URL.

### 3. Multi-hit surfacing
For cross-turn matches return multiple distinct clusters (not just the best window) → each
far-apart region gets its own jump link (cap ~6, rank by density).
- Q: cheap definition of "distinct clusters"? (row_gis already all; for cross-turn: greedy
  non-overlapping windows over the term-occurrence positions?)
- Q: given continuous scroll can reach the other region, is multi-link needed, or is one link
  + "N matches — scroll" enough? What's most intuitive?

## Constraints
- stdlib only; single file; zero external deps. Recall MUST stay 100% (candidate-only FTS;
  matcher is final). No result changes. `(mtime_ns, size)` cache key. Keep 172 tests green.

## Ask
Red-team each proposal. Highest-risk? Correctness traps? Better alternatives? Prioritize for
"faster + more accurate + more intuitive", speed first. **Analysis only — do NOT edit files.**
