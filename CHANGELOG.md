# Changelog

## 4.2.1 — 2026-08-21

- **Fix: the app could write its state files into the real config directory even when pointed
  somewhere else.** The paths for settings, favorites, starred sessions, saved folders, and the
  update check were assembled once when the program started. Anything that later redirected the
  config directory — the test suite, demo mode — moved the directory but not those paths, so
  writes still landed in the real `~/.config/ai-session-search`. Every path is now resolved at
  the moment it is used, and a test asserts that redirecting the config directory redirects all
  of them (and that the old import-time constants stay gone).

  **This bug destroyed saved settings.** Verifying the style settings in a browser ran a throwaway
  server that was supposed to use a temporary config directory; because of this defect it wrote
  over the real settings file instead, clearing the saved UI style. If your Settings → style
  choices are back to defaults after updating, that is why — they cannot be recovered and will
  need to be chosen again. Favorites, starred sessions, and your folder list were not affected.

## 4.2.0 — 2026-08-20

- **Inline code now has its own style settings, separate from code blocks.** Previously the two
  shared one set of controls, so enlarging code blocks also enlarged the `` `code` `` spans inside
  sentences — pushing the line height around — and inline code's background and corners couldn't
  be changed at all. Settings → Advanced now has an **Inline code** group: size, background,
  text color, and corner radius, each independent of the code-block controls. The existing
  controls are relabelled "Code block …" so it's clear which is which.
- **Inline size is set as a multiple of your body text, not a fixed pixel size**, so it stays
  proportionate when you change the body font size.
- **The font is still shared between the two** — a document rarely wants a different monospace
  face inline than in a block. Ask if you'd like these split too.
- **The preview now includes a sentence with inline code**, so you can see that setting while
  choosing it, and the theme presets fill in inline colors along with everything else.
- **Nothing changes until you choose something**: the new defaults are exactly what inline code
  looked like before, so an existing install renders identically.

## 4.1.1 — 2026-08-20

- **Fix: "Code font", "Code border width", and "Code border color" did nothing.** All three saved
  correctly and appeared in the page's stylesheet, but had no visible effect on the code blocks
  in a conversation:
  - **The font** was set on the `<pre>`, while the text you actually see sits in a `<code>` inside
    it. Every browser's built-in stylesheet has its own rule for `<code>`, and a rule that matches
    an element directly beats a value inherited from its parent — so the built-in monospace font
    won and your choice was ignored. The inner element now inherits the font and size explicitly.
  - **The border** was only applied to the standalone "🧩 Code only" view. In a normal
    conversation the frame around a code block is drawn by its wrapper (which also holds the
    language label), and that wrapper still had its border hardcoded. It now follows the width,
    color, and corner-radius settings, in both light and dark mode.
  Every style control was then re-verified in a real browser by setting a distinctive value and
  reading back the rendered result, rather than only checking that the CSS was emitted.

## 4.1.0 — 2026-08-19

- **New: a Settings page for how the UI looks** (`⚙️ Settings`, linked from the top of the index).
  Start from a **theme preset** — Default, GitHub, Dracula, or Solarized — which sets the code,
  table, and highlight colors for light and dark at once. Open **Advanced** for individual
  control: the code font and size, code-block background, border color/width/corner radius,
  table border and header shading, zebra striping on/off, all six search-highlight colors, and
  the body text size, line height, and content width.
- **Colors are chosen per mode, with a preview that can show either one.** A single color
  necessarily looks wrong in one of the two modes, so light and dark are set separately. Since
  the app follows your macOS appearance and has no theme switch of its own, the preview panel
  has its own **Light / Dark** buttons: the sample code block, table, and highlighted sentence
  render in the mode you're editing — with matching background and text color — without touching
  your system setting.
- **Anything you haven't changed renders exactly as before.** Untouched settings emit no CSS at
  all and fall back to the original built-in values, so this release changes nothing visually
  until you choose something.
- **The Settings page never styles itself with your choices**, so no color you pick can make the
  page you'd fix it from unreadable. A **Reset to defaults** button clears everything at once.
  Printing is unaffected too: a print stylesheet resets to the light values, so a dark code
  background can't come out as white-on-white on paper.
- Values are validated on both save and render — colors must be hex, sizes are range-checked, and
  the font field accepts only font-name characters — so a hand-edited settings file can't inject
  anything into the page's stylesheet.

## 4.0.37 — 2026-08-19

- **New: each search result snippet shows when that message was written.** Results used to give
  you the matching text and the role, but no date — so you couldn't tell a hit from last week
  from one a year old without opening it. Every snippet now carries a compact `MM/DD HH:MM`
  stamp (hover it for the full date including the year). Turns that genuinely have no timestamp
  simply show nothing rather than an empty slot.
  The timestamp rides the existing cached search rows, so a broad search costs the same as
  before — an earlier attempt that re-parsed each matched session on render was 20× slower and
  was thrown away.
