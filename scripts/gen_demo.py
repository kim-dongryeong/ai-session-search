#!/usr/bin/env python3
"""Generate the bundled demo dataset (synthetic transcripts — no real data).

Writes src/ai_session_search/demo/ with Claude Code, Codex, and Gemini CLI sessions
laid out exactly like the real thing, so `aiss --demo` (and the README/homepage
screenshots) show every feature without touching anyone's private history.

Run:  python3 scripts/gen_demo.py
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "..", "src", "ai_session_search", "demo")
DEMO = os.path.normpath(DEMO)
if os.path.isdir(DEMO):
    shutil.rmtree(DEMO)

OPUS = "claude-opus-4-8"
SONNET = "claude-sonnet-5"


def w(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for o in lines:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")


def usage(i, o, cw=0, cr=0):
    return {"input_tokens": i, "output_tokens": o,
            "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def human(text, cwd, ts, branch="main", forked=None):
    o = {"type": "user", "timestamp": ts, "cwd": cwd, "gitBranch": branch,
         "message": {"role": "user", "content": text}}
    if forked:
        o["forkedFrom"] = {"sessionId": forked, "messageUuid": "m-fork"}
    return o


def asst(cwd, ts, blocks, model=OPUS, u=(120, 90, 400, 8000)):
    return {"type": "assistant", "timestamp": ts, "cwd": cwd, "message": {
        "role": "assistant", "model": model, "usage": usage(*u), "content": blocks}}


def tool(name, tid, **inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def result(tid, content, cwd, ts):
    return {"type": "user", "timestamp": ts, "cwd": cwd, "toolUseResult": content,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": content}]}}


def text(t):
    return {"type": "text", "text": t}


def think(t):
    return {"type": "thinking", "thinking": t}


# ============================ CLAUDE ============================
CLA = os.path.join(DEMO, "claude")
API = "/Users/dev/acme-api"
NOTES = "/Users/dev/notes-app"

# ---- Session A: add Redis rate limiting (acme-api) ----
SID_A = "a1a1a1a1-0001-4a01-8a01-aaaaaaaaaaaa"
slug_api = os.path.join(CLA, "-Users-dev-acme-api")
RL_NEW = (
    "import type { RequestHandler } from 'express';\n"
    "import { createClient } from 'redis';\n\n"
    "const redis = createClient({ url: process.env.REDIS_URL });\n"
    "redis.connect().catch(console.error);\n\n"
    "const LIMIT = 100;          // requests\n"
    "const WINDOW = 60;          // seconds\n\n"
    "export const rateLimit: RequestHandler = async (req, res, next) => {\n"
    "  const key = `rl:${req.ip}`;\n"
    "  const n = await redis.incr(key);\n"
    "  if (n === 1) await redis.expire(key, WINDOW);\n"
    "  res.setHeader('X-RateLimit-Limit', LIMIT);\n"
    "  res.setHeader('X-RateLimit-Remaining', Math.max(0, LIMIT - n));\n"
    "  if (n > LIMIT) return res.status(429).json({ error: 'rate limit exceeded' });\n"
    "  next();\n"
    "};\n"
)
w(os.path.join(slug_api, SID_A + ".jsonl"), [
    {"type": "ai-title", "aiTitle": "Add Redis-backed rate limiting to the API"},
    human("Our public /api endpoints have no rate limiting and we're getting hammered by a "
          "scraper. Can you add a Redis-backed limiter as Express middleware — 100 requests/min "
          "per IP, standard X-RateLimit-* headers — and wire it into the app?",
          API, "2026-06-30T09:14:02Z"),
    asst(API, "2026-06-30T09:14:20Z", [
        think("Plan: a small middleware using Redis INCR + EXPIRE for a fixed 60s window keyed "
              "by IP. INCR returns the new count; set the TTL only on the first hit of a window. "
              "Return 429 past 100. Let me find where middleware is registered first."),
        tool("Grep", "t1", pattern="app\\.use\\(", path="src/app.ts"),
    ], u=(180, 140, 900, 12000)),
    result("t1", "src/app.ts:12:app.use(express.json());\n"
                 "src/app.ts:13:app.use(cors());", API, "2026-06-30T09:14:21Z"),
    asst(API, "2026-06-30T09:14:40Z", [
        tool("Read", "t2", file_path="src/app.ts"),
    ]),
    result("t2", "import express from 'express';\nimport cors from 'cors';\n"
                 "import { router } from './routes';\n\nexport const app = express();\n"
                 "app.use(express.json());\napp.use(cors());\napp.use('/api', router);\n",
           API, "2026-06-30T09:14:41Z"),
    asst(API, "2026-06-30T09:15:10Z", [
        text("I'll add a `rateLimit` middleware and register it before the router."),
        tool("Write", "t3", file_path="src/middleware/rateLimit.ts", content=RL_NEW),
    ], u=(220, 260, 700, 13500)),
    result("t3", "File created: src/middleware/rateLimit.ts (18 lines)", API, "2026-06-30T09:15:11Z"),
    asst(API, "2026-06-30T09:15:30Z", [
        tool("Edit", "t4", file_path="src/app.ts",
             old_string="import { router } from './routes';\n\nexport const app = express();\n"
                        "app.use(express.json());\napp.use(cors());\napp.use('/api', router);",
             new_string="import { router } from './routes';\nimport { rateLimit } from './middleware/rateLimit';\n\n"
                        "export const app = express();\napp.use(express.json());\napp.use(cors());\n"
                        "app.use('/api', rateLimit);\napp.use('/api', router);"),
    ]),
    result("t4", "Applied 1 edit to src/app.ts", API, "2026-06-30T09:15:31Z"),
    asst(API, "2026-06-30T09:15:50Z", [
        tool("Bash", "t5", command="npm test", description="Run the test suite"),
    ]),
    result("t5", "> acme-api@1.4.0 test\n> vitest run\n\n"
                 " ✓ src/routes.test.ts (8 tests) 214ms\n ✓ src/health.test.ts (2 tests) 41ms\n\n"
                 " Test Files  2 passed (2)\n      Tests  10 passed (10)\n", API, "2026-06-30T09:16:12Z"),
    asst(API, "2026-06-30T09:16:30Z", [
        text("Done — the limiter is live and the suite is green.\n\n"
             "- `src/middleware/rateLimit.ts` — Redis `INCR`/`EXPIRE`, fixed 60s window per IP\n"
             "- registered on `/api` **before** the router so it guards every route\n"
             "- emits `X-RateLimit-Limit` / `X-RateLimit-Remaining`, returns `429` past 100\n\n"
             "```ts\nif (n > LIMIT) return res.status(429).json({ error: 'rate limit exceeded' });\n```\n\n"
             "Set `REDIS_URL` in your env; falls back to `redis://localhost:6379`."),
        tool("Bash", "t6", command="git commit -am 'feat(api): Redis-backed rate limiting (100/min per IP)'",
             description="Commit the middleware"),
    ], u=(160, 320, 500, 14000)),
    result("t6", "[main 4f2a1c9] feat(api): Redis-backed rate limiting (100/min per IP)\n"
                 " 2 files changed, 21 insertions(+), 1 deletion(-)", API, "2026-06-30T09:16:45Z"),
    human("nice. one worry — a burst right at the window boundary could let ~200 through. "
          "add a quick test that documents the current behavior so we don't regress.",
          API, "2026-06-30T09:20:03Z"),
    asst(API, "2026-06-30T09:20:30Z", [
        think("They're right about fixed-window burst. For now just pin the behavior with a test "
              "at 100 ok / 101 blocked; note the boundary caveat in a comment."),
        tool("Write", "t7", file_path="src/middleware/rateLimit.test.ts",
             content="import { describe, it, expect } from 'vitest';\n"
                     "import request from 'supertest';\nimport { app } from '../app';\n\n"
                     "describe('rate limit', () => {\n"
                     "  it('allows 100 then blocks the 101st', async () => {\n"
                     "    for (let i = 0; i < 100; i++) await request(app).get('/api/ping');\n"
                     "    const res = await request(app).get('/api/ping');\n"
                     "    expect(res.status).toBe(429);\n"
                     "  });\n});\n"),
    ], u=(140, 210, 600, 15000)),
    result("t7", "File created: src/middleware/rateLimit.test.ts (12 lines)", API, "2026-06-30T09:20:31Z"),
    asst(API, "2026-06-30T09:20:50Z", [
        tool("Bash", "t8", command="npm test", description="Re-run tests"),
    ]),
    result("t8", " ✓ src/middleware/rateLimit.test.ts (1 test) 512ms\n"
                 " Test Files  3 passed (3)\n      Tests  11 passed (11)\n", API, "2026-06-30T09:21:20Z"),
    asst(API, "2026-06-30T09:21:35Z", [
        text("Added `rateLimit.test.ts` (100 OK → 101 = 429) and left a `// fixed window: bursts at "
             "the boundary can exceed the limit` note. Sliding-window is the follow-up if that bites."),
        tool("Bash", "t9", command="git commit -am 'test(api): pin rate-limit behavior'",
             description="Commit the test"),
    ]),
    result("t9", "[main 7b3d0e1] test(api): pin rate-limit behavior\n 1 file changed, 12 insertions(+)",
           API, "2026-06-30T09:21:48Z"),
])

# ---- Session A's subagent: a code review sidechain ----
sub_dir = os.path.join(slug_api, SID_A, "subagents")
w(os.path.join(sub_dir, "agent-review01.jsonl"), [
    {"type": "user", "isSidechain": True, "timestamp": "2026-06-30T09:16:35Z",
     "message": {"role": "user", "content": "You are a senior code reviewer. Review "
                 "src/middleware/rateLimit.ts for correctness and security. Be terse; flag real bugs only."}},
    {"type": "assistant", "isSidechain": True, "timestamp": "2026-06-30T09:16:55Z",
     "message": {"role": "assistant", "model": OPUS, "usage": usage(300, 180),
                 "content": [
                     {"type": "text", "text": "Two things worth noting:\n"
                      "1. **Fixed-window burst** — a client can send ~2×LIMIT across the window edge. "
                      "Fine if documented; sliding window (sorted set) if strict.\n"
                      "2. **Fail-open on Redis down** — `incr` throwing will 500 every request. Consider "
                      "wrapping in try/catch and letting traffic through (or a local fallback) so Redis "
                      "isn't a hard dependency for availability.\n\n"
                      "Correctness of the happy path is fine. `expire` only on first hit is correct."}]}},
])

# ---- Session B: fix flaky test, branched from A (acme-api) ----
SID_B = "b2b2b2b2-0002-4b02-8b02-bbbbbbbbbbbb"
w(os.path.join(slug_api, SID_B + ".jsonl"), [
    {"type": "ai-title", "aiTitle": "Fix the flaky rate-limit test in CI"},
    human("The rate-limit test is flaky in CI — about 1 run in 5 the 429 comes one request early "
          "(100th instead of 101st). Locally it always passes. Track it down and fix it.",
          API, "2026-07-01T11:02:10Z", forked=SID_A),
    asst(API, "2026-07-01T11:02:40Z", [
        think("Flaky + early-by-one + only in CI smells like state bleed between tests: the Redis "
              "counter from a prior test isn't reset, so this test starts at n=1 sometimes. Let me "
              "read the test and see if there's a beforeEach flush."),
        tool("Read", "t1", file_path="src/middleware/rateLimit.test.ts"),
    ], u=(150, 120, 700, 9000)),
    result("t1", "describe('rate limit', () => {\n  it('allows 100 then blocks the 101st', ...)\n"
                 "// no beforeEach — the Redis key persists across test files", API, "2026-07-01T11:02:41Z"),
    asst(API, "2026-07-01T11:03:10Z", [
        tool("Bash", "t2", command="npm test -- --run rateLimit 2>&1 | tail -20",
             description="Reproduce with just this test"),
    ]),
    result("t2", "AssertionError: expected 429 to be 200\n"
                 " ❯ src/middleware/rateLimit.test.ts:8:24\n"
                 "Traceback: key rl:127.0.0.1 already at 1 from health.test.ts\n"
                 " Tests  1 failed (1)", API, "2026-07-01T11:03:40Z"),
    asst(API, "2026-07-01T11:04:00Z", [
        text("Confirmed: it's cross-test state bleed on the shared Redis key, not a limiter bug. "
             "Adding a `beforeEach` that flushes the counter."),
        tool("Edit", "t3", file_path="src/middleware/rateLimit.test.ts",
             old_string="import { app } from '../app';\n\ndescribe('rate limit', () => {",
             new_string="import { app } from '../app';\nimport { redis } from '../middleware/rateLimit';\n\n"
                        "describe('rate limit', () => {\n  beforeEach(async () => { await redis.flushdb(); });"),
    ], u=(140, 160, 600, 10000)),
    result("t3", "Applied 1 edit to src/middleware/rateLimit.test.ts", API, "2026-07-01T11:04:01Z"),
    asst(API, "2026-07-01T11:04:20Z", [
        tool("Bash", "t4", command="for i in 1 2 3 4 5; do npm test -- --run rateLimit; done",
             description="Run 5× to confirm no flake"),
    ]),
    result("t4", "run 1: 1 passed\nrun 2: 1 passed\nrun 3: 1 passed\nrun 4: 1 passed\nrun 5: 1 passed\n"
                 "no flakes in 5 runs", API, "2026-07-01T11:05:30Z"),
    asst(API, "2026-07-01T11:05:45Z", [
        text("Fixed. Root cause was **test isolation**, not the limiter: `health.test.ts` left "
             "`rl:127.0.0.1` at 1, so this test started one ahead. `beforeEach` flushes the DB; "
             "5/5 green now."),
        tool("Bash", "t5", command="git commit -am 'test(api): flush redis between rate-limit tests (fix CI flake)'",
             description="Commit the fix"),
    ]),
    result("t5", "[main 9c4f7a2] test(api): flush redis between rate-limit tests (fix CI flake)\n"
                 " 1 file changed, 2 insertions(+)", API, "2026-07-01T11:05:58Z"),
])

# ---- Session C: scaffold SvelteKit notes app (notes-app, sonnet) ----
SID_C = "c3c3c3c3-0003-4c03-8c03-cccccccccccc"
slug_notes = os.path.join(CLA, "-Users-dev-notes-app")
w(os.path.join(slug_notes, SID_C + ".jsonl"), [
    {"type": "ai-title", "aiTitle": "Scaffold a minimal SvelteKit notes app"},
    human("Scaffold a minimal SvelteKit app in this empty folder: a notes list with add + delete, "
          "persisted to localStorage. No backend, keep it tiny.", NOTES, "2026-07-02T15:40:00Z"),
    asst(NOTES, "2026-07-02T15:40:25Z", [
        text("I'll scaffold SvelteKit (skeleton), then add a notes store backed by localStorage "
             "and a single page with an input + list."),
        tool("Bash", "t1", command="npm create svelte@latest . -- --template skeleton --types ts",
             description="Scaffold SvelteKit skeleton"),
    ], model=SONNET, u=(140, 180, 300, 4000)),
    result("t1", "✔ Which Svelte app template? › Skeleton project\n✔ Add type checking? › TypeScript\n"
                 "Your project is ready! Installed 214 packages.", NOTES, "2026-07-02T15:41:10Z"),
    asst(NOTES, "2026-07-02T15:41:30Z", [
        tool("Write", "t2", file_path="src/lib/notes.ts",
             content="import { writable } from 'svelte/store';\n\n"
                     "const KEY = 'notes';\nconst initial = JSON.parse(localStorage.getItem(KEY) ?? '[]');\n"
                     "export const notes = writable<string[]>(initial);\n"
                     "notes.subscribe((v) => localStorage.setItem(KEY, JSON.stringify(v)));\n"),
    ], model=SONNET),
    result("t2", "File created: src/lib/notes.ts (6 lines)", NOTES, "2026-07-02T15:41:31Z"),
    asst(NOTES, "2026-07-02T15:42:00Z", [
        tool("Write", "t3", file_path="src/routes/+page.svelte",
             content="<script lang=\"ts\">\n  import { notes } from '$lib/notes';\n  let draft = '';\n"
                     "  const add = () => { if (draft.trim()) { $notes = [...$notes, draft.trim()]; draft = ''; } };\n"
                     "  const del = (i: number) => { $notes = $notes.filter((_, j) => j !== i); };\n</script>\n\n"
                     "<h1>Notes</h1>\n<input bind:value={draft} on:keydown={(e) => e.key === 'Enter' && add()} />\n"
                     "<button on:click={add}>Add</button>\n<ul>\n  {#each $notes as n, i}\n"
                     "    <li>{n} <button on:click={() => del(i)}>✕</button></li>\n  {/each}\n</ul>\n"),
    ], model=SONNET, u=(160, 240, 400, 5000)),
    result("t3", "File created: src/routes/+page.svelte (14 lines)", NOTES, "2026-07-02T15:42:01Z"),
    asst(NOTES, "2026-07-02T15:42:30Z", [
        tool("Bash", "t4", command="npm run build", description="Verify it builds"),
    ], model=SONNET),
    result("t4", "vite v5.4.0 building for production...\n✓ 38 modules transformed.\n"
                 "✓ built in 1.83s", NOTES, "2026-07-02T15:42:55Z"),
    asst(NOTES, "2026-07-02T15:43:10Z", [
        text("Scaffolded and building clean. You've got:\n- `src/lib/notes.ts` — a `writable` store "
             "that hydrates from and mirrors to `localStorage`\n- `src/routes/+page.svelte` — add "
             "(Enter or button) + delete, no backend\n\nRun `npm run dev` and it's live at :5173."),
        tool("Bash", "t5", command="git init -q && git add -A && git commit -q -m 'feat: SvelteKit notes app'",
             description="Initial commit"),
    ], model=SONNET),
    result("t5", "[main (root-commit) 1a2b3c4] feat: SvelteKit notes app\n 9 files changed, 240 insertions(+)",
           NOTES, "2026-07-02T15:43:25Z"),
])

# ============================ CODEX ============================
COD = os.path.join(DEMO, ".codex", "sessions", "2026", "07", "03")
SID_CODEX = "d4d4d4d4-0004-4d04-8d04-dddddddddddd"
w(os.path.join(COD, f"rollout-2026-07-03T10-30-00-{SID_CODEX}.jsonl"), [
    {"type": "session_meta", "timestamp": "2026-07-03T10:30:00Z", "payload": {
        "id": SID_CODEX, "cwd": API, "model_provider": "openai",
        "cli_version": "0.41.0", "originator": "cli"}},
    {"type": "turn_context", "payload": {"model": "gpt-5.3-codex"}},
    {"type": "response_item", "timestamp": "2026-07-03T10:30:05Z", "payload": {
        "type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "The GET /api/search endpoint gets slow (~800ms) on the "
             "big fixtures. Profile it and speed it up without changing the response shape."}]}},
    {"type": "response_item", "timestamp": "2026-07-03T10:30:20Z", "payload": {
        "type": "reasoning", "summary": [
            {"type": "summary_text", "text": "First measure, don't guess. Run the bench harness with "
             "the node profiler and see where the time goes — I suspect a linear scan over all rows "
             "per query instead of an index."}]}},
    {"type": "response_item", "timestamp": "2026-07-03T10:30:35Z", "payload": {
        "type": "function_call", "call_id": "c1", "name": "exec_command",
        "arguments": json.dumps({"cmd": ["node", "--prof", "bench/search.js"], "workdir": API})}},
    {"type": "response_item", "timestamp": "2026-07-03T10:30:52Z", "payload": {
        "type": "function_call_output", "call_id": "c1",
        "output": "search x1000: 812ms avg\nhot path: 71% in linearScan() at src/search.ts:44\n"
                  "  (filters the full 50k-row array on every request)"}},
    {"type": "response_item", "timestamp": "2026-07-03T10:31:10Z", "payload": {
        "type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "The profiler confirms it: 71% of the time is a full "
             "linear scan of the 50k-row array per request. I'll build an inverted index of "
             "token → row-ids once at load and intersect posting lists per query. Same results, "
             "O(matches) instead of O(rows)."}]}},
    {"type": "response_item", "timestamp": "2026-07-03T10:31:40Z", "payload": {
        "type": "function_call", "call_id": "c2", "name": "exec_command",
        "arguments": json.dumps({"cmd": ["npm", "run", "bench"], "workdir": API})}},
    {"type": "response_item", "timestamp": "2026-07-03T10:32:05Z", "payload": {
        "type": "function_call_output", "call_id": "c2",
        "output": "search x1000: 24ms avg  (was 812ms — 34× faster)\nall 11 tests still passing"}},
    {"type": "response_item", "timestamp": "2026-07-03T10:32:20Z", "payload": {
        "type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "Done. Built a token→row-id inverted index at load time "
             "and swapped the per-request `linearScan` for posting-list intersection. **812ms → 24ms "
             "(~34×)**, identical output, tests green. Index build adds ~40ms to startup, amortized "
             "across all requests."}]}},
])

# ============================ GEMINI ============================
GEM = os.path.join(DEMO, ".gemini", "tmp", "notes-app", "chats")
SID_GEM = "e5e5e5e5-0005-4e05-8e05-eeeeeeeeeeee"
w(os.path.join(GEM, f"session-2026-07-04-{SID_GEM}.jsonl"), [
    {"sessionId": SID_GEM, "projectHash": "notes-app", "startTime": "2026-07-04T14:00:00Z", "kind": "main"},
    {"type": "user", "content": [{"text": "Add a dark-mode toggle to the notes app that persists "
     "the choice to localStorage and respects prefers-color-scheme on first visit."}]},
    {"type": "gemini", "model": "gemini-3-flash-preview",
     "thoughts": [
         {"subject": "Approach", "description": "Store theme in a Svelte store backed by "
          "localStorage; default to matchMedia('(prefers-color-scheme: dark)'). Toggle a "
          "data-theme attribute on <html> and key the CSS off it."},
         {"subject": "Scope", "description": "One store + a button in +layout.svelte + a few CSS "
          "variables. Keep it dependency-free."}],
     "content": "I added a `theme` store that seeds from `localStorage` (falling back to the OS "
                "preference), toggles `data-theme` on `<html>`, and a ☾/☀ button in the layout. "
                "CSS variables switch on `:root[data-theme=\"dark\"]`. Verified the build.",
     "toolCalls": [
         {"name": "run_shell_command", "args": {"command": "npm run build"},
          "result": [{"functionResponse": {"response": {"output": "✓ built in 1.71s — 39 modules"}}}]}],
     "tokens": {"input": 1180, "output": 340, "cached": 200, "thoughts": 90, "tool": 30, "total": 1840}},
    {"type": "user", "content": [{"text": "great, ship it"}]},
    {"type": "gemini", "model": "gemini-3-flash-preview",
     "content": "Committed as `feat: dark-mode toggle (persisted, respects OS preference)`. 🌙",
     "toolCalls": [
         {"name": "run_shell_command", "args": {"command": "git commit -am 'feat: dark-mode toggle'"},
          "result": [{"functionResponse": {"response": {"output": "[main 5e6f7a8] feat: dark-mode toggle\n 3 files changed, 34 insertions(+)"}}}]}],
     "tokens": {"input": 640, "output": 90, "cached": 400, "thoughts": 0, "tool": 20, "total": 750}},
])


def _set_mtimes():
    """Set each transcript's mtime to its latest in-content timestamp, so the index
    shows realistic dates instead of 'generated just now'."""
    import datetime as _dt

    def parse(s):
        try:
            return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    for r, _, fs in os.walk(DEMO):
        for f in fs:
            if not f.endswith(".jsonl"):
                continue
            p = os.path.join(r, f)
            best = None
            with open(p, encoding="utf-8") as fh:
                for ln in fh:
                    try:
                        o = json.loads(ln)
                    except ValueError:
                        continue
                    for key in ("timestamp", "startTime"):
                        ts = parse(o.get(key, "")) if isinstance(o.get(key), str) else None
                        if ts and (best is None or ts > best):
                            best = ts
            if best:
                os.utime(p, (best, best))


_set_mtimes()

if __name__ == "__main__":
    total = sum(1 for r, _, fs in os.walk(DEMO) for f in fs if f.endswith(".jsonl"))
    print(f"demo written to {DEMO}  ({total} transcript files)")
