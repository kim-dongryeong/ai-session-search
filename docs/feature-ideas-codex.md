- **1. Cross-machine project aliases**
  - **What:** Let the user collapse paths like `/Users/kdr/dev/foo`, `/home/kdr/foo`, and copied `~/.claude/projects/.../foo` into one logical project.
  - **Why:** Across machines, real `cwd` fragments the index and search filters.
  - **How:** Add a small UI alias map stored in `localStorage`; normalize project filter labels at render time only. Keep raw paths inspectable.

- **2. URL-addressable view state**
  - **What:** Preserve search query, scope, project filter, sort, page size, session id, selected message, and thread mode in the URL.
  - **Why:** Power users need to jump back to exact evidence, keep tabs, and send themselves links.
  - **How:** Encode state in query params / hash. No server persistence, no writes, no DB.

- **3. Session minimap / structure rail**
  - **What:** Add a compact right-side rail showing my-message positions, tool-heavy regions, errors, subagent spans, and current viewport.
  - **Why:** Large 12k-message sessions need spatial navigation, not just paging.
  - **How:** Server emits lightweight per-message category offsets; browser renders a proportional vertical bar with clickable markers.

- **4. “Interesting events” filter**
  - **What:** One-click filters for likely reread targets: errors, failed commands, file edits, test runs, commits, PR/issue URLs, `TODO`, stack traces, and permission/approval events.
  - **Why:** When reviewing old coding sessions, the useful bits are usually where something changed, failed, or was decided.
  - **How:** Regex/classifier pass over existing events at request time; expose as chips. Keep it deterministic and transparent.

- **5. Per-session decision/change digest**
  - **What:** A generated outline of touched files, commands run, tests run, failures, commits/branches/PR links, and major user prompts.
  - **Why:** Before rereading thousands of lines, the user needs to know whether this is the right session.
  - **How:** Stdlib-only heuristic extraction from tool calls/results and message text. No LLM summary; call it “extracted facts,” not “summary.”

- **6. Better snippet clustering for global search**
  - **What:** Group search results by session, then by nearby matches, with “open around first match” and “open all matches in session.”
  - **Why:** Raw full-text search gets noisy across many copied machines.
  - **How:** Merge matches within N messages / N minutes; show title, project alias, date, match count, and strongest snippets.

- **7. Message permalinks + local annotations via URL only**
  - **What:** Every message gets a stable anchor and copy-link button; optional temporary browser-side notes/bookmarks.
  - **Why:** Reviewing often means collecting exact turns to revisit.
  - **How:** Use `session_uuid#line_number` or event UUID anchors. Store optional bookmarks in `localStorage`; never write beside transcripts.

- **8. Unwise under constraints: semantic search, embeddings, persistent tags**
  - **Why not:** They want DBs, external deps, background indexing, or writeable metadata. That violates the tool’s best property: portable, read-only, single-file, obvious behavior.
  - **Safer substitute:** deterministic extracted facets, URL state, localStorage-only aliases/bookmarks, and better grouping.