- **Old search index files are now cleaned up.** Each time the cache format changed, the app
  started a new index file and silently abandoned the previous one, so a long-lived install
  accumulated one orphaned multi-hundred-megabyte database per past format (several GB in
  practice). The app now deletes superseded index files the first time it opens the current one.
  Because this release does change the format, expect one background re-index after updating —
  it runs in the warm-up thread, so searching stays available while it catches up.

## 4.0.36 — 2026-08-15

- **Fix: retrying a stuck "Restarting into the new version…" re-downloaded the whole update.**
  If the browser gave up waiting for the relaunch (e.g. the bundle swap was slow because the
  disk/CPU was busy with something else), the update usually still finished successfully in the
  background — but the "Installed, but didn't restart" message was the *same* button with its
  original click handler still attached, so clicking it re-ran the entire download → verify →
  install flow from scratch and popped the "Download the update, verify it, and restart?"
  confirm again, even though nothing needed re-downloading. It now just rechecks whether the
  new version is already running and reloads if so.
- **The relaunch-verification window is wider and the two ends agree on it.** The browser's own
  timeout for "did the new version come up" was tighter than the server's own retry budget, so
  the browser could declare failure while the server was still legitimately retrying. Both sides
  now share a wider, aligned window.

## 4.0.35 — 2026-08-15

- **New: newest-first sort in the conversation view.** A `⇅ Newest first` toggle next to
  "Code only" flips the message order so page 1 shows the most recent messages instead of the
  first ones — the same `sort=new` convention the project timeline already used. Switching to
  newest-first falls back to classic Prev/Next paging (the incremental scroll-fill only makes
  sense for a contiguous ascending run); switching back to chronological restores the usual
  auto-loading behavior unchanged. Jumping to a message from search (goto=) always lands in the
  normal ascending order regardless of which sort you had selected.

## 4.0.34 — 2026-08-15

- **New: per-message favorites (★).** Every message — in the conversation view, in-session
  search results, threads, sub-agent views, and the project timeline — now has a small ☆
  button next to its permalink. Click it to save that one message; a new **⭐ Favorites** page
  (linked from the top of the index) lists everything you saved, grouped by session, each with
  its excerpt and a jump link straight to that message. This is separate from the existing
  whole-session ⭐ stars.
- **Favorites survive moving your history to another computer.** A favorite is keyed by the
  session UUID embedded in the transcript's *filename* plus the message's position — never by
  the file's absolute path. So whether you copy a session folder to a new machine and add it as
  a search folder, or transplant the files into the new machine's own session folder, the same
  favorites file keeps working: the app re-finds each session by scanning the current folders
  for that filename. To migrate, copy the single file shown at the bottom of the Favorites page
  (`~/.config/ai-session-search/favorites.json`) to the same location on the new computer. If a
  favorite's session isn't in any added folder yet, the page says so instead of a dead link.

## 4.0.33 — 2026-08-15

- **Fix: Codex, Gemini, and Antigravity replies were labelled "Claude".** The assistant-message
  label was hardcoded, so opening a Codex transcript showed `✦ Claude` above every reply that
  Codex had written. Each session now shows the agent that actually wrote it — `🌀 Codex`,
  `✨ Gemini`, `✨ Antigravity`, or `✦ Claude`. This applies everywhere a message is rendered:
  the conversation view, in-session search, threads, sub-agent views, the incremental
  "load more" fragments, and the cross-session search snippets.
  In the **project timeline**, which merges several sessions into one stream, the label is
  decided per message from its own session — so a folder holding both Codex and Claude work
  labels each message correctly.
- **Screens that cover every provider at once now stay neutral.** The legend, the index page
  blurb, and a workspace summary that spans more than one agent say `✦ Agent` instead of naming
  one; the search scope filter is now `✦ Only the agent` rather than `✦ Only Claude`. The legend
  descriptions ("the agent's reasoning", "output of a tool the agent ran", …) were reworded the
  same way.

## 4.0.32 — 2026-08-14

- **Fix: the Back button could show the version (and page) from before an update.** Pages were
  cacheable, so after a self-update the browser would restore a copy rendered by the *old*
  build — the version badge in the top-right flipped back to the previous number on Back, and
  forward again on any fresh request. Pages are now sent `Cache-Control: no-store` (everything
  is served from your own machine, so re-fetching costs nothing), and a `pageshow` handler
  catches browsers that restore from the back/forward cache anyway: it asks the running server
  which version it is and reloads on a mismatch. This was cosmetic — the new build was always
  the one actually serving — but it made it look like the update had come undone.

## 4.0.31 — 2026-08-13

- **In-session search results now have the category filter chips.** Searching inside one
  conversation (the 🔎 box at the top of a session) showed a flat list of matches with no way
  to narrow it. It now carries the same `0`=All / `1`,`2`,… chip bar as the full conversation
  (🧑 My messages, ✦ Agent, ⚠️ Errors, ✏️ Edits, 🧠 Memory, ❯ Commands, ⎇ Commits, 🧪 Tests,
  🔗 URL), with counts computed over the matched messages only, so a chip never appears for a
  category that has no hits. Filtering also hides the "▲ Load 100 before / ▼ Load 100 after"
  buttons attached to a hidden result, instead of leaving them stranded.

## 4.0.30 — 2026-08-12

A one-click update could fail outright when the download server dropped the very first
connection — a common, harmless hiccup — because nothing retried.

- **Fix: a single dropped connection could fail the whole update.** GitHub's download
  server occasionally closes the very first connection of a request without answering it
  at all; that's normal and the very next attempt almost always succeeds. The updater
  previously had no retry logic anywhere, so this harmless hiccup showed up to you as
  "Update failed — download failed: Remote end closed connection without response" and
  you had to click "Update" again yourself. It now retries the download (and the
  behind-the-scenes check for the latest release) a few times with a short pause between
  attempts before giving up.
- **Better wording when an update genuinely can't be downloaded.** If every retry fails
  (for example your connection is actually down), you now see "Download failed — check
  your connection and try again." instead of a raw exception string. The technical detail
  is still included in parentheses for a bug report, and the Update button goes back to
  being clickable so you can try again right away.

## 4.0.29 — 2026-08-12

One-click update now actually relaunches you into the new version, and the app never
quietly moves to a different address behind your back.

- **Fix: "Update & restart" could install the new version and then never relaunch it.**
  macOS's `open` activates an already-running copy of an app instead of starting a new one,
  so the handoff to the freshly installed build silently never happened — the old server
  kept running and the page sat on "Restarting into the new version…" forever. The
  updater now forces a genuinely new instance (`open -n`), and — instead of just assuming
  that worked — actively confirms the new version came up before declaring success. If it
  still doesn't show up after a retry, you get a clear message telling you to quit and
  reopen the app yourself, rather than an update bar that spins indefinitely.
- **Fix: the progress text no longer looks like a button while it isn't one.** "Updating…"
  and "Restarting…" now render as plain status text with a spinner — they're not clickable
  while the update is in flight. The button look comes back only when there's actually
  something to click again (an error to retry).
- **Fix: the app never silently starts on a different port than usual.** Previously, if its
  usual port was taken by another program, it would quietly fall back to a different one —
  which broke the installed app shortcut and could leave a dead duplicate behind. Now, if
  the usual port is unavailable, it tells you so in a dialog (naming the port and, when it
  can tell, what's using it) and lets you choose: quit and free it up, or continue once on a
  temporary port. It never makes that choice for you.
- **Fix: a page in the session view now really is the size you chose.** Setting "per page" to,
  say, 5000 used to mean something different depending on how you scrolled: the "↓ Load 100
  more messages" button at the bottom could keep pulling in messages past the 5000 you asked
  for, quietly merging the next page into the one you were reading, and the opposite button at
  the top could do the same going backward. Loading more or earlier messages now always stops
  exactly at the edge of the current page — moving to another page is what Prev/Next (or `[`/`]`)
  are for. And with "Lazy-load long sessions" turned on (the default), a large per-page value no
  longer leaves most of the page sitting behind a button you have to click over and over — the
  rest of the page now fills itself in automatically, a chunk at a time with a loading spinner,
  and stops the moment the full page is on screen. `g`/`Home`/`Shift+G` still take you to the
  session's true first/last message, jumping to the right page first if you're not already on it.

## 4.0.28 — 2026-08-10

The project timeline now lets you choose how many messages a page shows, instead of only
accepting the count through a hand-edited URL.

- **New: a per-page selector on the timeline, with its own saved default.** The timeline has
  always accepted a `lim` URL parameter to control how many merged messages one page shows, but
  there was no control for it in the page itself — you had to edit the address bar by hand. A
  dropdown (50 / 100 / 200 / 500 / 1000 / 2000) now sits next to the sort toggle; changing it
  reloads the timeline at that page size and jumps back to the first page. A 📌 "set as default"
  button next to it saves the current choice as your default for future timeline visits — this is
  a separate setting from the session view's own per-page default, since the two views serve very
  different message counts (a session might be a few hundred messages; a project timeline can run
  into the tens of thousands), so picking a large default for one shouldn't force it onto the
  other. There's deliberately no "show all" option here, unlike the session view — a busy
  project's timeline can be ~70,000 messages, and loading all of them into the browser at once
  would hang the tab. A hand-edited URL with an out-of-range `lim` is still clamped to the same
  2000-message cap the server has always enforced.

## 4.0.27 — 2026-08-10

The project timeline now opens instantly, with an honest "building…" indicator instead of a
blank tab.

- **Fix: opening the timeline on a large project no longer looks frozen.** Merging every session
  in a busy project (hundreds of sessions, tens of thousands of messages) can take several
  seconds the first time — the page used to sit blank while that happened, with no sign anything
  was working. The page now paints immediately (header, project name, sort toggle) with a
  spinner and a plain explanation ("Building this project's timeline — the first open of a large
  project takes a few seconds…"), then fetches the actual message stream in the background and
  fills it in the moment it's ready — the same fetch-and-swap approach the search box already
  uses for its own "Searching…" spinner. If the fetch fails, the placeholder turns into an error
  with a Retry link. Everything on the page — the category filter chips and their digit-key
  shortcuts, the source-session badges, Prev/Next paging and the `[` / `]` shortcuts — keeps
  working once the content lands. Sessions that are already cached (the common case after the
  first open) still fill in almost instantly; the spinner is just honest about the cases where
  it can't be.

- **Fix: one-click "Update & restart" could land the app on a temporary random port and
  create a dead duplicate "installed app."** The updater swaps in the new version while the
  previous one is still shutting down; if the new version tried to take over the usual port
  before the old one had finished exiting, it gave up right away and grabbed whatever random
  port was free instead. The browser saw that random port as a brand-new site, showed the
  first-run "install as app" page again, and — if you clicked through it — created a second,
  permanently broken "installed app" shortcut pointing at a port that would never exist again.
  The app now waits a few seconds for its usual port to free up before giving up on it; if it
  truly can't have that port back, it picks another stable port instead of a random one, says
  so plainly (on the console and with a dismissible note in the app itself), and — while it's
  on that temporary stopgap — won't offer to install itself as an app at all, since doing so is
  exactly what created the broken duplicate in the first place.

## 4.0.26 — 2026-08-10

Read a whole project's conversation history as one story, and narrow a folder search to just
your own messages.

- **New: a project timeline that merges every session in a folder into one chronological
  message stream.** Open it from a folder page ("🕓 Read all messages in one timeline"). Work on
  a project usually spans many separate sessions over days or weeks; picking through them one at
  a time made it hard to follow what actually happened, in order. The timeline weaves every
  session's messages together by real timestamp (a turn with no timestamp of its own — some
  providers omit it on some lines — sorts right next to its own session's neighbours, not
  dumped at one end), sorts newest-first or oldest-first (a visible toggle), and pages through
  the result with classic Prev/Next links (plus `[` / `]`) — no auto-loading on scroll, on
  purpose. Every message uses the exact same rendering as the session view, so the category
  filter chips (🧑 my messages, ✦ agent, ⚠️ errors, ✏️ edits, …) and digit-key shortcuts work
  identically; each message also carries a small badge back to its own session
  (with full context) at that exact point. Each session's messages are cached individually
  (keyed on that session's own file), then merged — so on a project you're actively working in
  right now, a click that lands after Claude Code just wrote a new message only re-reads that
  one session instead of re-parsing the whole folder; paging is otherwise instant.
- **The per-folder search box now has the same scope selector as the main search bar** (🧑 Only
  me / ✦ Only Claude / conversation-only / code / commands), so you can narrow a
  "search this folder only" search to just your own messages without leaving the folder page.

## 4.0.25 — 2026-08-09

Pasting a sentence now lands on the session that actually contains it.

- **Session titles no longer bury the exact match under junk from unrelated sessions.**
  The title-match bonus used to hand out a large, uncapped score for every query word found
  anywhere in a title — including a single Korean particle matched inside an unrelated word
  (e.g. "가" inside "추가"), or a bare digit matched inside a year (e.g. "2" inside "2026") —
  and it counted a repeated query word multiple times. On a real paste with duplicated or
  short words, that could push dozens of irrelevant sessions above the one that genuinely
  contains the pasted text. The title bonus is now distinct-counted (a repeated query word
  counts once), length-floored (single-character terms don't count at all), boundary-aware for
  ASCII/Latin terms (so "app" can't match inside "happy"), and capped in total.
- **A full-coverage, tightly-clustered content match now ranks at phrase level.** When every
  query word lands together in one tight window — the only reason it isn't already an exact
  phrase is usually stray punctuation or markdown emphasis inside the pasted text — it's now
  scored like a near-exact paste instead of the plain, distance-driven cluster band.
- Two supporting content-matching fixes that this uncovered: a bag-of-words match spanning a
  turn split across several physical rows (a message mixing text with tool calls or code
  blocks) no longer looks up a term's position in the wrong sub-row and fabricates a bogus
  zero-span "cluster" out of nothing; and a query with a duplicated word (pasting text that
  repeats a word) can once again land the fast, single-turn exact-coverage match instead of
  being forced into a weaker fallback.
- **Infinite scroll in the session view is gone — replaced with explicit "load more" buttons
  and real Prev/Next paging.** Scrolling to the bottom (or top) of a long session used to
  silently pull in more messages on its own, which felt more surprising than convenient.
  Now nothing loads until you click: "Load 100 more messages" at the bottom, "Load earlier
  messages" at the top, or the classic Prev/Next page links (now also available on the
  default conversation view, not just the filtered one). `g` / `Shift+G` / `Home` / Cmd+Up
  still jump straight to the true top or bottom of a session in one shortcut.
- **In-session search results can now be expanded with 100 messages of context before/after,
  without leaving the search view.** Searching inside a session used to show only the matching
  messages in isolation; each result now has a "▲ Load 100 before" / "▼ Load 100 after" button
  that pulls in the surrounding conversation inline (visually dimmed to distinguish it from the
  actual match), so you can read what led up to or followed a hit without losing your search.

## 4.0.24 — 2026-07-29

The 4.0.22 update-check fix didn't actually work in the field — fixed for real this time,
plus you can now always reach the very top of a long session.

- **Update checks and one-click self-update now really work in the downloadable builds.**
  4.0.22 added a bundled-CA fallback for exactly this, but the fallback never actually ran:
  Python's `urlopen` wraps the certificate error inside a different exception type than the
  one the fallback was watching for, so the check kept failing the same way it always had.
  The new `check_error` reporting from 4.0.22 is what surfaced this — thank you for the
  reports. **Heads up:** if you're on 4.0.22 or 4.0.23, your copy's updater still can't
  download this fix itself — you'll need to grab 4.0.24 manually once from the Releases
  page. Automatic update checks and one-click updates work normally from 4.0.24 on.
- **`g`, `Home`, and Cmd+Up now reach the true first message of a long session.** Opening a
  session deep in (e.g. a search result far from the start) loads a window centered on that
  point rather than the whole file, with a "Load earlier messages" sentinel above it. Pressing
  `g` (or Home, or Cmd+Up) used to just scroll to the top of whatever had loaded so far, and
  then loading more above would push you back down — you could never actually reach the
  start. These now load everything above first (mirroring the Shift+G fix for the bottom),
  then land you on the real first message.

## 4.0.23 — 2026-07-28

Antigravity sessions now show which model (and its effort level — e.g. "Gemini 3.1 Pro
(High)", "Claude Sonnet 4.6 (Thinking)") produced each part of the conversation, with a
visible "Model switch" marker where it changed, parsed from the transcript's
settings-change events.

## 4.0.22 — 2026-07-28

The downloadable app could never actually reach GitHub — fixed, but everyone on 4.0.21 or
older needs one manual download to get there.

- **Update checks and one-click self-update were silently broken in every downloadable
  build.** The PyInstaller-frozen app doesn't carry an OS/venv certificate trust store, so
  every HTTPS call it made (the daily "is there a newer release?" check, and the self-update
  download) failed SSL verification and was quietly swallowed — the app never told you it
  couldn't check, it just never found an update. Only a system-python dev run (which borrows
  the OS's certs) ever actually worked.
- **Fixed by bundling a CA certificate file into the app at build time**, used as a fallback
  when the platform's own trust store comes up empty — the normal path is unchanged, this
  only kicks in when default verification fails.
- **Update-check failures are no longer silent.** `/api/update` now reports a short
  `check_error` when a check fails, instead of just going quiet and reusing stale cache.
- **Heads up:** if you're on 4.0.21 or older, your copy's updater can't download this fix
  itself (that's the bug) — you'll need to grab 4.0.22 manually once from the Releases page.
  Automatic update checks and one-click updates work normally from 4.0.22 on.

## 4.0.21 — 2026-07-21

Session view: per-page and lazy-loading now do what they say, and both are configurable.

- **Per-page = all now really shows all.** Picking a per-page value (e.g. "all" or 50000)
  used to still lazily stream the session in behind the scenes, so a big session could feel
  like it hadn't actually loaded everything. An explicit per-page choice now renders the
  whole window up front — no partial state to second-guess.
- **Shift+G reaches the true end.** In a long, lazily-streamed session, Shift+G used to jump
  only to the bottom of whatever had loaded so far — often nowhere near the real end. It now
  loads every remaining message first (spinner stays visible while it does), then lands on
  the true bottom, in one keypress.
- **Configurable default page size and lazy-loading.** New settings, next to the per-page
  selector in the session view: 📌 "set as default" saves your current per-page choice as the
  default for new sessions, and a "Lazy-load long sessions" checkbox lets you turn incremental
  loading off entirely (or leave it on with "all" as your default for fast opens).

## 4.0.20 — 2026-07-18

Search is faster to *first result*, tells you it's working, and surfaces every spot in a
session — designed and adversarially reviewed with Codex/agy via the AI build-loop protocol.

- **The first search after opening no longer takes ~8 seconds.** It used to bulk-load the
  entire ~450 MB row cache into memory before doing anything. Now each session's parsed
  rows are stored (zlib) right in the FTS DB, so a search deserializes only its handful of
  candidate sessions — measured **~8 s → 10 ms** for a specific query (a broad one loads only
  its candidates, not the whole corpus). Falls back to the classic bulk load only when a
  root has no usable index yet. The background indexer also stopped holding its lock across
  the whole build, so a search during the first index no longer blocks on it.
- **Pressing Enter shows feedback instantly.** The search box was a full-page reload with no
  spinner, so a slow search looked frozen. It now shows a "Searching…" spinner immediately
  and swaps results in without a reload (server returns a bare fragment; the URL, back/
  forward, and reload all still work; the box stays in sync with what's shown).
- **Far-apart matches in one session each get their own link.** When your terms appear in two
  or more places far apart in a session, the result card now shows a jump link for each
  region (up to 3), instead of only the single best spot — so you don't have to open the
  session and hunt for the others.
- **A stray pasted bracket/period no longer zeroes out a search.** Pasting `]Inspired by …
  Marconi.` used to return *nothing*, because the leading `]` glued onto `Inspired` (a token
  that appears nowhere in your history) and every word had to match. Unquoted words now shed
  edge punctuation (`] ( ) " . , ; : ! ?` …) while keeping punctuation *inside* a token
  (`app.py`, `self_update`, `src/app`, `well-known`), so a near-perfect paste still finds the
  passage. Quoted `"phrases"` stay literal.
- **A pasted sentence still finds its passage even with a stray/wrong/junk word.** Pasting a
  sentence with an extra or wrong word — one (`random on the ideas of … Marconi.`) or even
  words that appear *nowhere* (`ran1 ran2 on the ideas of … Marconi.`) — used to jump to the
  wrong turn or return **nothing** (every word had to match). Now the *longest contiguous run*
  of the query words is recognized (for 5+ word queries): it jumps to the pasted passage and
  ranks by how few words are missing, just below an exact-phrase match. Stays fast (the
  trigram index shortlists candidates for these too) and returns identical results with or
  without the fast path.
- **Ranking now scores how tightly your words cluster, not just which tier they fall in.**
  What matters is where the matched words sit **close together** — a block/paragraph — not how
  often they appear scattered across a huge session. Cross-turn matches are now scored by a
  proximity sweep: `(distinct-words-covered)² × 1/(1+distance)`, order-free, with an in-order
  bonus; the jump goes to the densest cluster and up to 3 far-apart clusters each keep their
  own link. One general coverage rule (≥60% of the words, minimum 2) replaces the old magic
  "5-word" gate, so a 2-word and a 13-word query obey the same principle. The candidate index
  stays recall-safe via a pigeonhole OR of the rarest query words (doc-frequency comes from
  the index itself, cached), so results remain identical with the fast path on or off.
- **Result snippets show more context.** Widened from ~150 to ~300 characters, with `…` when
  clipped, so you can read what surrounds the matched keywords instead of just the keywords.
- **App bundle id is now `kr.kdr.ai-session-search`** (was `com.kimdongryeong.ai-session-search`).
  ⚠️ **Existing macOS-app users: this one update can't install itself** — the self-updater only
  swaps a build with the *same* app identity, and the identity changed. **Download this version
  once from [Releases](https://github.com/kim-dongryeong/ai-session-search/releases/latest) and
  reinstall it manually**; automatic updates resume from the next version on. Instead of a raw
  verification error, the in-app updater now detects this case and shows a "Manual reinstall
  needed" notice with a direct download link.

## 4.0.19 — 2026-07-18

- **Specific searches are dramatically faster via a SQLite trigram candidate index.**
  Warm search ran the exact matcher over *every* session in the corpus, so a needle-in-a-
  haystack query paid the same cost as a broad one (and `limit` didn't help — it trims
  *after* the scan). A new `search-v1.sqlite3` in the cache dir holds a session-level
  trigram FTS over the (already-lowercased) session text plus a tiny `session_docs`
  metadata table. Each search shortlists a small **superset** of possible hits and runs the
  exact matcher only on those; the result meta line shows the narrowing (`⚡ 12/67`).
  Measured on real history (67 large Claude sessions): a rare/specific query drops
  **~300 ms → 4–6 ms (30–80×)**, a moderately common one ~2×. A *broad* query that already
  matches most of the corpus sees no narrowing and is marginally slower (the trigram MATCH
  itself has a cost on a big index) — those were never the slow ones you notice. Results are
  **identical** either way (see below); the one-time background build is ~7 min and the
  index is ~2× the row cache on disk.
  - **It's a pure speed layer — identical results, guaranteed.** The trigram index only
    *selects candidates*; the existing matcher (`match_session` / scope / field / snippet)
    still makes every final call. The candidate set is a proven superset: the AND of every
    ≥3-character term/phrase/field-value (a real hit contains all of them) unioned with a
    cheap metadata `LIKE`. A regression test asserts FTS-on and FTS-off return the exact
    same paths and scores across Korean/English/URL/path/phrase/field/negation queries.
  - **Recall-safe by construction.** `case_sensitive 1` on the trigram tokenizer over the
    Python-lowercased blob means normalization is single-sourced (no case-folding
    divergence). Korean substrings work (`검색` inside `검색해줘`) down to 3 chars; queries
    whose only terms are 1–2 chars, or a SQLite without FTS5/trigram/`contentless_delete`,
    transparently **fall back to the classic full scan**.
  - **No stale results even mid-index.** The index is built and refreshed on a background
    thread (keyed on `(mtime_ns, size)`); the request path never writes. Any file whose
    on-disk key differs from the index — brand-new, just-appended, or not-yet-built — is
    force-included in the candidate set and exact-matched from the live transcript, and
    deleted files are dropped by intersecting with the current filesystem. So background
    indexing is a latency optimization, never a correctness precondition. The old gzip row
    cache stays as the fallback; corruption self-heals (drop + rebuild); set the internal
    `_FTS_ENABLED = False` to force the old path.

## 4.0.18 — 2026-07-17

- **One-click "Update & restart" for the macOS app.** The update banner used to only link
  to the download page (drag-install by hand). On the signed + notarized macOS app it now
  shows an **Update & restart** button: confirm once and it downloads the release `.dmg`
  for your architecture, **verifies the signature**, swaps the app in `/Applications`, and
  relaunches into the new version on the same port — the Stats/Shottr-style experience.
  - **Refuses to install anything it can't trust.** Before swapping, the download must pass
    Gatekeeper (`spctl`, i.e. Apple-notarized) *and* be signed by the **same Apple Team and
    bundle id** as the running app. A mismatch aborts the update — a build signed by anyone
    else can never be installed over yours.
  - Reuses the existing replace-on-update handshake for the restart, so the port and the
    single installed PWA stay stable. The pip/pipx install still shows the `pipx upgrade`
    command; other builds still show the manual download link. Fully gated behind the
    loopback-only, token-guarded `/api/self_update` endpoint.

## 4.0.17 — 2026-07-17

- **Pasting a distinctive sentence jumps to where it actually appears.** An unquoted
  multi-word query was split into an AND-of-words and the result jumped to the earliest
  turn where those words *happened* to co-occur — which, for a sentence full of common
  words (`by`, `and`, `the`, `of`, …), was almost never the real occurrence. You'd land
  on an unrelated spot and then page through thousands of messages to find the one you
  meant. Now, when several plain words are given without quotes, a turn that contains
  them verbatim in order is treated as an implicit exact phrase: the jump lands on that
  turn and the session is ranked accordingly. Short queries (< 3 words) and normal
  AND-of-words search are unchanged.
  - **Wrapped pastes still match.** The verbatim check collapses runs of whitespace, so a
    sentence that got line-wrapped or double-spaced in the transcript still counts as the
    exact phrase (the check runs only on turns that already contain every word, so large
    sessions stay fast).
  - **In-session search (🔎 Search this session) uses the same rule** and shows every
    matching turn, so one session surfaces all of its matching spots — not just one.
  - **It says how it read your query.** When no session (or turn) contains the words as an
    exact phrase, a note explains that it fell back to matching the words separately and
    suggests wrapping the text in quotes — so an off-target jump no longer looks like a bug.

- **The conversation view scrolls continuously — no more "Next 1000" clicking.** Jumping to
  a match used to drop you onto a fixed 1000-message page; reading around it, or reaching a
  match on a later page, meant clicking through pages. Now the view is a window that fills in
  as you scroll: forward automatically to the end of the session, earlier on demand (a "↑ Load
  earlier messages" control, also on scroll-up). A jump lands centered in its window, with
  context on both sides. Loading is chunked in the background, so even multi-thousand-message
  sessions stay responsive. The human-only (🧑) filtered view keeps classic paging.

## 4.0.16 — 2026-07-15

- **Updates reliably reclaim the app's port (no more duplicate app windows).** The
  server that must step aside for an update is identified by a shutdown token in a
  single file that any of our servers can overwrite; when it got clobbered, the new
  version couldn't stop the old one, fell back to a random port, and Chrome made yet
  another duplicate app. A relaunch now also reads the running server's live PID from
  `/api/status` and, if the graceful shutdown doesn't free the port, stops that PID —
  but only a process `/api/status` confirms is ours, on loopback, owned by this user. A
  foreign app on the port is still never touched.

## 4.0.15 — 2026-07-15

- **The app is never shown in a browser tab during install.** On the first-run
  install page, finishing the install used to reveal the bare app in that
  browser tab (visible behind Chrome's "Successfully installed" toast) before
  the standalone app window opened. The install page now stays up as a
  "✓ Installed — you can close this tab" screen; the app only ever appears in
  its own window. (The number of Chrome install dialogs is set by Chrome and
  can't be reduced by the page — that flow is unchanged.)

## 4.0.14 — 2026-07-15

- **Updates no longer spawn duplicate app windows.** The local server used to
  fall back to a random port whenever 8777 was busy, and Chrome keys an
  installed app (PWA) by its address — so each random port looked like a brand
  new app: reinstalling piled up `AI Session Search 2.app`, `… 3.app` bundles,
  orphaned the old window, opened a browser tab instead of the app, and re-ran
  the install prompt every time. The app now commits one port for the machine
  (`~/.config/ai-session-search/port`) and reuses it forever — even after the
  other app that was on 8777 quits. First run scans 8777–8792 in order (never
  random); a busy port is only reclaimed if it's our own server (verified via
  `/api/status`), never another app's; updates replace the old server on the
  same port, so the installed app keeps working and no duplicate is created.

## 4.0.13 — 2026-07-14

Measured on 907MB of real history (5 folders, ~300 sessions):

- **Instant start.** The index and search caches now persist to
  `CONFIG_DIR/cache/` and reload on start, revalidated by the same
  (mtime, size) keys — a fresh server (reboot, update, relaunch) no longer
  reparses everything. First page: **53s → 0.1s**; first search: **54s →
  ~10s** (loading the cache) and ~1s afterwards. Demo mode never touches the
  cache; corrupt or old-format cache files are ignored and rebuilt.
- **Faster search.** Relevance counting no longer rescans each matched
  session's full text per term, whole-word scoring uses packed 8-byte token
  hashes instead of ~1.3GB of word sets, and matching runs on blob offsets
  with zero per-query allocations. Warm search: **3.4s → ~1s**.
- **One slow folder can't freeze the app.** A folder whose scan exceeds 2s
  (e.g. a Google Drive mount) serves cached data to requests while a
  background thread refreshes it.
- **Duplicate copies collapse.** A session that exists in several folders
  (e.g. a backup of `~/.claude/projects` added as a folder) now shows once —
  the freshest copy, with a `⧉ n` badge — in lists and search.
- **The session list is paged** (100 cards per page) instead of rendering
  every card at once.

## 4.0.12 — 2026-07-14

- **Large sessions stay responsive while resizing.** A session now shows 1,000 turns per
  page by default instead of eventually inserting as many as 10,000 message cards into
  the DOM. Larger limits and `All` remain available when explicitly selected.
- **The header changes layout only at defined breakpoints.** Its search controls and
  utility buttons use a stable grid instead of independently wrapping whenever a control
  crosses its minimum width. Message cards also isolate their layout and paint work.

## 4.0.11 — 2026-07-14

- **Installed updates now take effect on relaunch.** The detached local server used to
  outlive the app bundle, so a freshly installed version kept opening the old server
  until logout/reboot. A relaunch now checks the running server's version (new local
  `/api/status`) and, on mismatch, replaces it via an authenticated `POST /api/shutdown`
  (per-instance token, loopback-only). Same-version relaunches still reuse the server.
- **'All folders' now treats one workspace as one project across providers.** Claude keys
  projects by folder slug, Codex/Gemini/Antigravity by workspace path; the same folder
  used to show as duplicate rows, and a project filter from one provider dropped the
  others' sessions. Project keys now resolve to the canonical workspace for grouping,
  filtering, and folder-scoped search.

## 4.0.10 — 2026-07-14

- **Completed Claude Code background-agent reports are no longer missing.** Recent
  transcripts may store the full result only in a `queue-operation/enqueue`
  `<task-notification>` instead of a normal assistant turn. The viewer now restores the
  first copy while suppressing the duplicate `attachment` and `remove` mirrors.
- **Agent reports open in full by default.** These substantive results render as Markdown
  without the generic 4,000-character injected-context cap, remain manually collapsible,
  and are included in full-text search and the session API.
- **No more jittery layout while resizing the window.** The header search form, the
  project-stats table, and the Tools panel could force page-level horizontal overflow
  below ~750px; with space-taking scrollbars this made the layout oscillate instead of
  settling. Everything now shrinks or wraps, and wide tables scroll inside their card.
- **The current version is always visible in the header** and links to the release notes.

## 4.0.0 — 2026-07-07

**First public release** — download-and-run native apps, in-app updates, and a demo mode.

- **Native downloadable builds for macOS, Windows, and Linux** — no Python required.
  Grab a file from [Releases](https://github.com/kim-dongryeong/ai-session-search/releases/latest),
  double-click, and it opens in your browser (the server runs locally; nothing is uploaded).
  - **macOS** — a signed + **notarized** `.dmg` (Apple Silicon and Intel) once the signing
    secrets are configured, so Gatekeeper opens it without warnings.
  - **Windows** — a single `.exe`; download and double-click. (Unsigned for now, so
    SmartScreen shows *"Windows protected your PC"* → **More info → Run anyway** — this is
    expected for a new open-source app and safe.)
  - **Linux** — a self-contained `.tar.gz` binary.
  - Built by the `release` workflow (PyInstaller) on every version tag.
- **In-app update notice.** When a newer release exists, a slim bar offers a one-click
  update — a **Download** link in the native app, or a `pipx upgrade` command otherwise.
  Privacy-first: this is the *only* thing the app ever sends over the network — a plain,
  unauthenticated, once-a-day GET of the public GitHub releases endpoint (no identifiers,
  never any transcript content). Turn it off with `AISS_NO_UPDATE_CHECK=1`.
- **`aiss --demo`** — browse a bundled **synthetic** dataset (Claude + Codex + Gemini, with
  tool calls, diffs, thinking, a subagent thread, commits, and a branched session) instead
  of your own history. Great for a first look, and it's what the README/screenshots show —
  so no real data is ever exposed. Fully isolated: `--demo` never touches your real folders.
- Replaced the last piece of vendor artwork (a macOS icon used only in the install
  explainer) with a hand-drawn generic one — the project is now fully self-contained and
  clean for public release.

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
