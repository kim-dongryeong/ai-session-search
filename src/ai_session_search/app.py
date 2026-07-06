#!/usr/bin/env python3
"""Claude Code transcript viewer — stdlib only, read-only.

Correctly attributes WHO said what (audited + adversarially verified ruleset for the
Claude Code JSONL schema). Only genuine human-typed text is labelled "You"; tool
results, reasoning, tool calls, system/IDE injections, slash-command output,
task-notifications, autonomous build-loop prompts, and subagent threads are each their
own category, folded by default.

Features: session index (titles, project filter, sort), full-text search (all / my-only),
per-message timestamps, "my messages only" filter, answer-thread links, subagent thread
expansion, j/k keyboard nav + "/" search focus, configurable page size + render timing,
event/error chips, structure minimap, per-session extracted-fact digest, code/diff
extraction with copy, per-project stats, in-app folder add/remove.

Usage:
    ai-session-search [PROJECTS_DIR] [--port 8777] [--open]
    python3 -m ai_session_search [PROJECTS_DIR] [--port 8777]

Defaults to $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects.
"""
import argparse
import datetime
import difflib
import glob
import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

__version__ = "3.0.0"

# App icon — a speech bubble with a person mark (🧑 = "you"), the app's core idea.
# One SVG, used as favicon and (rasterized by tooling) as the app icon.
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#1f6feb"/>
<path d="M14 16h36a6 6 0 0 1 6 6v20a6 6 0 0 1-6 6H30l-11 9v-9h-5a6 6 0 0 1-6-6V22a6 6 0 0 1 6-6z" fill="#fff"/>
<circle cx="32" cy="29" r="6" fill="#1f6feb"/>
<path d="M21 43c0-6 5-9 11-9s11 3 11 9z" fill="#1f6feb"/>
</svg>"""

# Illustration: macOS ⌘-Tab switcher with OUR app highlighted (shown in the install modal)
SVG_CMDTAB = """<svg viewBox="0 0 360 142" class=illsvg xmlns="http://www.w3.org/2000/svg" role=img aria-label="Command-Tab app switcher">
<rect x="8" y="20" width="344" height="74" rx="18" fill="#33363e"/>
<rect x="30" y="38" width="40" height="40" rx="9" fill="#71767f"/>
<rect x="94" y="38" width="40" height="40" rx="9" fill="#71767f"/>
<rect x="152" y="31" width="56" height="56" rx="14" fill="none" stroke="#fff" stroke-width="2.5"/>
<rect x="160" y="38" width="40" height="40" rx="9" fill="#1f6feb"/>
<path d="M167 49h26a3 3 0 0 1 3 3v11a3 3 0 0 1-3 3h-11l-7 5v-5h-8a3 3 0 0 1-3-3V52a3 3 0 0 1 3-3z" fill="#fff"/>
<rect x="226" y="38" width="40" height="40" rx="9" fill="#71767f"/>
<rect x="290" y="38" width="40" height="40" rx="9" fill="#71767f"/>
<rect x="116" y="110" width="50" height="24" rx="6" fill="#e7e9ec" stroke="#c7ccd2"/>
<text x="141" y="127" text-anchor="middle" font-size="14" fill="#333">&#8984;</text>
<rect x="172" y="110" width="66" height="24" rx="6" fill="#e7e9ec" stroke="#c7ccd2"/>
<text x="205" y="127" text-anchor="middle" font-size="12" fill="#333">tab &#8677;</text>
</svg>"""

# Illustration: a browser window with the extensions (puzzle) button — extensions still work
SVG_EXT = """<svg viewBox="0 0 360 116" class=illsvg xmlns="http://www.w3.org/2000/svg" role=img aria-label="Chrome extensions still work">
<rect x="14" y="10" width="332" height="96" rx="12" fill="#fff" stroke="#d7dbe0"/>
<circle cx="36" cy="32" r="5" fill="#ff5f57"/><circle cx="52" cy="32" r="5" fill="#febc2e"/><circle cx="68" cy="32" r="5" fill="#28c840"/>
<rect x="88" y="22" width="176" height="20" rx="10" fill="#eef1f4"/>
<text x="99" y="36" font-size="11" fill="#8a8f98">127.0.0.1</text>
<rect x="278" y="20" width="28" height="24" rx="6" fill="#dbe5ff" stroke="#1f6feb"/>
<text x="292" y="38" text-anchor="middle" font-size="15">&#129513;</text>
<circle cx="324" cy="32" r="9" fill="#34a853"/>
<rect x="30" y="60" width="150" height="10" rx="5" fill="#dfe3e8"/>
<rect x="30" y="78" width="256" height="8" rx="4" fill="#eef1f4"/>
<rect x="30" y="92" width="196" height="8" rx="4" fill="#eef1f4"/>
</svg>"""

# ---- config -----------------------------------------------------------------
DEFAULT_PORT = 8777
if os.name == "nt":
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ai-session-search")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/ai-session-search")
ROOTS_FILE = os.path.join(CONFIG_DIR, "roots.txt")
_ROOTLOCK = threading.Lock()

# ---- i18n -------------------------------------------------------------------
# The UI is authored in English; the English string is its own translation key.
# tr(s) returns the active language's translation of s, or s unchanged (English).
# Ship a language by dropping <code>.json ({ "English text": "translation" }) into
# the package's locales/ dir, or into <CONFIG_DIR>/locales/ (user-added, no rebuild).
LOCALES = {}                      # {"ko": {english: translated, ...}, ...}
_LANG = threading.local()
_DEFAULT_LANG = "en"              # overridable via --lang / CCH_LANG

def load_locales():
    LOCALES.clear()
    dirs = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")]
    mp = getattr(sys, "_MEIPASS", None)           # PyInstaller bundle
    if mp:
        dirs += [os.path.join(mp, "ai_session_search", "locales"), os.path.join(mp, "locales")]
    dirs.append(os.path.join(CONFIG_DIR, "locales"))
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            code = os.path.basename(f)[:-5]
            if code == "en":
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    LOCALES.setdefault(code, {}).update(
                        {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)})
            except Exception:
                pass

def available_langs():
    return ["en"] + sorted(LOCALES)

def set_lang(code):
    _LANG.code = code if code in LOCALES else "en"

def cur_lang():
    return getattr(_LANG, "code", None) or _DEFAULT_LANG

def tr(s):
    """Translate an English UI string to the active language (or return it as-is)."""
    code = cur_lang()
    return LOCALES.get(code, {}).get(s, s) if code != "en" else s

# Mutable app state; populated by configure(). Import has no side effects.
ROOT = ""
ROOTS = []
DEFAULT_ROOTS = []
SAVED_ROOTS = []

def default_primary_root():
    """Standard Claude Code projects dir, honoring CLAUDE_CONFIG_DIR."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return os.path.join(os.path.expanduser(cfg), "projects")
    return os.path.expanduser(os.path.join("~", ".claude", "projects"))

def _discover_roots(primary, extra_roots=()):
    """Auto-discovered roots: primary, the standard locations, Codex, and any extras."""
    cands = [primary, default_primary_root(),
             os.path.expanduser(os.path.join("~", "Downloads", ".claude", "projects")),
             os.path.expanduser(os.path.join("~", ".codex", "sessions")),   # Codex
             os.path.expanduser(os.path.join("~", ".gemini", "tmp"))]       # Gemini CLI
    cands += [p for p in extra_roots if p]
    seen = []
    for c in cands:
        c = os.path.abspath(os.path.expanduser(c))
        if os.path.isdir(c) and c not in seen:
            seen.append(c)
    return seen or [os.path.abspath(os.path.expanduser(primary))]

def _load_saved():
    out = []
    try:
        with open(ROOTS_FILE, encoding="utf-8") as fh:
            for ln in fh:
                p = ln.strip()
                if p and os.path.isdir(p):
                    out.append(os.path.abspath(p))
    except OSError:
        pass
    return out

def _save_saved(extra):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(ROOTS_FILE, "w", encoding="utf-8") as fh:
            fh.write("".join(p + "\n" for p in extra))
    except OSError:
        pass

def normalize_root(path):
    """Resolve a user-given path to a usable projects root (has */*.jsonl), or None.
    Accepts the projects dir itself, a parent containing projects/, or a .claude dir."""
    if not path:
        return None
    p = os.path.abspath(os.path.expanduser(path.strip()))
    if not os.path.isdir(p):
        return None
    for cand in (p, os.path.join(p, "projects"), os.path.join(p, ".claude", "projects")):
        if os.path.isdir(cand) and glob.glob(os.path.join(cand, "*", "*.jsonl")):
            return cand
    return None

def configure(primary_root=None, extra_roots=()):
    """(Re)initialize app state. Called by main(); tests call it directly."""
    global ROOT, ROOTS, DEFAULT_ROOTS, SAVED_ROOTS
    primary = os.path.abspath(os.path.expanduser(primary_root or default_primary_root()))
    DEFAULT_ROOTS = _discover_roots(primary, extra_roots)
    SAVED_ROOTS = [p for p in _load_saved() if p not in DEFAULT_ROOTS]
    ROOTS = list(DEFAULT_ROOTS)
    for p in SAVED_ROOTS:
        if p not in ROOTS:
            ROOTS.append(p)
    ROOT = primary if primary in ROOTS else ROOTS[0]
    load_locales()
    with _INDEX["lock"]:
        _INDEX["by_root"].clear()
    with _SEARCH["lock"]:
        _SEARCH["by_path"].clear()
    with _SESSION["lock"]:
        _SESSION["by_path"].clear()
    return ROOT

def root_for_path(p):
    """Which allowed root contains p (so session links work regardless of active root).
    Uses realpath so an in-root symlink can't point reads outside the allowed roots."""
    ap = os.path.realpath(p or "")
    for r in ROOTS:
        try:
            if os.path.commonpath([ap, os.path.realpath(r)]) == os.path.realpath(r):
                return r
        except ValueError:
            pass
    return None

def active_root(v):
    return v if v in ROOTS else ROOT
DEFAULT_LIM = 500
LIM_OPTIONS = [100, 250, 500, 1000, 2000, 5000, 10000]

ANSI = re.compile(r"\x1b\[[0-9;]*m")
INJECT_PREFIXES = ("<ide_opened_file>", "<ide_selection>", "<system-reminder>", "<command-", "<task-notification>")
STRING_INJECT_PREFIXES = ("<task-notification>", "<command-name>", "<local-command-stdout>",
                          "<local-command-stderr>", "<system-reminder>", "<local-command-caveat>",
                          "<ide_opened_file>", "<ide_selection>", "Caveat:")
LOOP_PREFIXES = ("You are CLAUDE in an AUTONOMOUS", "You are in the Codex×Claude×agy build loop")
# Codex (~/.codex/sessions/**/rollout-*.jsonl) — a `role:user` message starting with any
# of these is injected context, NOT the human (same precision-first rule as Claude Code).
CODEX_INJECT_PREFIXES = ("# Context from my IDE setup:", "<environment_context>",
                         "# AGENTS.md instructions for", "The following is the Codex agent history",
                         "<turn_aborted>", "<skill>", "# In app browser:",
                         "<user_instructions>", "<permissions instructions>")
_CODEX_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

def provider_of(path):
    """Which agent wrote this transcript, from its path/filename."""
    q = (path or "").replace(os.sep, "/")
    b = os.path.basename(q)
    if "/.codex/" in q or b.startswith("rollout-"):
        return "codex"
    if "/.gemini/" in q or b.startswith("session-"):
        return "gemini"
    return "claude"

def _codex_sid(path):
    m = _CODEX_UUID.search(os.path.basename(path))
    return m.group(0) if m else os.path.basename(path)[:-6]
SKIP_TYPES = {"mode", "permission-mode", "file-history-snapshot", "queue-operation",
              "agent-name", "started", "result", "fork-context-ref", "attachment", "system"}
TITLE_TYPES = {"ai-title", "custom-title", "last-prompt", "summary"}

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Update", "str_replace_editor", "create_file", "apply_patch"}
TEST_RE = re.compile(r"\b(pytest|jest|vitest|mocha|npm (run )?test|yarn test|pnpm test|go test|cargo test|rspec|phpunit|unittest|ctest|gradle test|mvn test)\b", re.I)
ERR_RE = re.compile(r"\b(Traceback|Exception|FAILED|fatal:|panic:)\b|exit code [1-9]|command not found|is not recognized|: error:|Error:", re.I)
URL_RE = re.compile(r"https?://[^\s)\]<>\"']+")
COMMIT_RE = re.compile(r"git commit")
COMMIT_MSG_RE = re.compile(r"-m\s+[\"']([^\"']+)[\"']")
CODE_FENCE_RE = re.compile(r"```([\w.+-]*)\n(.*?)```", re.S)

def parse_lim(v):
    if v in ("all", "0", "-1"):
        return None
    try:
        n = int(v)
        return n if n > 0 else DEFAULT_LIM
    except Exception:
        return DEFAULT_LIM

# ---- jsonl ------------------------------------------------------------------
def iter_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue

# ---- classification (audited + verified ruleset) ----------------------------
def fmt_tool_use(b):
    inp = b.get("input", {})
    try:
        inp = json.dumps(inp, ensure_ascii=False, indent=2)
    except Exception:
        inp = str(inp)
    return f"{b.get('name','tool')}\n{inp}"

def tool_result_text(o):
    tur = o.get("toolUseResult")
    if tur is not None:
        if isinstance(tur, str):
            return ANSI.sub("", tur)
        try:
            return json.dumps(tur, ensure_ascii=False, indent=2)
        except Exception:
            return str(tur)
    content = (o.get("message") or {}).get("content")
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                out.append(str(c or ""))
    return ANSI.sub("", "\n".join(out) or str(content or ""))

def user_text(o):
    content = (o.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""

_CHANNEL_RE = re.compile(r'^\s*<channel\s+([^>]*?)>\n?(.*?)\n?</channel>\s*$', re.S)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')

def parse_channel(text):
    """'<channel source=… user=…>\\nbody\\n</channel>' → (attrs_dict, body) or None.
    These are human messages relayed into the session by a channel plugin (Telegram/…)."""
    m = _CHANNEL_RE.match(text or "")
    if not m:
        return None
    return dict(_ATTR_RE.findall(m.group(1))), m.group(2)

_CHANNEL_NAMES = [("telegram", "Telegram"), ("slack", "Slack"), ("discord", "Discord"),
                  ("whatsapp", "WhatsApp"), ("sms", "SMS"), ("email", "Email")]

def channel_label(attrs):
    src = (attrs.get("source") or "").lower()
    name = next((nm for key, nm in _CHANNEL_NAMES if key in src), "Channel")
    user = attrs.get("user") or attrs.get("user_id") or ""
    return f"💬 {esc(tr(name))}" + (f" · @{esc(user)}" if user else "")

def classify_line(o, sub=False):
    t = o.get("type")
    if t in TITLE_TYPES or t in SKIP_TYPES:
        return None
    msg = o.get("message") or {}
    content = msg.get("content")

    if t == "assistant" and o.get("isApiErrorMessage"):
        return ("system", [("injected", str(content))])
    if o.get("isSidechain") and not sub:
        return ("subagent", [("text", user_text(o) or str(content))])

    if t == "assistant":
        segs = []
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "thinking":
                    segs.append(("thinking", b.get("thinking", "") or ""))
                elif bt == "tool_use":
                    segs.append(("tool_use", fmt_tool_use(b)))
                elif bt == "text" and b.get("text", "").strip():
                    segs.append(("text", b["text"]))
                elif bt == "fallback":
                    segs.append(("injected", f"{tr('Model switch')} {b.get('from',{}).get('model','?')} → {b.get('to',{}).get('model','?')}"))
        elif isinstance(content, str) and content.strip():
            segs.append(("text", content))
        return ("assistant", segs) if segs else None

    if t == "user":
        you_role = "orchestrator" if sub else "you"
        # channel-relayed human message (Telegram/Slack/… plugin). The harness flags
        # these isMeta/promptSource=system, but they are genuine person-authored text —
        # keep them out of the system/injected bucket and show who sent them.
        chan = content if isinstance(content, str) else (
            next((b.get("text", "") for b in content
                  if isinstance(b, dict) and b.get("type") == "text"), "")
            if isinstance(content, list) else "")
        if chan.lstrip().startswith("<channel ") and parse_channel(chan):
            return ("channel", [("channel", chan)])
        has_block = isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
        if o.get("toolUseResult") is not None or has_block:
            return ("tool-result", [("tool_result", tool_result_text(o))])
        if o.get("isMeta") or o.get("isCompactSummary") or o.get("promptSource") == "system":
            return ("system", [("injected", user_text(o))])
        if isinstance(content, str):
            s = content.lstrip()
            if s.startswith(STRING_INJECT_PREFIXES) or s.startswith(LOOP_PREFIXES):
                return ("system", [("injected", content)])
            return (you_role, [("text", content)]) if content.strip() else None
        if isinstance(content, list):
            human, markers = [], []
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text", "")
                    if txt.lstrip().startswith(INJECT_PREFIXES):
                        markers.append(txt)
                    else:
                        human.append(("text", txt))
                elif bt == "image":
                    human.append(("text", tr("🖼️ [pasted image]")))
            if human:
                first = next((x[1] for x in human if x[0] == "text"), "").lstrip()
                if first.startswith(LOOP_PREFIXES) and not sub:
                    return ("system", [("injected", "\n".join(x[1] for x in human))])
                segs = list(human)
                if markers:
                    segs.append(("injected", "\n".join(markers)))
                return (you_role, segs)
            if markers:
                return ("system", [("injected", "\n".join(markers))])
    return None

# ---- event tagging ----------------------------------------------------------
def turn_tags(o, role, segs):
    tags = set()
    for kind, txt in segs:
        if kind == "tool_use":
            name = txt.split("\n", 1)[0].strip()
            if name in EDIT_TOOLS:
                tags.add("edit")
            if name in ("Bash", "exec_command", "shell", "local_shell", "run_shell_command"):
                tags.add("command")
                if COMMIT_RE.search(txt):
                    tags.add("commit")
                if TEST_RE.search(txt):
                    tags.add("test")
            if name in ("WebFetch", "WebSearch"):
                tags.add("web")
            if URL_RE.search(txt):
                tags.add("url")
        elif kind == "tool_result":
            if ERR_RE.search(txt):
                tags.add("error")
            if URL_RE.search(txt):
                tags.add("url")
        elif kind == "text":
            if URL_RE.search(txt):
                tags.add("url")
    tur = o.get("toolUseResult")
    if isinstance(tur, dict):
        if tur.get("is_error") or tur.get("isError"):
            tags.add("error")
        ec = tur.get("exit_code", tur.get("exitCode"))
        if isinstance(ec, int) and ec != 0:
            tags.add("error")
    content = (o.get("message") or {}).get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                tags.add("error")
    return tags

def classify_turns(path, sub=False):
    prov = provider_of(path)
    if prov == "codex":
        return _codex_load(path)["turns"]
    if prov == "gemini":
        return _gemini_load(path)["turns"]
    out = []
    for o in iter_lines(path):
        r = classify_line(o, sub)
        if r:
            turn = {"role": r[0], "segs": r[1], "ts": o.get("timestamp", ""),
                    "tags": turn_tags(o, r[0], r[1])}
            if o.get("type") == "assistant":
                msg = o.get("message") or {}
                turn["model"] = msg.get("model", "")
                turn["tok"] = usage_tok(msg.get("usage"))
            out.append(turn)
    return out

# ---- Codex transcript support (~/.codex/sessions/**/rollout-*.jsonl) ----------
def classify_codex_line(o):
    """Map one Codex response_item to (role, segs). Ignores event_msg mirrors."""
    if o.get("type") != "response_item":
        return None
    pl = o.get("payload") or {}
    pt = pl.get("type")
    if pt == "message":
        role = pl.get("role")
        text = "\n".join(x.get("text", "") for x in pl.get("content", []) or []
                         if isinstance(x, dict) and x.get("text"))
        if not text.strip():
            return None
        if role == "assistant":
            return ("assistant", [("text", text)])
        if role == "developer":
            return ("system", [("injected", text)])
        if role == "user":
            s = text.lstrip()
            if s.startswith(CODEX_INJECT_PREFIXES) or s.startswith(LOOP_PREFIXES):
                return ("system", [("injected", text)])
            return ("you", [("text", text)])
        return None
    if pt == "reasoning":
        summ = "\n".join(x.get("text", "") for x in pl.get("summary", []) or []
                         if isinstance(x, dict) and x.get("text"))
        return ("assistant", [("thinking", summ)])
    if pt in ("function_call", "custom_tool_call"):
        args = pl.get("arguments")
        if args is None:
            args = pl.get("input", "")
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        return ("assistant", [("tool_use", f"{pl.get('name', 'tool')}\n{args}")])
    if pt in ("function_call_output", "custom_tool_call_output"):
        out = pl.get("output")
        if isinstance(out, (dict, list)):
            out = json.dumps(out, ensure_ascii=False)
        return ("tool-result", [("tool_result", str(out or ""))])
    if pt == "web_search_call":
        return ("assistant", [("tool_use", "WebSearch\n" + json.dumps(pl.get("action") or {}, ensure_ascii=False))])
    return None

def _codex_load(path):
    """One pass over a Codex rollout file → {turns, meta} (same shape as Claude)."""
    cwd = model = last_ts = first_human = ""
    n = {"you": 0, "assistant": 0, "tool-result": 0, "system": 0, "subagent": 0}
    turns = []
    for o in iter_lines(path):
        t = o.get("type")
        if t == "session_meta":
            pl = o.get("payload") or {}
            cwd = pl.get("cwd", cwd) or cwd
            model = model or pl.get("model") or ""
        elif t == "turn_context" and not model:
            model = (o.get("payload") or {}).get("model") or ""
        if o.get("timestamp"):
            last_ts = o["timestamp"]
        r = classify_codex_line(o)
        if not r:
            continue
        role, segs = r
        turn = {"role": role, "segs": segs, "ts": o.get("timestamp", ""), "tags": turn_tags(o, role, segs)}
        if role == "assistant" and model:
            turn["model"] = model
        turns.append(turn)
        if role in n:
            n[role] += 1
        if role == "you" and not first_human:
            first_human = " ".join(x[1] for x in segs if x[0] == "text").strip()
    title = (first_human or (os.path.basename(cwd) if cwd else "") or tr("(untitled)")).strip()[:120]
    meta = {"title": title, "preview": first_human.strip()[:140], "n": n, "last_ts": last_ts,
            "cwd": cwd, "start_cwd": cwd, "branch": "", "forked": "", "loop": False,
            "tok": {"in": 0, "out": 0, "cw": 0, "cr": 0}, "models": ({model: 1} if model else {})}
    return {"turns": turns, "meta": meta}

# ---- Gemini CLI support (~/.gemini/tmp/<project>/chats/session-*.jsonl) --------
_GEMINI_PROJMAP = {"v": None}

def _gemini_projmap():
    """{project-name → real workspace path} from ~/.gemini/projects.json (cached)."""
    if _GEMINI_PROJMAP["v"] is None:
        m = {}
        try:
            with open(os.path.expanduser("~/.gemini/projects.json"), encoding="utf-8") as fh:
                for realpath, name in (json.load(fh).get("projects") or {}).items():
                    m[name] = realpath
        except Exception:
            pass
        _GEMINI_PROJMAP["v"] = m
    return _GEMINI_PROJMAP["v"]

def _gemini_projname(path):
    q = path.replace(os.sep, "/")
    return q.split("/tmp/", 1)[1].split("/")[0] if "/tmp/" in q else ""

def _gemini_sid(path):
    try:
        with open(path, encoding="utf-8") as fh:
            o = json.loads(fh.readline() or "{}")
        if o.get("sessionId"):
            return o["sessionId"]
    except Exception:
        pass
    m = re.search(r"session-.*-([0-9a-f]{6,})\.jsonl$", os.path.basename(path))
    return m.group(1) if m else os.path.basename(path)[:-6]

def classify_gemini_line(o):
    t = o.get("type")
    if t == "user":
        c = o.get("content")
        text = c if isinstance(c, str) else ("\n".join(
            x.get("text", "") for x in c if isinstance(x, dict) and x.get("text")) if isinstance(c, list) else "")
        return ("you", [("text", text)]) if text.strip() else None
    if t == "gemini":
        segs = []
        th = "\n\n".join(f'{x.get("subject", "")}: {x.get("description", "")}'.strip(": ")
                         for x in (o.get("thoughts") or []) if isinstance(x, dict))
        if th.strip():
            segs.append(("thinking", th))
        content = o.get("content")
        if isinstance(content, str) and content.strip():
            segs.append(("text", content))
        for tc in o.get("toolCalls") or []:
            if not isinstance(tc, dict):
                continue
            segs.append(("tool_use", f"{tc.get('name', 'tool')}\n{json.dumps(tc.get('args') or {}, ensure_ascii=False)}"))
            outs = []
            for r in tc.get("result") or []:
                fr = r.get("functionResponse") if isinstance(r, dict) else None
                if fr and isinstance(fr.get("response"), dict) and fr["response"].get("output") is not None:
                    outs.append(str(fr["response"]["output"]))
            if not outs and tc.get("resultDisplay"):
                outs.append(str(tc["resultDisplay"]))
            if outs:
                segs.append(("tool_result", "\n".join(outs)))
        return ("assistant", segs) if segs else None
    if t == "info":
        return ("system", [("injected", str(o.get("content", "")))])
    return None

def _gemini_load(path):
    cwd = _gemini_projmap().get(_gemini_projname(path), "") or _gemini_projname(path)
    model = last_ts = first_human = ""
    n = {"you": 0, "assistant": 0, "tool-result": 0, "system": 0, "subagent": 0}
    tok = {"in": 0, "out": 0, "cw": 0, "cr": 0}
    models = {}
    turns = []
    for o in iter_lines(path):
        if o.get("timestamp"):
            last_ts = o["timestamp"]
        if o.get("type") == "gemini":
            if o.get("model"):
                model = model or o["model"]
                models[o["model"]] = models.get(o["model"], 0) + 1
            tk = o.get("tokens") or {}
            tok["in"] += tk.get("input", 0) or 0
            tok["out"] += tk.get("output", 0) or 0
            tok["cr"] += tk.get("cached", 0) or 0
        r = classify_gemini_line(o)
        if not r:
            continue
        role, segs = r
        turn = {"role": role, "segs": segs, "ts": o.get("timestamp", ""), "tags": turn_tags(o, role, segs)}
        if role == "assistant" and model:
            turn["model"] = model
        turns.append(turn)
        if role in n:
            n[role] += 1
        if role == "you" and not first_human:
            first_human = " ".join(x[1] for x in segs if x[0] == "text").strip()
    title = (first_human or _gemini_projname(path) or tr("(untitled)")).strip()[:120]
    meta = {"title": title, "preview": first_human.strip()[:140], "n": n, "last_ts": last_ts,
            "cwd": cwd, "start_cwd": cwd, "branch": "", "forked": "", "loop": False,
            "tok": tok, "models": models}
    return {"turns": turns, "meta": meta}

# ---- subagents --------------------------------------------------------------
def subagent_files(session_path):
    base = session_path[:-6] if session_path.endswith(".jsonl") else session_path
    sub = os.path.join(base, "subagents")
    if not os.path.isdir(sub):
        return []
    return sorted(glob.glob(os.path.join(sub, "**", "agent-*.jsonl"), recursive=True))

def subagent_brief(path):
    turns = classify_turns(path, sub=True)
    brief = ""
    for t in turns:
        if t["role"] == "orchestrator":
            brief = " ".join(x[1] for x in t["segs"] if x[0] == "text").strip()
            break
    aid = os.path.basename(path)[len("agent-"):-len(".jsonl")]
    m = re.search(r"/workflows/(wf_[^/]+)/", path.replace(os.sep, "/"))
    return {"path": path, "agentId": aid, "wf": m.group(1) if m else "",
            "n": len(turns), "brief": (brief or tr("(no instruction)"))[:120]}

# ---- digest + code extraction ----------------------------------------------
def _toolinput(txt):
    name, _, rest = txt.partition("\n")
    try:
        return name.strip(), json.loads(rest)
    except Exception:
        return name.strip(), {}

# Fields that make a tool CALL findable: the command, the files, the pattern, the
# intent — NOT raw JSON keys and NOT large code blobs (content/new_string are already
# searchable via the tool_result diff, so re-indexing them would only bloat the index).
_TOOL_SEARCH_FIELDS = ("command", "cmd", "file_path", "path", "notebook_path", "pattern",
                       "query", "url", "description", "prompt")

def _tool_use_search_text(txt):
    """Searchable text for a tool_use seg: tool name + its identifying args
    (e.g. `Bash git commit -m …`, `Read src/app.py`, `Grep TODO`)."""
    name, inp = _toolinput(txt)
    vals = [name]
    if isinstance(inp, dict):
        for k in _TOOL_SEARCH_FIELDS:
            v = inp.get(k)
            if isinstance(v, str) and v.strip():
                vals.append(v)
    return " ".join(vals)

def session_digest(turns):
    files, commits, urls = set(), [], set()
    cmds = tests = errors = edits = webs = 0
    for t in turns:
        if "error" in t["tags"]:
            errors += 1
        for kind, txt in t["segs"]:
            if kind == "tool_use":
                name, inp = _toolinput(txt)
                if name in EDIT_TOOLS:
                    edits += 1
                    fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
                    if fp:
                        files.add(fp)
                elif name in ("Bash", "exec_command", "shell", "local_shell", "run_shell_command"):
                    cmds += 1
                    cmd = inp.get("command") or inp.get("cmd") or ""
                    if COMMIT_RE.search(cmd):
                        m = COMMIT_MSG_RE.search(cmd)
                        commits.append(m.group(1) if m else "git commit")
                    if TEST_RE.search(cmd):
                        tests += 1
                elif name in ("WebFetch", "WebSearch"):
                    webs += 1
            elif kind in ("text", "tool_result"):
                for u in URL_RE.findall(txt):
                    urls.add(u.rstrip(".,);"))
    prs = sorted({u for u in urls if re.search(r"github\.com/.+/(pull|issues)/\d+", u)})
    return {"files": sorted(files), "cmds": cmds, "commits": commits, "tests": tests,
            "errors": errors, "edits": edits, "urls": sorted(urls), "prs": prs, "webs": webs}

def extract_code(turns):
    arts = []
    for gi, t in enumerate(turns):
        for kind, txt in t["segs"]:
            if kind == "text" and t["role"] == "assistant":
                for m in CODE_FENCE_RE.finditer(txt):
                    body = m.group(2)
                    if body.strip():
                        arts.append({"gi": gi, "label": (m.group(1) or "code"), "kind": "block", "body": body, "ts": t["ts"]})
            elif kind == "tool_use":
                name, inp = _toolinput(txt)
                if name in EDIT_TOOLS:
                    fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or name
                    if "content" in inp:
                        body = inp.get("content", "")
                    elif "new_string" in inp:
                        body = inp.get("new_string", "")
                    elif "new_str" in inp:
                        body = inp.get("new_str", "")
                    else:
                        body = json.dumps(inp, ensure_ascii=False, indent=2)
                    if str(body).strip():
                        arts.append({"gi": gi, "label": fp, "kind": "edit", "body": str(body), "ts": t["ts"]})
    return arts

# ---- per-file summary -------------------------------------------------------
def summarize_file(path):
    prov = provider_of(path)
    if prov == "codex":
        return _codex_load(path)["meta"]
    if prov == "gemini":
        return _gemini_load(path)["meta"]
    ai_title = custom_title = last_prompt = first_human = ""
    n = {"you": 0, "assistant": 0, "tool-result": 0, "system": 0, "subagent": 0}
    last_ts = cwd = start_cwd = branch = forked = ""
    tok = {"in": 0, "out": 0, "cw": 0, "cr": 0}
    models = {}
    loop = False
    for o in iter_lines(path):
        t = o.get("type")
        if t == "assistant":
            m = o.get("message") or {}
            add_tok(tok, usage_tok(m.get("usage")))
            mdl = m.get("model")
            if mdl:
                models[mdl] = models.get(mdl, 0) + 1
        if t == "ai-title":
            ai_title = o.get("aiTitle", ai_title) or ai_title; continue
        if t == "custom-title":
            custom_title = o.get("customTitle", custom_title) or custom_title; continue
        if t == "last-prompt":
            last_prompt = o.get("lastPrompt", last_prompt) or last_prompt; continue
        c = o.get("cwd")
        if c:
            cwd = c                       # last cwd = current workspace
            if not start_cwd:
                start_cwd = c             # first cwd = launch dir
        branch = o.get("gitBranch", branch) or branch
        if not forked:
            ff = o.get("forkedFrom")
            if isinstance(ff, dict) and ff.get("sessionId"):
                forked = ff["sessionId"]
        if o.get("timestamp"):
            last_ts = o["timestamp"]
        r = classify_line(o)
        if not r:
            continue
        if r[0] in n:
            n[r[0]] += 1
        if r[0] == "system" and not loop:
            if any(x[0] == "injected" and x[1].lstrip().startswith(LOOP_PREFIXES) for x in r[1]):
                loop = True
        if r[0] == "you" and not first_human:
            first_human = " ".join(x[1] for x in r[1] if x[0] == "text").strip()
    title = custom_title or ai_title or first_human or last_prompt or tr("(untitled)")
    return {"title": title.strip()[:120], "preview": (last_prompt or first_human).strip()[:140],
            "n": n, "last_ts": last_ts, "cwd": cwd, "start_cwd": start_cwd, "branch": branch,
            "forked": forked, "loop": loop, "tok": tok, "models": models}

# ---- combined session load (one pass: turns + meta) — kills the /session double-parse
_SESSION = {"by_path": {}, "lock": threading.Lock()}

def _load_session_uncached(path):
    ai_title = custom_title = last_prompt = first_human = ""
    n = {"you": 0, "assistant": 0, "tool-result": 0, "system": 0, "subagent": 0}
    last_ts = cwd = start_cwd = branch = forked = ""
    tok = {"in": 0, "out": 0, "cw": 0, "cr": 0}
    models = {}
    loop = False
    turns = []
    for o in iter_lines(path):
        t = o.get("type")
        if t == "assistant":
            m = o.get("message") or {}
            add_tok(tok, usage_tok(m.get("usage")))
            if m.get("model"):
                models[m["model"]] = models.get(m["model"], 0) + 1
        if t == "ai-title":
            ai_title = o.get("aiTitle", ai_title) or ai_title; continue
        if t == "custom-title":
            custom_title = o.get("customTitle", custom_title) or custom_title; continue
        if t == "last-prompt":
            last_prompt = o.get("lastPrompt", last_prompt) or last_prompt; continue
        c = o.get("cwd")
        if c:
            cwd = c
            if not start_cwd:
                start_cwd = c
        branch = o.get("gitBranch", branch) or branch
        if not forked:
            ff = o.get("forkedFrom")
            if isinstance(ff, dict) and ff.get("sessionId"):
                forked = ff["sessionId"]
        if o.get("timestamp"):
            last_ts = o["timestamp"]
        r = classify_line(o)
        if not r:
            continue
        role, segs = r
        turn = {"role": role, "segs": segs, "ts": o.get("timestamp", ""), "tags": turn_tags(o, role, segs)}
        if t == "assistant":
            m = o.get("message") or {}
            turn["model"] = m.get("model", "")
            turn["tok"] = usage_tok(m.get("usage"))
        turns.append(turn)
        if role in n:
            n[role] += 1
        if role == "system" and not loop and any(
                x[0] == "injected" and x[1].lstrip().startswith(LOOP_PREFIXES) for x in segs):
            loop = True
        if role == "you" and not first_human:
            first_human = " ".join(x[1] for x in segs if x[0] == "text").strip()
    title = custom_title or ai_title or first_human or last_prompt or tr("(untitled)")
    meta = {"title": title.strip()[:120], "preview": (last_prompt or first_human).strip()[:140],
            "n": n, "last_ts": last_ts, "cwd": cwd, "start_cwd": start_cwd, "branch": branch,
            "forked": forked, "loop": loop, "tok": tok, "models": models}
    for i, tt in enumerate(turns):        # per-question token cost (answer block until next 🧑)
        if tt["role"] == "you":
            qsum = {"in": 0, "out": 0, "cw": 0, "cr": 0}
            j = i + 1
            while j < len(turns) and turns[j]["role"] != "you":
                add_tok(qsum, turns[j].get("tok"))
                j += 1
            if any(qsum.values()):
                tt["qtok"] = qsum
    return {"turns": turns, "meta": meta}

def load_session(path):
    """Cached one-pass load of a session (turns + meta), keyed on (mtime_ns, size)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    with _SESSION["lock"]:
        hit = _SESSION["by_path"].get(path)
        if hit is not None and hit[0] == key:
            return hit[1]
    prov = provider_of(path)
    if prov == "codex":
        data = _codex_load(path)
    elif prov == "gemini":
        data = _gemini_load(path)
    else:
        data = _load_session_uncached(path)
    with _SESSION["lock"]:
        cache = _SESSION["by_path"]
        cache[path] = (key, data)
        if len(cache) > 64:                # bounded: drop oldest-inserted
            for k in list(cache)[:len(cache) - 64]:
                del cache[k]
    return data

# ---- index cache (per root, incrementally refreshed) -------------------------
_INDEX = {"by_root": {}, "lock": threading.Lock()}
def is_codex_root(root):
    q = (root or "").replace(os.sep, "/")
    return "/.codex/" in q or q.rstrip("/").endswith("/.codex/sessions")

def is_gemini_root(root):
    q = (root or "").replace(os.sep, "/")
    return "/.gemini/" in q or q.rstrip("/").endswith("/.gemini/tmp")

def root_glyph(root):
    """Provider glyph for a folder — by kind or by 'codex'/'gemini'/'claude' in its path."""
    q = (root or "").lower().replace(os.sep, "/")
    if is_codex_root(root) or "codex" in q:
        return "🌀 "
    if is_gemini_root(root) or "gemini" in q:
        return "✨ "
    if "claude" in q:
        return "✴️ "
    return ""

def session_files(root):
    if is_codex_root(root):
        return sorted(glob.glob(os.path.join(root, "**", "rollout-*.jsonl"), recursive=True))
    if is_gemini_root(root):
        return sorted(glob.glob(os.path.join(root, "*", "chats", "session-*.jsonl")))
    return sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))

def _looks_ref(t):
    """A hex/UUID-ish token (a session-id or a fragment of one), not a normal word."""
    s = (t or "").replace("-", "")
    return len(s) >= 6 and all(c in "0123456789abcdef" for c in s)

def find_session_by_sid(root, sid):
    """First transcript file named <sid>.jsonl anywhere under root (for branched-from links)."""
    if not re.fullmatch(r"[0-9a-f-]{8,36}", sid or ""):
        return None
    for p in sorted(glob.glob(os.path.join(root, "*", sid + ".jsonl"))):
        return p
    return None

def adjacent_sessions(root, current_path):
    """Prev/next session in the SAME project, chronological (by mtime). Work spans sessions."""
    index = get_index(root)
    cur = next((it for it in index if it["path"] == current_path), None)
    if not cur:
        return None, None
    same = sorted((it for it in index if it["proj"] == cur["proj"]), key=lambda it: it["mtime"])
    pos = next((i for i, it in enumerate(same) if it["path"] == current_path), None)
    if pos is None:
        return None, None
    return (same[pos - 1] if pos > 0 else None), (same[pos + 1] if pos + 1 < len(same) else None)

def _index_item(path, st):
    s = summarize_file(path)
    prov = provider_of(path)
    if prov == "codex":                         # no project folders — group by workspace (cwd)
        proj = s["cwd"] or "codex"
        sid = _codex_sid(path)
    elif prov == "gemini":
        proj = s["cwd"] or _gemini_projname(path) or "gemini"
        sid = _gemini_sid(path)
    else:
        proj = os.path.basename(os.path.dirname(path))
        sid = os.path.basename(path)[:-6]
    return {"path": path, "proj": proj, "provider": prov,
            "sid": sid, "title": s["title"], "preview": s["preview"],
            "n": s["n"], "mtime": st.st_mtime, "size": st.st_size, "cwd": s["cwd"],
            "start_cwd": s["start_cwd"], "branch": s["branch"], "forked": s["forked"], "loop": s["loop"],
            "tok": s["tok"], "models": s["models"]}

def get_index(root):
    """Per-root index; re-summarizes only files whose (mtime, size) changed,
    picks up new sessions, and drops deleted ones — so a long-running server
    always shows current data at ~one stat() per file per request."""
    with _INDEX["lock"]:
        cache = _INDEX["by_root"].setdefault(root, {})
        seen = set()
        for path in session_files(root):
            try:
                st = os.stat(path)
            except OSError:
                continue
            seen.add(path)
            key = (st.st_mtime_ns, st.st_size)
            hit = cache.get(path)
            if hit is None or hit[0] != key:
                cache[path] = (key, _index_item(path, st))
        for gone in set(cache) - seen:
            del cache[gone]
        items = [v[1] for v in cache.values()]
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

# ---- search cache: per-file searchable turn texts, keyed on (mtime_ns, size) --
_SEARCH = {"by_path": {}, "lock": threading.Lock()}
_SEARCH_KINDS = ("text", "tool_result", "thinking", "injected")

# search-row kind flags (bitmask), for scope/field filtering
K_TEXT, K_TOOL, K_RESULT, K_CODE = 1, 2, 4, 8
K_FILE, K_CMD, K_ERROR, K_THINK, K_SYS = 16, 32, 64, 128, 256
_CODE_CAP = 20000   # cap a single code body's searchable length (bloat guard)

def _rows_from_turns(turns):
    """Structured search rows for one session's turns: {gi, role, text, kind, label}.
    Includes CODE rows from extract_code() so the '🧩 Code only' content is searchable."""
    out = []
    for gi, t in enumerate(turns):
        role, tags = t["role"], t["tags"]
        err = K_ERROR if "error" in tags else 0
        for k, v in t["segs"]:
            if k == "text":
                out.append({"gi": gi, "role": role, "text": v, "kind": K_TEXT, "label": ""})
            elif k == "channel":
                pc = parse_channel(v)
                out.append({"gi": gi, "role": role, "text": pc[1] if pc else v, "kind": K_TEXT, "label": ""})
            elif k == "thinking":
                out.append({"gi": gi, "role": role, "text": v, "kind": K_THINK, "label": ""})
            elif k == "injected":
                out.append({"gi": gi, "role": role, "text": v, "kind": K_SYS, "label": ""})
            elif k == "tool_use":
                name, inp = _toolinput(v)
                kind = K_TOOL | (K_CMD if name == "Bash" else 0)
                if isinstance(inp, dict) and (inp.get("file_path") or inp.get("path") or inp.get("notebook_path")):
                    kind |= K_FILE
                out.append({"gi": gi, "role": role, "text": _tool_use_search_text(v), "kind": kind, "label": name})
            elif k == "tool_result":
                out.append({"gi": gi, "role": role, "text": v, "kind": K_RESULT | err, "label": ""})
    for art in extract_code(turns):
        body = str(art["body"])
        out.append({"gi": art["gi"], "role": "assistant", "text": body[:_CODE_CAP],
                    "kind": K_CODE | (K_FILE if art["kind"] == "edit" else 0), "label": art.get("label", "")})
    out = [r for r in out if r["text"].strip()]
    for r in out:
        r["low"] = r["text"].lower()          # precompute once (matching never re-lowers)
    return out

_WORD_RE = re.compile(r"\w+")

def _rows_blob(path):
    """(rows, blob, tokens) for a session — cached. blob = all lowercased text (cheap
    substring pre-filter); tokens = its whole-word set (O(1) whole-word test in scoring)."""
    try:
        st = os.stat(path)
    except OSError:
        return [], "", frozenset()
    key = (st.st_mtime_ns, st.st_size)
    with _SEARCH["lock"]:
        hit = _SEARCH["by_path"].get(path)
        if hit is not None and hit[0] == key:
            return hit[1], hit[2], hit[3]
    rows = _rows_from_turns(classify_turns(path))
    blob = "\n".join(r["low"] for r in rows)
    tokens = frozenset(_WORD_RE.findall(blob))
    with _SEARCH["lock"]:
        _SEARCH["by_path"][path] = (key, rows, blob, tokens)
    return rows, blob, tokens

def search_rows(path):
    """Cached structured search rows for a session file (keyed on mtime_ns+size)."""
    return _rows_blob(path)[0]

def search_turns(path):
    """Back-compat: one (gi, role, text) per turn over the default (non-code) corpus."""
    by = {}
    for r in search_rows(path):
        if r["kind"] & K_CODE:
            continue
        e = by.get(r["gi"])
        if e is None:
            by[r["gi"]] = (r["role"], [r["text"]])
        else:
            e[1].append(r["text"])
    return [(gi, role, " ".join(parts)) for gi, (role, parts) in by.items()]

# ---- query grammar + matching ----------------------------------------------
FIELD_ALIASES = {"file": "file", "path": "file", "cmd": "cmd", "command": "cmd",
                 "code": "code", "error": "error", "err": "error",
                 "role": "role", "id": "id", "session": "id", "sid": "id"}
FIELD_KIND = {"file": K_FILE, "cmd": K_CMD, "code": K_CODE, "error": K_ERROR | K_RESULT}
_SQ_TOK = re.compile(r'(-?)(?:(\w+):)?("[^"]*"|“[^”]*”|\S+)')

def parse_search_query(q):
    """'file:app.py -flaky "exact" foo' → {terms, phrases, fields, neg}.
    Unknown `word:` prefixes (e.g. http://) stay plain terms."""
    terms, phrases, neg, fields = [], [], [], {}
    for neg_s, field, raw in _SQ_TOK.findall(q or ""):
        is_phrase = raw[:1] in ('"', '“')
        val = raw.strip('"“”').strip().lower()
        if not val:
            continue
        f = FIELD_ALIASES.get((field or "").lower()) if field else None
        if field and not f:                       # unrecognized field → keep token whole
            val = f"{field}:{val}".lower()
        if f:
            fields.setdefault(f, []).append(val)
        elif neg_s:
            neg.append(val)
        elif is_phrase:
            phrases.append(val)
        else:
            terms.append(val)
    return {"terms": terms, "phrases": phrases, "fields": fields, "neg": neg}

def _scope_ok(r, scope):
    kind, role = r["kind"], r["role"]
    if scope == "human":
        return role == "you"
    if scope == "claude":
        return role == "assistant" and not (kind & K_CODE)
    if scope == "chat":
        return role in ("you", "assistant") and not (kind & (K_TOOL | K_RESULT | K_SYS | K_CODE))
    if scope == "code":
        return bool(kind & K_CODE)
    if scope == "tool":
        return bool(kind & (K_TOOL | K_RESULT | K_CMD | K_FILE))
    return True                                    # all (includes code rows)

def _fields_ok(active, field_terms):
    for f, vals in field_terms.items():
        mask = FIELD_KIND[f]
        for val in vals:
            if not any((r["kind"] & mask) and val in r["low"] for r in active):
                return False
    return True

def _best_window(term_gis, need):
    """Smallest turn-span window covering at least one occurrence of every term."""
    events = sorted((gi, ti) for ti in range(len(need)) for gi in term_gis[need[ti]])
    if not events:
        return None
    have, left, distinct, best = {}, 0, 0, None
    for right in range(len(events)):
        gi, ti = events[right]
        have[ti] = have.get(ti, 0) + 1
        if have[ti] == 1:
            distinct += 1
        while distinct == len(need):
            span = gi - events[left][0]
            if best is None or span < best[0]:
                best = (span, sorted({events[k][0] for k in range(left, right + 1)}))
            lti = events[left][1]
            have[lti] -= 1
            if have[lti] == 0:
                distinct -= 1
            left += 1
    return best

def match_session(active, terms, phrases, blob="", tokens=frozenset()):
    """Return the best hit for one session: row (same-turn) → cluster (nearby turns)
    → session (anywhere). None if not all terms/phrases are present. `blob`/`tokens` (the
    file's cached lowercased text and whole-word set) are used only for cheap score counts."""
    need = terms + phrases
    if not need:
        return None
    # which terms appear in each turn — one pass over rows' precomputed lowercase text,
    # no big per-turn string joins (that was the hot spot on large sessions).
    gi_terms = {}
    for r in active:
        low = r["low"]
        for t in need:
            if t in low:
                gi_terms.setdefault(r["gi"], set()).add(t)
    ntot = len(need)
    ww = [blob.count(t) for t in terms]
    all_word = bool(terms) and all(t in tokens for t in terms)   # O(1) whole-word test
    row_gis = sorted(gi for gi, s in gi_terms.items() if len(s) == ntot)
    if row_gis:
        return {"kind": "row", "gis": row_gis, "ww": ww, "all_word": all_word, "span": 0}
    term_gis = {t: sorted(gi for gi, s in gi_terms.items() if t in s) for t in need}
    if not all(term_gis[t] for t in need):
        return None
    win = _best_window(term_gis, need)
    if win is not None:
        span, gis = win
        return {"kind": "cluster" if span <= 12 else "session", "gis": gis,
                "ww": ww, "all_word": False, "span": span}
    return {"kind": "session", "gis": [term_gis[t][0] for t in need], "ww": ww,
            "all_word": False, "span": 99}

def _snippet(text, terms):
    """A ~150-char window centered on the first (whole-word, else substring) match."""
    pos = None
    for t in terms:
        m = word_re(t).search(text)
        if m:
            pos = m.start()
            break
    if pos is None:
        low = text.lower()
        for t in terms:
            j = low.find(t)
            if j >= 0:
                pos = j
                break
    if pos is None:
        pos = 0
    return text[max(0, pos - 55):pos + 95].replace("\n", " ")

# ---- render helpers ---------------------------------------------------------
def esc(s):
    return html.escape(s or "")

def fmt_ts(ts):
    if not ts:
        return ""
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts[:16]

def fmt_ts_short(ts):
    if not ts:
        return ""
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return ts[:16]

def fmt_mtime(t):
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")

def fmt_size(b):
    for unit, div in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if b >= div:
            return f"{b/div:.1f}{unit}"
    return f"{b}B"

# ---- token usage & model ----------------------------------------------------
_TOK_KEYS = (("in", "input_tokens"), ("out", "output_tokens"),
             ("cw", "cache_creation_input_tokens"), ("cr", "cache_read_input_tokens"))

def usage_tok(u):
    """Pull the 4 token counts from a message.usage dict → {in,out,cw,cr} or None."""
    if not isinstance(u, dict):
        return None
    d = {}
    for a, b in _TOK_KEYS:
        v = u.get(b)
        d[a] = v if isinstance(v, int) else 0
    return d if any(d.values()) else None

def add_tok(dst, src):
    if src:
        for a, _ in _TOK_KEYS:
            dst[a] += src.get(a, 0)
    return dst

def fmt_tok(n):
    n = n or 0
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)

_MODEL_RE = re.compile(r"(opus|sonnet|haiku|fable)-(\d+)(?:-(\d+))?")
def model_short(m):
    """'claude-opus-4-8' → 'Opus 4.8'; synthetic/unknown → '' (skip)."""
    s = (m or "")
    if not s or s.startswith("<"):
        return ""
    mm = _MODEL_RE.search(s)
    if mm:
        base = mm.group(1).capitalize()
        return f"{base} {mm.group(2)}.{mm.group(3)}" if mm.group(3) else f"{base} {mm.group(2)}"
    return s.replace("claude-", "")

def tok_badge(tok, cls="tokb"):
    if not tok or not any(tok.values()):
        return ""
    title = (f"{tr('Input')} {tok['in']:,} · {tr('Output')} {tok['out']:,} · "
             f"{tr('Cache write')} {tok['cw']:,} · {tr('Cache read')} {tok['cr']:,} ({tr('cache read is reused context, cheap')})")
    return (f'<span class="{cls}" title="{esc(title)}">'
            f'↑{fmt_tok(tok["in"])} ↓{fmt_tok(tok["out"])}'
            f'<span class=tokc> 💾{fmt_tok(tok["cw"])}</span></span>')

def models_badge(models):
    out = []
    for m, c in sorted((models or {}).items(), key=lambda kv: -kv[1]):
        sh = model_short(m)
        if sh:
            out.append(f'<span class=mdl title="{esc(m)} · {c} {esc(tr('responses'))}">{esc(sh)}<span class=mdlc> {c}</span></span>')
    return " ".join(out)

def agg_stats(items):
    s = {"sessions": 0, "my_sessions": 0, "my_msgs": 0, "size": 0, "my_size": 0,
         "loop": 0, "asst": 0, "tool": 0, "tok": {"in": 0, "out": 0, "cw": 0, "cr": 0}, "models": {}}
    for it in items:
        s["sessions"] += 1
        s["size"] += it["size"]
        s["asst"] += it["n"]["assistant"]
        s["tool"] += it["n"]["tool-result"]
        s["my_msgs"] += it["n"]["you"]
        add_tok(s["tok"], it.get("tok"))
        for m, c in (it.get("models") or {}).items():
            s["models"][m] = s["models"].get(m, 0) + c
        if it["n"]["you"] > 0:
            s["my_sessions"] += 1
            s["my_size"] += it["size"]
        if it.get("loop"):
            s["loop"] += 1
    return s

_HOME = os.path.expanduser("~")
def short_path(p):
    if not p:
        return ""
    if p == _HOME or p.startswith(_HOME + os.sep) or p.startswith(_HOME + "/"):
        return "~" + p[len(_HOME):]
    return p

def proj_label(item):
    return short_path(item.get("cwd") or "") or item.get("proj", "")

def counts_html(n, system=False):
    parts = [f'<span title="{esc(tr("Messages you sent"))}">🧑 {n["you"]}</span>',
             f'<span title="{esc(tr("Claude (assistant) replies"))}">✦ {n["assistant"]}</span>',
             f'<span title="{esc(tr("Tool results (Bash/Edit/Read …)"))}">⚙ {n["tool-result"]}</span>']
    if system:
        parts.append(f'<span title="{esc(tr("System / injected context"))}">ⓘ {n["system"]}</span>')
    return " · ".join(parts)

def parse_query(q):
    """'foo bar "exact phrase"' → ['foo', 'bar', 'exact phrase'] (lowercased).
    All terms must match (AND); quoted phrases match as a unit."""
    terms = []
    for m in re.finditer(r'"([^"]+)"|“([^”]+)”|(\S+)', q or ""):
        t = (m.group(1) or m.group(2) or m.group(3) or "").strip().lower()
        if t:
            terms.append(t)
    return terms

HL_COLORS = 6  # palette slots; term N uses color N % HL_COLORS

def word_re(t):
    """Whole-word matcher for a term/phrase (Unicode-aware boundaries)."""
    return re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I)

def _date_ts(s, end=False):
    """'YYYY-MM-DD' → local epoch seconds (end=True → next-day 00:00), else None."""
    try:
        d = datetime.date.fromisoformat((s or "").strip())
    except (ValueError, TypeError):
        return None
    dt = datetime.datetime(d.year, d.month, d.day)
    if end:
        dt += datetime.timedelta(days=1)
    return dt.timestamp()

def hl(text, q):
    """Highlight every occurrence of every query term, each term its own color."""
    terms = parse_query(q)
    if not terms:
        return esc(text)
    low = text.lower()
    spans = []  # (start, end, term_index)
    for ti, t in enumerate(terms):
        i = 0
        while True:
            j = low.find(t, i)
            if j < 0:
                break
            spans.append((j, j + len(t), ti))
            i = j + len(t)
    if not spans:
        return esc(text)
    spans.sort()
    merged = [list(spans[0])]
    for s, e, ti in spans[1:]:
        if s <= merged[-1][1]:                       # overlap → extend, keep first color
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e, ti])
    out, i = [], 0
    for s, e, ti in merged:
        out.append(esc(text[i:s]))
        out.append(f'<mark class="hl{ti % HL_COLORS}">{esc(text[s:e])}</mark>')
        i = e
    out.append(esc(text[i:]))
    return "".join(out)

def hl_html(html_str, q):
    """Highlight query terms inside already-rendered HTML, touching text nodes only
    (never tag names or attribute values)."""
    terms = parse_query(q)
    if not terms:
        return html_str
    parts = re.split(r"(<[^>]+>)", html_str)   # even idx = text, odd = tags
    for k in range(0, len(parts), 2):
        parts[k] = _hl_frag(parts[k], terms)
    return "".join(parts)

def _hl_frag(text, terms):
    """Highlight terms in an ALREADY-escaped text fragment (no re-escaping)."""
    if not text:
        return text
    low = text.lower()
    spans = []
    for ti, t in enumerate(terms):
        i = 0
        while True:
            j = low.find(t, i)
            if j < 0:
                break
            spans.append((j, j + len(t), ti))
            i = j + len(t)
    if not spans:
        return text
    spans.sort()
    merged = [list(spans[0])]
    for s, e, ti in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e, ti])
    res, i = [], 0
    for s, e, ti in merged:
        res.append(text[i:s])
        res.append(f'<mark class="hl{ti % HL_COLORS}">{text[s:e]}</mark>')
        i = e
    res.append(text[i:])
    return "".join(res)

# ---- minimal, safe Markdown → HTML (stdlib only, by design) -----------------
# Everything is html.escape()'d BEFORE any markdown transform, so raw HTML in a
# transcript is neutralised (shown as text) and the syntax chars (* _ ` # | - [ ])
# survive escaping untouched.
_MD_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_MD_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_MD_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_MD_DELIM_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")

def _md_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]

def _md_aligns(delim):
    out = []
    for c in _md_cells(delim):
        left, right = c.startswith(":"), c.endswith(":")
        out.append("center" if left and right else "right" if right else "left" if left else "")
    return out

def _md_table(header, delim, rows):
    aligns = _md_aligns(delim)
    hcells = _md_cells(header)
    ncol = len(hcells)
    def sty(i):
        a = aligns[i] if i < len(aligns) else ""
        return f' style="text-align:{a}"' if a else ""
    thead = "".join(f"<th{sty(i)}>{md_inline(esc(c))}</th>" for i, c in enumerate(hcells))
    body = []
    for r in rows:
        cells = _md_cells(r)
        cells += [""] * (ncol - len(cells))
        tds = "".join(f"<td{sty(i)}>{md_inline(esc(cells[i]))}</td>" for i in range(ncol))
        body.append(f"<tr>{tds}</tr>")
    return (f'<div class="md-tablewrap"><table class="md-table"><thead><tr>{thead}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')

def md_inline(s):
    """Inline markdown on an ALREADY-escaped string. Underscore emphasis is
    word-boundary-gated so snake_case identifiers survive."""
    if not s:
        return s
    stash = []
    def keep(html_):
        stash.append(html_)
        return f"\x00{len(stash) - 1}\x01"
    s = re.sub(r"`([^`]+)`", lambda m: keep(f'<code class="md-ic">{m.group(1)}</code>'), s)
    def _lnk(m):
        text, url = m.group(1), m.group(2)
        low = url.lower()
        if low.startswith(("http://", "https://", "mailto:")) or url[:1] in ("/", "#", "."):
            return keep(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{text}</a>')
        return m.group(0)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _lnk, s)
    s = re.sub(r"(?<![\"=/\w])(https?://[^\s<>()]+[^\s<>().,;:!?])",
               lambda m: keep(f'<a href="{m.group(1)}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>'), s)
    s = re.sub(r"\*\*(\S(?:.*?\S)?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)__(\S(?:.*?\S)?)__(?!\w)", r"<strong>\1</strong>", s)
    s = re.sub(r"~~(\S(?:.*?\S)?)~~", r"<del>\1</del>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)([^*\n]+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)_(?!\w)", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x01", lambda m: stash[int(m.group(1))], s)

def _md_is_block(lines, i):
    line = lines[i]
    ls = line.lstrip()
    if _MD_FENCE_RE.match(ls) or _MD_HEAD_RE.match(line.strip()) or _MD_HR_RE.match(line):
        return True
    if ls.startswith(">") or _MD_LIST_RE.match(line):
        return True
    if "|" in line and i + 1 < len(lines) and _MD_DELIM_RE.match(lines[i + 1]):
        return True
    return False

def _md_list(block):
    items = []
    for ln in block:
        m = _MD_LIST_RE.match(ln)
        if m:
            indent = len(m.group(1).replace("\t", "  "))
            ordered = m.group(2)[0] not in "-*+"
            items.append({"indent": indent, "ordered": ordered, "text": m.group(3), "children": []})
        elif items:
            items[-1]["text"] += "\n" + ln.strip()
    root = []
    stack = [(-1, root)]
    for it in items:
        while len(stack) > 1 and it["indent"] <= stack[-1][0]:
            stack.pop()
        stack[-1][1].append(it)
        stack.append((it["indent"], it["children"]))
    def render(nodes):
        if not nodes:
            return ""
        tag = "ol" if nodes[0]["ordered"] else "ul"
        lis = []
        for nd in nodes:
            inner = "<br>".join(md_inline(esc(x)) for x in nd["text"].split("\n"))
            lis.append(f'<li>{inner}{render(nd["children"])}</li>')
        return f'<{tag} class="md-list">{"".join(lis)}</{tag}>'
    return render(root)

def md_to_html(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    n = len(lines)
    out, i = [], 0
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = _MD_FENCE_RE.match(line.lstrip())
        if m:                                        # fenced code
            fence = m.group(1)[0] * 3
            langtok = m.group(2).strip().split()
            lang = langtok[0] if langtok else ""
            body = []
            i += 1
            while i < n and not lines[i].lstrip().startswith(fence):
                body.append(lines[i])
                i += 1
            i += 1
            head = f'<div class="md-clang">{esc(lang)}</div>' if lang else ""
            out.append(f'<div class="md-codewrap">{head}'
                       f'<pre class="md-code"><code>{esc(chr(10).join(body))}</code></pre></div>')
            continue
        if "|" in line and i + 1 < n and _MD_DELIM_RE.match(lines[i + 1]):   # table
            header, delim = line, lines[i + 1]
            i += 2
            rows = []
            while i < n and lines[i].strip() and "|" in lines[i] and not _MD_FENCE_RE.match(lines[i].lstrip()):
                rows.append(lines[i])
                i += 1
            out.append(_md_table(header, delim, rows))
            continue
        m = _MD_HEAD_RE.match(line.strip())
        if m:                                        # heading
            lvl = len(m.group(1))
            out.append(f'<div class="md-h md-h{lvl}">{md_inline(esc(m.group(2).strip().rstrip("#").strip()))}</div>')
            i += 1
            continue
        if _MD_HR_RE.match(line):                     # horizontal rule
            out.append('<hr class="md-hr">')
            i += 1
            continue
        if line.lstrip().startswith(">"):             # blockquote
            bq = []
            while i < n and lines[i].lstrip().startswith(">"):
                bq.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f'<blockquote class="md-bq">{md_to_html(chr(10).join(bq))}</blockquote>')
            continue
        if _MD_LIST_RE.match(line):                   # list
            block = []
            while i < n and lines[i].strip() and (_MD_LIST_RE.match(lines[i]) or lines[i][:1] in (" ", "\t")):
                block.append(lines[i])
                i += 1
            out.append(_md_list(block))
            continue
        para = []                                     # paragraph
        while i < n and lines[i].strip() and not _md_is_block(lines, i):
            para.append(lines[i])
            i += 1
        out.append('<p class="md-p">' + "<br>".join(md_inline(esc(p)) for p in para) + "</p>")
    return "".join(out)

def md_html(text, q=""):
    """Render markdown safely; on any failure fall back to escaped+highlighted text."""
    try:
        h = md_to_html(text)
        return hl_html(h, q) if q else h
    except Exception:
        return hl(text, q)

# English values are the translation KEYS; tr() is applied at render time (NOT here —
# a module-level tr() would freeze to whichever language loaded first).
ROLE_LABEL = {"you": "🧑 You", "assistant": "✦ Claude", "tool-result": "⚙ Tool result",
              "system": "ⓘ System / injected", "subagent": "🤖 Subagent",
              "orchestrator": "📋 Instruction → subagent", "channel": "💬 Channel"}
ROLE_DESC = {
    "you": "Messages you actually typed or pasted — a verified ruleset marks only these as 'You'.",
    "assistant": "Claude's (the assistant's) replies.",
    "tool-result": "Output of a tool Claude ran (Bash command, Edit/Write, Read, …). Not written by a human.",
    "system": "Context the system injected automatically — system-reminder, IDE notices, slash-command output, task-notification, etc. Not written by a human.",
    "subagent": "Conversation of a sub-agent Claude spawned.",
    "orchestrator": "The task brief given to a sub-agent (generated by Claude, not a human).",
    "channel": "A human message relayed into the session through an external channel plugin (Telegram, …). The sender is shown after @ — not necessarily you."}

def legend_html(open_=False):
    rows = [("🧑 You", ROLE_DESC["you"]),
            ("💬 Telegram / channel", ROLE_DESC["channel"]),
            ("✦ Claude", ROLE_DESC["assistant"]),
            ("💭 Thinking", "Claude's reasoning — usually collapsed / private."),
            ("🔧 Tool call", "Claude calling a tool (run Bash, Edit/Write/Read a file, …)."),
            ("⚙ Tool result", ROLE_DESC["tool-result"]),
            ("ⓘ System / injected", ROLE_DESC["system"]),
            ("📋 Instruction", ROLE_DESC["orchestrator"]),
            ("🤖 Subagent", ROLE_DESC["subagent"])]
    body = "".join(f'<div style="margin:3px 0"><b>{esc(tr(e))}</b> — <span class=meta>{esc(tr(d))}</span></div>'
                   for e, d in rows)
    return (f'<details class="card"{" open" if open_ else ""}>'
            f'<summary style="cursor:pointer;font-weight:650;color:#1f6feb">{esc(tr("❓ Message types (legend)"))}</summary>'
            f'<div style="margin-top:8px">{body}</div></details>')
TAG_BADGE = {"error": "⚠️", "edit": "✏️", "command": "❯", "commit": "⎇", "test": "🧪", "url": "🔗", "web": "🌐"}

# ---- tool-call & tool-result pretty rendering -------------------------------
def _split_tool(txt):
    """'Name\\n{json}' → (name, parsed_input_or_None, raw_rest)."""
    name, _, rest = txt.partition("\n")
    try:
        return name.strip(), json.loads(rest), rest
    except Exception:
        return name.strip(), None, rest

def _tk_pre(s, cls="tk-out", cap=8000):
    s = str(s)
    s = s if len(s) <= cap else s[:cap] + "\n… (truncated)"
    return f'<pre class="{cls}">{esc(s)}</pre>'

def _diff_line(ln):
    s = ln[:1]
    cls = "d-add" if s == "+" else "d-del" if s == "-" else "d-ctx"
    return f'<div class="dl {cls}">{esc(ln) or "&nbsp;"}</div>'

def _patch_html(patch, filepath="", cap=800):
    """Render Claude's structuredPatch (a ready-made unified diff) as GitHub-style diff."""
    rows = [f'<div class="tk-file">📄 {esc(filepath)}</div>'] if filepath else []
    body, count = [], 0
    for h in patch:
        if not isinstance(h, dict):
            continue
        body.append(f'<div class="dl d-hunk">@@ -{h.get("oldStart","?")},{h.get("oldLines","?")}'
                    f' +{h.get("newStart","?")},{h.get("newLines","?")} @@</div>')
        for ln in h.get("lines", []):
            if count >= cap:
                body.append('<div class="dl d-ctx">… (diff truncated)</div>')
                break
            body.append(_diff_line(ln))
            count += 1
        if count >= cap:
            break
    rows.append(f'<div class="tk-diff">{"".join(body)}</div>')
    return "".join(rows)

def _difflib_html(old, new, filepath="", cap=800):
    """Diff two strings (Edit old→new) with stdlib difflib, GitHub-style."""
    lines = list(difflib.unified_diff(str(old).splitlines(), str(new).splitlines(), lineterm="", n=3))
    while lines and (lines[0].startswith("--- ") or lines[0].startswith("+++ ")):
        lines.pop(0)
    rows = [f'<div class="tk-file">📄 {esc(filepath)}</div>'] if filepath else []
    body = []
    for ln in lines[:cap]:
        body.append(f'<div class="dl d-hunk">{esc(ln)}</div>' if ln.startswith("@@") else _diff_line(ln))
    if len(lines) > cap:
        body.append('<div class="dl d-ctx">… (diff truncated)</div>')
    rows.append(f'<div class="tk-diff">{"".join(body)}</div>')
    return "".join(rows)

SHELL_TOOLS = {"Bash", "exec_command", "shell", "local_shell", "run_shell_command"}   # Claude / Codex / Gemini

def _tool_use_summary(txt):
    name, inp, _ = _split_tool(txt)
    prev = ""
    if isinstance(inp, dict):
        if name in SHELL_TOOLS:
            prev = inp.get("command") or inp.get("cmd") or ""
        elif name in EDIT_TOOLS:
            fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
            prev = short_path(fp) if fp else ""
        elif name == "Read":
            fp = inp.get("file_path") or inp.get("path") or ""
            prev = short_path(fp) if fp else ""
        elif name in ("Grep", "Glob"):
            prev = inp.get("pattern", inp.get("query", ""))
        else:
            prev = inp.get("description", "") or inp.get("prompt", "")
    prev = " ".join(str(prev).split())
    return name, (prev[:72] + "…") if len(prev) > 72 else prev

def tool_use_html(txt):
    name, inp, raw = _split_tool(txt)
    if not isinstance(inp, dict):
        return _tk_pre(raw)
    rows = []
    if name in SHELL_TOOLS:
        rows.append(_tk_pre(inp.get("command") or inp.get("cmd") or "", "tk-cmd"))
        meta = []
        if inp.get("run_in_background"):
            meta.append(tr("background"))
        if inp.get("workdir"):
            meta.append(esc(short_path(inp["workdir"])))
        if inp.get("timeout"):
            meta.append(f'timeout {inp["timeout"]}ms')
        if meta:
            rows.append(f'<div class="tk-meta">{" · ".join(meta)}</div>')
        if inp.get("description"):
            rows.append(f'<div class="tk-desc">{esc(inp["description"])}</div>')
    elif name in EDIT_TOOLS:
        fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
        old, new = inp.get("old_string"), inp.get("new_string")
        if isinstance(old, str) and isinstance(new, str):
            rows.append(_difflib_html(old, new, fp))          # Edit → real diff
        elif "content" in inp:                                # Write → new file body
            if fp:
                rows.append(f'<div class="tk-file">📄 {esc(fp)}</div>')
            rows.append(_tk_pre(inp.get("content", ""), "tk-out tk-add"))
        elif isinstance(inp.get("edits"), list):              # MultiEdit → each hunk
            if fp:
                rows.append(f'<div class="tk-file">📄 {esc(fp)}</div>')
            for e in inp["edits"]:
                if isinstance(e, dict) and isinstance(e.get("old_string"), str) and isinstance(e.get("new_string"), str):
                    rows.append(_difflib_html(e["old_string"], e["new_string"]))
        elif fp:
            rows.append(f'<div class="tk-file">📄 {esc(fp)}</div>')
    elif name == "Read":
        fp = inp.get("file_path") or inp.get("path") or ""
        extra = [f"{k} {inp[k]}" for k in ("offset", "limit") if inp.get(k)]
        rows.append(f'<div class="tk-file">📄 {esc(fp)}'
                    + (f' <span class="tk-meta">· {esc(" · ".join(extra))}</span>' if extra else "") + "</div>")
    elif name in ("Grep", "Glob"):
        rows.append(_tk_pre(inp.get("pattern", inp.get("query", "")), "tk-cmd"))
        if inp.get("path"):
            rows.append(f'<div class="tk-meta">{esc(tr("path"))}: {esc(inp["path"])}</div>')
    else:
        for k, v in inp.items():
            if isinstance(v, str) and ("\n" in v or len(v) > 80):
                rows.append(f'<div class="tk-lbl">{esc(k)}</div>{_tk_pre(v)}')
            else:
                vs = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                rows.append(f'<div class="tk-kv"><span class="tk-k">{esc(k)}</span> {esc(vs)}</div>')
    return "".join(rows) or _tk_pre(raw, cap=4000)

def _dict_result_html(d):
    # Edit/Write result: {filePath, oldString, newString, structuredPatch, content, …}
    if "structuredPatch" in d or ("oldString" in d and "newString" in d) or "filePath" in d:
        fp = d.get("filePath") or d.get("file_path") or ""
        patch = d.get("structuredPatch")
        if isinstance(patch, list) and patch:
            return _patch_html(patch, fp)
        old, new = d.get("oldString"), d.get("newString")
        if isinstance(old, str) and isinstance(new, str):
            return _difflib_html(old, new, fp)
        if isinstance(d.get("content"), str):                 # Write result
            head = f'<div class="tk-file">📄 {esc(fp)}</div>' if fp else ""
            return head + _tk_pre(d["content"], "tk-out tk-add")
        if fp:
            return f'<div class="tk-file">📄 {esc(fp)}</div><div class="tk-meta">{esc(tr("file saved"))}</div>'
    if "stdout" in d or "stderr" in d:
        rows = []
        stdout, stderr = d.get("stdout"), d.get("stderr")
        if stdout:
            rows.append(_tk_pre(stdout))
        elif not (stderr and str(stderr).strip()):
            rows.append(f'<div class="tk-meta">{esc(tr("(no output)"))}</div>')
        if stderr and str(stderr).strip():
            rows.append(f'<div class="tk-lbl">stderr</div>{_tk_pre(stderr, "tk-out tk-err")}')
        meta = []
        if d.get("interrupted"):
            meta.append(tr("⚠️ interrupted"))
        ec = d.get("exit_code", d.get("exitCode"))
        if isinstance(ec, int) and ec != 0:
            meta.append(f"exit {ec}")
        if meta:
            rows.append(f'<div class="tk-meta">{esc(" · ".join(meta))}</div>')
        return "".join(rows)
    for key in ("content", "text", "result", "output", "stdout"):
        v = d.get(key)
        if isinstance(v, str) and v.strip():
            return _tk_pre(v)
    f = d.get("file")
    if isinstance(f, dict) and isinstance(f.get("content"), str):
        return (f'<div class="tk-file">📄 {esc(str(f.get("filePath", "")))}</div>' + _tk_pre(f["content"]))
    return _tk_pre(json.dumps(d, ensure_ascii=False, indent=2))

def tool_result_html(txt):
    if txt.lstrip()[:1] in ("{", "["):
        try:
            data = json.loads(txt)
        except Exception:
            data = None
        if isinstance(data, dict):
            return _dict_result_html(data)
    return _tk_pre(txt)

# Tool calls worth showing expanded by default (compact & informative: the command,
# the diff, the file, the pattern). Everything else stays folded.
AUTO_OPEN_USE = set(EDIT_TOOLS) | {"Bash", "Read", "Grep", "Glob"}

def _result_kind(txt):
    """Classify a tool result so the view can decide what to expand by default.
    'edit' results are folded (the paired Edit call above already shows the diff)."""
    if txt.lstrip()[:1] in ("{", "["):
        try:
            d = json.loads(txt)
        except Exception:
            d = None
        if isinstance(d, dict):
            if "stdout" in d or "stderr" in d:
                return "bash"
            if "structuredPatch" in d or ("oldString" in d and "newString" in d) or "filePath" in d:
                return "edit"
    return "other"

def render_turn(gi, t, q="", thread_link=None):
    role, segs, ts, tags = t["role"], t["segs"], t["ts"], t["tags"]
    role_label, role_desc = tr(ROLE_LABEL.get(role, role)), tr(ROLE_DESC.get(role, ""))
    parts = []
    for kind, txt in segs:
        if kind == "text":
            parts.append(f'<div class="seg md">{md_html(txt, q)}</div>')
        elif kind == "channel":
            pc = parse_channel(txt)
            if pc:
                attrs, body = pc
                role_label = channel_label(attrs)
                srcbits = [b for b in (attrs.get("source"), attrs.get("chat_id") and f'chat {attrs["chat_id"]}',
                                       attrs.get("ts")) if b]
                role_desc = ROLE_DESC["channel"] + (" — " + " · ".join(srcbits) if srcbits else "")
                cap = f'<div class="chan-cap">{esc(" · ".join(srcbits))}</div>' if srcbits else ""
                parts.append(f'<div class="seg md chan-body">{md_html(body, q)}</div>{cap}')
            else:
                parts.append(f'<div class="seg md">{md_html(txt, q)}</div>')
        elif kind == "thinking":
            if (txt or "").strip():
                parts.append(f'<details class=fold><summary>{tr("💭 Thinking")}</summary><div class="seg md">{md_html(txt, q)}</div></details>')
            else:
                parts.append(tr('<div class="seg muted">💭 (thinking hidden)</div>'))
        elif kind == "tool_use":
            name, prev = _tool_use_summary(txt)
            sm = f"🔧 <b>{esc(name)}</b>" + (f' <span class="tk-sum">{esc(prev)}</span>' if prev else "")
            op = " open" if name in AUTO_OPEN_USE else ""
            parts.append(f'<details class="fold"{op}><summary>{sm}</summary><div class="tk-body">{tool_use_html(txt)}</div></details>')
        elif kind == "tool_result":
            rk = _result_kind(txt)
            if rk == "bash":
                lbl, op = tr("⚙ Run result"), " open"
            elif rk == "edit":
                lbl, op = tr("⚙ Edit result") + ' <span class=tk-sum>· ' + tr("same as the edit above — expand for diff") + '</span>', ""
            else:
                lbl, op = f'{tr("⚙ Tool result")} ({len(txt)} {tr("chars")})', (" open" if len(txt) < 1200 else "")
            parts.append(f'<details class="fold"{op}><summary>{lbl}</summary>'
                         f'<div class="tk-body">{tool_result_html(txt)}</div></details>')
        elif kind == "injected":
            tt = txt if len(txt) < 4000 else txt[:4000] + "\n… (truncated)"
            parts.append(f'<details class=fold><summary>{tr("Show injected context")}</summary><div class="seg mono">{esc(tt)}</div></details>')
    badges = "".join(f'<span class=badge title="{c}">{TAG_BADGE[c]}</span>' for c in
                     ("error", "edit", "command", "commit", "test", "url", "web") if c in tags)
    link = f'<a class=threadlink href="{thread_link}">{tr("↳ answer thread")}</a>' if thread_link else ""
    tstr = f'<span class=time>{fmt_ts_short(ts)}</span>' if ts else ""
    data = f' data-thread="{esc(thread_link)}"' if thread_link else ""
    cats = " ".join((["you"] if role == "you" else []) + sorted(tags))
    extra = ""
    if role == "assistant":
        sh = model_short(t.get("model", ""))
        if sh:
            extra += f'<span class=mdl>{esc(sh)}</span>'
        extra += tok_badge(t.get("tok"))
    elif role == "you" and t.get("qtok"):
        extra += tok_badge(t["qtok"], "tokb qtok")
    plink = f'<a class=permalink href="#t{gi}" title="{esc(tr("copy link to this message"))}">🔗</a>'
    who = (f'<div class=who><span title="{esc(role_desc)}">{role_label} {badges}</span>'
           f'<span class=whoR>{extra}{tstr}{plink}{link}</span></div>')
    return f'<div class="msg {role}" id="t{gi}" data-cats="{cats}"{data}>{who}{"".join(parts)}</div>'

# ---- HTML shell (token-replace, NOT str.format — so CSS/JS braces stay literal) ----
SHELL = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/favicon.svg">
<meta name="theme-color" content="#1f6feb">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="AI Session Search">
<title>%%TITLE%%</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font:14.5px/1.65 -apple-system,system-ui,'Apple SD Gothic Neo',sans-serif;margin:0;background:#f5f6f8;color:#1a1a1a}
@media(prefers-color-scheme:dark){body{background:#13151a;color:#e7e9ec}}
header{position:sticky;top:0;z-index:9;background:#1f6feb;color:#fff;padding:11px 18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header a.home{color:#fff;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap}
header form{margin:0;flex:1;display:flex;gap:7px;min-width:240px}
header input[type=search]{flex:1;padding:7px 12px;border:0;border-radius:8px;font-size:14px}
header select,header button{padding:7px 11px;border:0;border-radius:8px;font-size:13px;cursor:pointer}
header button{background:#0b4fc4;color:#fff}
header .advbtn{background:#1857b8}
.langsw{color:#fff;font-size:12px;white-space:nowrap;opacity:.9}
.langsw a{color:#cfe0ff;text-decoration:none;padding:0 2px}
.langsw a:hover{text-decoration:underline}
.langsw b{padding:0 2px}
.modal-ov{display:none;position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.5);align-items:center;justify-content:center;padding:16px}
.modal-ov.open{display:flex}
.modal{background:#fff;color:#1a1a1a;border-radius:16px;max-width:440px;width:100%;padding:22px 22px 18px;position:relative;box-shadow:0 20px 60px rgba(0,0,0,.35);max-height:92vh;overflow:auto}
@media(prefers-color-scheme:dark){.modal{background:#1b1e24;color:#e7e9ec}}
.modal-x{position:absolute;top:8px;right:12px;border:0;background:transparent;font-size:26px;line-height:1;color:#8a8f98;cursor:pointer}
.modal-h{margin:2px 0 4px;font-size:19px}
.modal-sub{margin:0 0 14px;color:#8a8f98;font-size:13px}
.modal-ill{margin:0 0 12px}
.illsvg{width:100%;height:auto;display:block;border:1px solid #e4e7eb;border-radius:10px;background:#f7f9fc}
@media(prefers-color-scheme:dark){.illsvg{border-color:#2a2e35;background:#141720}}
.modal-cap{font-size:12.5px;color:#444;margin-top:6px}
@media(prefers-color-scheme:dark){.modal-cap{color:#cfd4db}}
.modal-actions{display:flex;gap:8px;margin-top:16px}
.modal-primary{flex:1;padding:10px;border:0;border-radius:9px;background:#1f6feb;color:#fff;font-size:14px;font-weight:600;cursor:pointer}
.modal-secondary{padding:10px 14px;border:1px solid #cfd4db;border-radius:9px;background:transparent;color:#555;font-size:13px;cursor:pointer}
@media(prefers-color-scheme:dark){.modal-secondary{border-color:#3a3f47;color:#cfd4db}}
.modal-note{font-size:11.5px;color:#8a8f98;margin:10px 0 0;line-height:1.5}
.adv{flex-basis:100%;display:none;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 2px 2px}
.adv.open{display:flex}
.adv .advlbl{color:#fff;font-size:12px;opacity:.85}
.adv select,.adv input{padding:6px 9px;border:0;border-radius:7px;font-size:13px}
.wrap{max-width:940px;margin:0 auto;padding:16px}
.rootbar{max-width:940px;margin:0 auto;padding:8px 16px 0;display:flex;gap:7px;align-items:center;flex-wrap:wrap}
.rootbar .lbl{font-size:11.5px;color:#8a8f98}
.rootbar a{font-size:12px;text-decoration:none;padding:4px 11px;border-radius:14px;background:#e9edf2;color:#444;border:1px solid #dfe3e8}
.rootbar a.on{background:#0b4fc4;color:#fff;border-color:#0b4fc4}
@media(prefers-color-scheme:dark){.rootbar a{background:#1b1e24;color:#cfd4db;border-color:#3a3f47}}
.rootitem{display:inline-flex;align-items:center;gap:3px}
.rootbar a.rmroot{padding:2px 6px;background:transparent;border:0;color:#b04;font-size:11px}
.rootbar a.rmroot:hover{background:#fde;border-radius:8px}
.addroot{display:inline-flex;gap:5px;margin-left:4px}
.addroot input{padding:5px 10px;border:1px solid #cfd4db;border-radius:14px;font-size:12px;width:min(46vw,300px)}
.addroot button{padding:5px 11px;border:0;border-radius:14px;background:#16a34a;color:#fff;font-size:12px;cursor:pointer}
@media(prefers-color-scheme:dark){.addroot input{background:#1b1e24;color:#e7e9ec;border-color:#3a3f47}}
.card{background:#fff;border:1px solid #e4e7eb;border-radius:11px;padding:12px 16px;margin:9px 0}
@media(prefers-color-scheme:dark){.card{background:#1b1e24;border-color:#2a2e35}}
.card a.t{font-weight:650;color:#1f6feb;text-decoration:none;font-size:15.5px}
.meta{color:#8a8f98;font-size:12px;margin-top:3px}
.chip{display:inline-block;border-radius:6px;padding:1px 7px;font-size:11px;margin-right:5px;background:#eef1f4;color:#555}
@media(prefers-color-scheme:dark){.chip{background:#2a2e35;color:#aeb4bd}}
.preview{color:#666;font-size:12.5px;margin-top:5px}
@media(prefers-color-scheme:dark){.preview{color:#9aa0a8}}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0 10px}
.bar a{text-decoration:none;font-size:13px;padding:5px 11px;border-radius:8px;background:#e9edf2;color:#333}
.bar a.on{background:#1f6feb;color:#fff}
@media(prefers-color-scheme:dark){.bar a{background:#242830;color:#cfd4db}}
.psize{display:inline-flex;gap:5px;align-items:center;font-size:12px;color:#8a8f98;flex-wrap:wrap}
.psize select{padding:4px 8px;border-radius:7px}
.hint{font-size:11.5px;color:#9aa0a8}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.chip-f{cursor:pointer;border:1px solid #d0d4da;background:#fff;color:#333;border-radius:14px;padding:3px 11px;font-size:12px}
.chip-f.active{background:#1f6feb;color:#fff;border-color:#1f6feb}
.chip-f .cnt{opacity:.6;margin-left:3px}
@media(prefers-color-scheme:dark){.chip-f{background:#1b1e24;color:#cfd4db;border-color:#3a3f47}}
.digest{background:#f7f9fc;border:1px solid #dbe3ef}
@media(prefers-color-scheme:dark){.digest{background:#171b22;border-color:#283041}}
.digest b{color:#1f6feb}
.loopchip{display:inline-block;background:#fff3cd;color:#8a6d00;border:1px solid #ffe08a;border-radius:12px;padding:1px 9px;font-size:11.5px;font-weight:600;white-space:nowrap}
@media(prefers-color-scheme:dark){.loopchip{background:#3a3115;color:#f0d68a;border-color:#5c4d1c}}
table.stab{border-collapse:collapse;width:100%;margin-top:8px;font-size:12.5px}
table.stab th,table.stab td{text-align:right;padding:4px 8px;border-bottom:1px solid #e8ebef}
table.stab th:first-child,table.stab td:first-child{text-align:left}
table.stab thead th{color:#8a8f98;font-weight:600;cursor:help}
table.stab td a{color:#1f6feb;text-decoration:none}
table.stab tr.tot td{font-weight:700;border-top:2px solid #cdd2d8;border-bottom:0}
@media(prefers-color-scheme:dark){table.stab th,table.stab td{border-color:#2a2e35}}
.dfile{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#555;display:block}
@media(prefers-color-scheme:dark){.dfile{color:#9aa0a8}}
.msg{margin:12px 0;border:1px solid #e4e7eb;border-radius:11px;overflow:hidden;scroll-margin-top:64px}
@media(prefers-color-scheme:dark){.msg{border-color:#2a2e35}}
.who{padding:5px 14px;font-weight:700;font-size:12px;letter-spacing:.02em;display:flex;justify-content:space-between;align-items:center}
.you .who{background:#e3efff;color:#10488f}
.you{border-color:#bcd8ff}
.assistant .who{background:#e8f7ee;color:#157038}
.tool-result .who,.system .who,.subagent .who{background:#f0f1f3;color:#777}
.orchestrator .who{background:#f3eefe;color:#6b3fb5} .orchestrator{border-color:#d9c8f5}
.channel .who{background:#e2f4fb;color:#0b6a8f} .channel{border-color:#b7e2f2}
.chan-body{border-left:3px solid #34aadc}
.chan-cap{padding:2px 15px 8px;font-size:11px;color:#8a8f98;font-family:ui-monospace,Menlo,monospace;word-break:break-all}
@media(prefers-color-scheme:dark){
 .you .who{background:#16304f;color:#9ec5ff} .you{border-color:#244668}
 .assistant .who{background:#15331f;color:#7ddfa1}
 .orchestrator .who{background:#241a3a;color:#c2a8f0} .orchestrator{border-color:#3a2c5c}
 .channel .who{background:#0e2c39;color:#7fcbe6} .channel{border-color:#1d4a5e}
 .tool-result .who,.system .who,.subagent .who{background:#23262d;color:#9aa0a8}}
.subcard{background:#faf7ff;border:1px solid #e3d7f7}
@media(prefers-color-scheme:dark){.subcard{background:#1c1830;border-color:#352a52}}
.whoR{display:flex;gap:10px;align-items:center}
.time{font-weight:400;color:#9aa0a8;font-size:11px;font-variant-numeric:tabular-nums}
.sid{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;color:#9aa0a8;user-select:all}
code.sid{background:#eef1f4;padding:1px 5px;border-radius:4px;color:#555}
@media(prefers-color-scheme:dark){code.sid{background:#2a2e35;color:#aeb4bd}}
.srefcard>summary{cursor:pointer;font-weight:650;color:#1f6feb}
.srefbody{margin-top:8px}
.srow{display:flex;gap:10px;align-items:baseline;padding:2px 0;font-size:12.5px}
.srow .slbl{flex:0 0 110px;color:#8a8f98;font-size:11.5px;text-align:right}
.srow .sval{flex:1;min-width:0;word-break:break-all}
.spath{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;background:#eef1f4;padding:1px 5px;border-radius:4px;color:#444;user-select:all}
@media(prefers-color-scheme:dark){.spath{background:#2a2e35;color:#cfd4db}}
.slink code.sid{color:#1f6feb;text-decoration:underline}
@media(max-width:620px){.srow{flex-direction:column;gap:1px}.srow .slbl{flex:none;text-align:left}}
.badge{font-weight:400;font-size:11px;margin-left:2px}
.threadlink{font-weight:600;color:#1f6feb;text-decoration:none;font-size:11px;white-space:nowrap}
.tokb{font-weight:500;font-size:10.5px;color:#6b7280;font-variant-numeric:tabular-nums;background:#eef1f4;border-radius:5px;padding:0 6px;white-space:nowrap;cursor:help}
@media(prefers-color-scheme:dark){.tokb{background:#242830;color:#aeb4bd}}
.tokb .tokc{color:#a0a6ae}
.tokb.qtok{background:#e3efff;color:#10488f}
@media(prefers-color-scheme:dark){.tokb.qtok{background:#16304f;color:#9ec5ff}}
.mdl{font-weight:600;font-size:10.5px;color:#157038;background:#e8f7ee;border-radius:5px;padding:0 6px;white-space:nowrap}
.mdl .mdlc{font-weight:400;color:#5aa77a}
@media(prefers-color-scheme:dark){.mdl{background:#15331f;color:#7ddfa1}}
td.mdlcell{text-align:left;white-space:normal;line-height:1.9}
td.mdlcell .mdl{display:inline-block;margin:1px 0}
form.ssearch{display:flex;gap:7px;margin:10px 0;flex-wrap:wrap}
form.ssearch input[type=search]{flex:1;min-width:180px;padding:7px 12px;border:1px solid #cfd4db;border-radius:8px;font-size:13.5px}
@media(prefers-color-scheme:dark){form.ssearch input[type=search]{background:#1b1e24;color:#e7e9ec;border-color:#3a3f47}}
form.ssearch button{padding:7px 14px;border:0;border-radius:8px;background:#1f6feb;color:#fff;font-size:13px;cursor:pointer}
form.ssearch a.ssclear{align-self:center;font-size:12px;color:#b04;text-decoration:none}
.seg{padding:9px 15px;white-space:pre-wrap;word-break:break-word}
.seg.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#555;max-height:340px;overflow:auto;background:#fafbfc}
@media(prefers-color-scheme:dark){.seg.mono{color:#9aa0a8;background:#15171c}}
.muted{color:#9aa0a8;font-style:italic}
/* rendered markdown */
.seg.md{white-space:normal;word-break:break-word}
.md>*:first-child{margin-top:0}.md>*:last-child{margin-bottom:0}
.md-p{margin:8px 0}
.md-h{font-weight:700;margin:14px 0 6px;line-height:1.3}
.md-h1{font-size:1.35em}.md-h2{font-size:1.22em}.md-h3{font-size:1.1em}
.md-h4,.md-h5,.md-h6{font-size:1em;color:#555}
@media(prefers-color-scheme:dark){.md-h4,.md-h5,.md-h6{color:#aeb4bd}}
.md-list{margin:6px 0;padding-left:24px}
.md-list li{margin:2px 0}
.md-list .md-list{margin:2px 0}
.md-bq{margin:8px 0;padding:2px 12px;border-left:3px solid #cbd2da;color:#555}
@media(prefers-color-scheme:dark){.md-bq{border-color:#3a3f47;color:#9aa0a8}}
.md-hr{border:0;border-top:1px solid #e0e3e7;margin:12px 0}
.md-ic{background:#eef1f4;border-radius:4px;padding:.5px 5px;font-family:ui-monospace,Menlo,monospace;font-size:.9em}
@media(prefers-color-scheme:dark){.md-ic{background:#2a2e35}}
.md a{color:#1f6feb}
.md-codewrap{margin:8px 0;border:1px solid #e4e7eb;border-radius:8px;overflow:hidden}
@media(prefers-color-scheme:dark){.md-codewrap{border-color:#2a2e35}}
.md-clang{font:11px/1 ui-monospace,Menlo,monospace;color:#8a8f98;padding:6px 10px;background:#f0f1f3;border-bottom:1px solid #e4e7eb}
@media(prefers-color-scheme:dark){.md-clang{background:#23262d;border-color:#2a2e35}}
pre.md-code{margin:0;padding:10px 12px;overflow:auto;background:#fafbfc;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;white-space:pre;line-height:1.5}
@media(prefers-color-scheme:dark){pre.md-code{background:#15171c}}
.md-tablewrap{overflow-x:auto;margin:9px 0}
table.md-table{border-collapse:collapse;font-size:13px}
table.md-table th,table.md-table td{border:1px solid #dfe3e8;padding:5px 11px;text-align:left;vertical-align:top}
table.md-table thead th{background:#f0f3f7;font-weight:650;white-space:nowrap}
table.md-table tbody tr:nth-child(even){background:#fafbfc}
@media(prefers-color-scheme:dark){
 table.md-table th,table.md-table td{border-color:#2a2e35}
 table.md-table thead th{background:#23262d}
 table.md-table tbody tr:nth-child(even){background:#191c22}}
/* tool call / tool result */
.tk-body{padding:8px 14px;background:#fafbfc}
@media(prefers-color-scheme:dark){.tk-body{background:#15171c}}
.tk-sum{color:#8a8f98;font-family:ui-monospace,Menlo,monospace;font-size:11.5px;margin-left:4px}
pre.tk-cmd,pre.tk-out{margin:5px 0;padding:9px 12px;border-radius:7px;font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;overflow:auto;max-height:360px;line-height:1.5}
pre.tk-cmd{background:#0d1117;color:#e6edf3;border:1px solid #23272e}
pre.tk-cmd::before{content:"$ ";color:#7ee787}
pre.tk-out{background:#fff;color:#333;border:1px solid #e4e7eb}
@media(prefers-color-scheme:dark){pre.tk-out{background:#1b1e24;color:#cfd4db;border-color:#2a2e35}}
pre.tk-err{background:#fff5f5;color:#9b2c2c;border-color:#e5a0a3}
@media(prefers-color-scheme:dark){pre.tk-err{background:#2a1a1a;color:#f0a0a0;border-color:#5c2a2a}}
pre.tk-del{background:#fff0f0;color:#86181d;border-color:#f1b0b7}
pre.tk-add{background:#eaffee;color:#116329;border-color:#acefbf}
@media(prefers-color-scheme:dark){
 pre.tk-del{background:#2a1416;color:#f0a8ac;border-color:#5c2a2e}
 pre.tk-add{background:#12261a;color:#8ddfa3;border-color:#2c5c3a}}
.tk-desc{color:#8a8f98;font-style:italic;font-size:12px;margin:3px 0 2px}
.tk-meta{color:#8a8f98;font-size:11.5px;margin:3px 0}
.tk-file{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#1f6feb;margin:2px 0 4px;word-break:break-all}
.tk-lbl{font-size:11px;color:#8a8f98;margin:6px 0 1px;text-transform:uppercase;letter-spacing:.03em}
.tk-kv{font-size:12.5px;margin:2px 0}
.tk-k{font-family:ui-monospace,Menlo,monospace;color:#6b3fb5;font-size:11.5px}
@media(prefers-color-scheme:dark){.tk-k{color:#c2a8f0}}
.tk-diff{margin:5px 0;border:1px solid #e4e7eb;border-radius:7px;overflow:auto;max-height:440px;background:#fff;font-family:ui-monospace,Menlo,monospace;font-size:12px;line-height:1.55}
@media(prefers-color-scheme:dark){.tk-diff{background:#1b1e24;border-color:#2a2e35}}
.tk-diff .dl{padding:0 10px;white-space:pre-wrap;word-break:break-word;border-left:3px solid transparent}
.dl.d-add{background:#e6ffec;border-left-color:#2da44e;color:#116329}
.dl.d-del{background:#ffebe9;border-left-color:#cf222e;color:#82071e}
.dl.d-ctx{color:#57606a}
.dl.d-hunk{background:#f0f3f7;color:#57606a;font-weight:600}
@media(prefers-color-scheme:dark){
 .dl.d-add{background:#12261a;color:#7ee787}
 .dl.d-del{background:#2a1416;color:#ffa198}
 .dl.d-ctx{color:#9aa0a8}
 .dl.d-hunk{background:#23262d;color:#9aa0a8}}
details.fold{border-top:1px dashed #e0e3e7}
details.fold>summary{cursor:pointer;padding:5px 15px;font-size:12px;color:#8a8f98;user-select:none}
@media(prefers-color-scheme:dark){details.fold{border-color:#2a2e35}}
mark{background:#ffe27a;color:#000;padding:0 1px;border-radius:2px;font-weight:600}
.hl0{background:#ffe27a}.hl1{background:#9ae6b4}.hl2{background:#9ecbff}
.hl3{background:#fbb6ce}.hl4{background:#ffc38a}.hl5{background:#cbb2f7}
.hlkey{display:inline-block;font-size:11px;padding:0 6px;border-radius:3px;color:#000;margin-right:5px;font-weight:600}
.msg.kfocus{outline:3px solid #1f6feb;outline-offset:2px}
.msg:target{outline:3px solid #f59e0b;outline-offset:2px}
.pg{display:flex;gap:10px;justify-content:center;margin:18px 0}
.pg a{padding:7px 16px;border-radius:9px;background:#1f6feb;color:#fff;text-decoration:none;font-size:13px}
.snip{color:#666;font-size:12.5px;margin:4px 0 0;padding-left:10px;border-left:2px solid #d9dde2}
.snip a.snipjump{text-decoration:none}
.snip a.snipjump:hover .chip{background:#1f6feb;color:#fff}
.chip.kindchip{background:#fff3cd;color:#8a6d00}
@media(prefers-color-scheme:dark){.chip.kindchip{background:#3a3115;color:#f0d68a}}
.provbadge.gemini{background:#efe6ff;color:#5a2ca0}
@media(prefers-color-scheme:dark){.provbadge.gemini{background:#241a3a;color:#c2a8f0}}
.provbadge.codex{background:#e2f4fb;color:#0b6a8f}
.provbadge.claude{background:#e8f7ee;color:#157038}
@media(prefers-color-scheme:dark){.provbadge.codex{background:#0e2c39;color:#7fcbe6}.provbadge.claude{background:#15331f;color:#7ddfa1}}
.starbtn{border:0;background:transparent;cursor:pointer;font-size:16px;color:#c9ad3a;padding:0 2px;vertical-align:middle;line-height:1}
.starbtn.on{color:#e6b800}
.permalink{text-decoration:none;font-size:11px;opacity:.35;cursor:pointer}
.permalink:hover{opacity:1}
.sessnav{justify-content:space-between;font-size:12.5px}
.sessnav a{text-decoration:none;background:#e9edf2;color:#333;padding:6px 12px;border-radius:8px;max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(prefers-color-scheme:dark){.sessnav a{background:#242830;color:#cfd4db}}
kbd{background:#e7e9ec;border-radius:4px;padding:0 5px;font-size:11px;border:1px solid #c7ccd2;color:#333}
.codeart{margin:12px 0;border:1px solid #e4e7eb;border-radius:10px;overflow:hidden}
@media(prefers-color-scheme:dark){.codeart{border-color:#2a2e35}}
.codehead{display:flex;justify-content:space-between;align-items:center;padding:5px 12px;background:#f0f1f3;font-size:12px;font-family:ui-monospace,Menlo,monospace}
@media(prefers-color-scheme:dark){.codehead{background:#23262d;color:#cfd4db}}
.copy{cursor:pointer;border:0;background:#1f6feb;color:#fff;border-radius:6px;padding:3px 10px;font-size:11px}
pre.code{margin:0;padding:10px 13px;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;max-height:520px;overflow:auto;background:#fafbfc}
@media(prefers-color-scheme:dark){pre.code{background:#15171c;color:#dfe3e8}}
#minimap{position:fixed;right:3px;top:58px;bottom:8px;width:11px;display:flex;flex-direction:column;z-index:8;opacity:.6;border-radius:5px;overflow:hidden}
#minimap:hover{opacity:1;width:15px}
#minimap .seg{flex:1 1 auto;min-height:1px;cursor:pointer;border:0}
#minimap .seg:hover{outline:1px solid rgba(0,0,0,.5)}
.mm-error{background:#e5484d}.mm-you{background:#1f6feb}.mm-edit{background:#8b5cf6}
.mm-command{background:#16a34a}.mm-claude{background:#9bd3ad}.mm-orch{background:#a78bda}.mm-other{background:#cdd2d8}
@media(max-width:760px){#minimap{display:none}}
</style></head><body>
<header>
  <a class=home href="%%HOMEHREF%%">&#9776; %%HOMELABEL%%</a>
  <form action="/search" role=search>
    <input type=search name=q id=qbox placeholder='%%QPH%%' value="%%Q%%">
    <select name=scope title="%%SCOPETITLE%%">%%SCOPEOPTS%%</select>
    %%ROOTHIDDEN%%
    <button>%%SEARCHBTN%%</button>
    <button type=button id=advtoggle class=advbtn title="%%ADVTITLE%%">🔧 %%ADVLABEL%%%%ADVDOT%%</button>
    <div id=advpanel class="adv %%ADVOPEN%%">
      <span class=advlbl>%%PERIODLBL%%</span>
      <select name=days title="%%DAYSTITLE%%">%%DAYSOPTS%%</select>
      <span class=advlbl>%%ORLBL%%</span>
      <input type=date name=from value="%%FROM%%" title="%%FROMTITLE%%">
      <span class=advlbl>~</span>
      <input type=date name=to value="%%TO%%" title="%%TOTITLE%%">
    </div>
  </form>
  <button type=button id=installbtn class=advbtn style="display:none" title="%%INSTALLTITLE%%">%%INSTALLLBL%%</button>
  %%LANGSW%%
</header>
%%ROOTBAR%%
<div class=wrap>%%BODY%%</div>
%%INSTALLMODAL%%
<div id=minimap></div>
<script>
(function(){
  var cur=-1;
  function ys(){return Array.prototype.slice.call(document.querySelectorAll('.msg.you'));}
  function focusYou(i){var a=ys();if(!a.length)return;cur=((i%a.length)+a.length)%a.length;
    a.forEach(function(e){e.classList.remove('kfocus');});var el=a[cur];
    el.classList.add('kfocus');el.scrollIntoView({block:'center',behavior:'smooth'});}
  // advanced-search (Tools) toggle
  var at=document.getElementById('advtoggle');
  if(at){at.addEventListener('click',function(){document.getElementById('advpanel').classList.toggle('open');});}
  // language switch: set the cookie and reload the SAME url (keeps your search/query intact)
  document.querySelectorAll('.langsw a[data-lang]').forEach(function(a){
    a.addEventListener('click',function(e){e.preventDefault();
      document.cookie='cchlang='+a.getAttribute('data-lang')+';path=/;max-age=31536000;samesite=lax';
      location.reload();});
  });
  // Enter submits the search even mid-IME-composition (Korean/CJK: the first Enter would
  // otherwise only commit the character, so it took two presses).
  var qb=document.getElementById('qbox');
  if(qb)qb.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&(e.isComposing||e.keyCode===229)&&qb.form){
      var f=qb.form;setTimeout(function(){f.requestSubmit?f.requestSubmit():f.submit();},0);
    }
  });
  document.addEventListener('keydown',function(e){
    var tag=(e.target.tagName||'').toLowerCase();
    var typing=(tag==='input'||tag==='select'||tag==='textarea');
    // use e.code (physical key) so shortcuts work under non-Latin keyboard layouts (Korean/…)
    var C=e.code;
    if((C==='Slash'||e.key==='/')&&!typing){e.preventDefault();var s=document.getElementById('qbox');if(s){s.focus();s.select();}return;}
    if(e.key==='Escape'&&typing){e.target.blur();return;}
    if(typing)return;
    if(C==='KeyJ'||C==='KeyN'){if(ys().length){e.preventDefault();focusYou(cur+1);}}
    else if(C==='KeyK'||C==='KeyP'){if(ys().length){e.preventDefault();focusYou(cur-1);}}
    else if(e.key==='Enter'&&cur>=0){var a=ys();var l=a[cur]&&a[cur].getAttribute('data-thread');if(l)location.href=l;}
  });
  // copy buttons (code view)
  document.addEventListener('click',function(e){
    if(e.target.classList.contains('copy')){
      var pre=e.target.closest('.codeart').querySelector('pre.code');
      var txt=pre?pre.textContent:'';
      if(navigator.clipboard){navigator.clipboard.writeText(txt);}
      var o=e.target.textContent;e.target.textContent='Copied \u2713';setTimeout(function(){e.target.textContent=o;},1200);
    }
  });
  // "Install as app" — a big explainer modal (⌘-Tab + extensions still work), then the native prompt
  var deferredPrompt=null, ibtn=document.getElementById('installbtn');
  var mov=document.getElementById('installmodal');
  var standalone=window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches;
  function openInstall(){if(mov)mov.classList.add('open');}
  function closeInstall(){if(mov)mov.classList.remove('open');}
  if(ibtn)ibtn.addEventListener('click',openInstall);
  var ic=document.getElementById('installclose'); if(ic)ic.addEventListener('click',closeInstall);
  var il=document.getElementById('installlater'); if(il)il.addEventListener('click',closeInstall);
  if(mov)mov.addEventListener('click',function(e){if(e.target===mov)closeInstall();});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&mov&&mov.classList.contains('open'))closeInstall();});
  var inow=document.getElementById('installnow');
  if(inow)inow.addEventListener('click',function(){
    if(deferredPrompt){deferredPrompt.prompt();deferredPrompt=null;if(ibtn)ibtn.style.display='none';closeInstall();}
    else{var h=document.getElementById('installhow');if(h)h.style.display='';}
  });
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferredPrompt=e;
    if(ibtn)ibtn.style.display='';
    try{if(!standalone&&!localStorage.getItem('aiss:installtip')){localStorage.setItem('aiss:installtip','1');openInstall();}}catch(_){}
  });
  window.addEventListener('appinstalled',function(){if(ibtn)ibtn.style.display='none';closeInstall();});
  if(standalone&&ibtn)ibtn.style.display='none';
  // localStorage stars (browser-local; server never sees them, transcripts stay read-only)
  function starred(sid){try{return localStorage.getItem('aiss:star:'+sid)==='1';}catch(_){return false;}}
  function paintStar(b){b.textContent=starred(b.getAttribute('data-sid'))?'\u2605':'\u2606';b.classList.toggle('on',starred(b.getAttribute('data-sid')));}
  document.addEventListener('click',function(e){
    var b=e.target.closest&&e.target.closest('.starbtn');
    if(b){e.preventDefault();var sid=b.getAttribute('data-sid');
      try{if(starred(sid))localStorage.removeItem('aiss:star:'+sid);else localStorage.setItem('aiss:star:'+sid,'1');}catch(_){}
      document.querySelectorAll('.starbtn[data-sid="'+sid+'"]').forEach(paintStar);return;}
    // message permalink \u2192 copy full URL with #tN
    var pl=e.target.closest&&e.target.closest('.permalink');
    if(pl){e.preventDefault();var url=location.href.split('#')[0]+pl.getAttribute('href');
      if(navigator.clipboard){navigator.clipboard.writeText(url);}
      history.replaceState(null,'',pl.getAttribute('href'));
      var o=pl.textContent;pl.textContent='\u2713';setTimeout(function(){pl.textContent=o;},1000);return;}
  });
  // event/error filter chips
  var active={};
  function applyFilter(){
    var keys=Object.keys(active).filter(function(k){return active[k];});
    document.querySelectorAll('.msg').forEach(function(m){
      if(!keys.length){m.style.display='';return;}
      var cats=(m.getAttribute('data-cats')||'').split(' ');
      var hit=keys.some(function(k){return cats.indexOf(k)>=0;});
      m.style.display=hit?'':'none';
    });
    buildMinimap();
  }
  document.querySelectorAll('.chip-f').forEach(function(b){
    b.addEventListener('click',function(){
      var c=b.getAttribute('data-cat');
      if(c==='*'){active={};document.querySelectorAll('.chip-f').forEach(function(x){x.classList.remove('active');});applyFilter();return;}
      active[c]=!active[c];b.classList.toggle('active',active[c]);applyFilter();
    });
  });
  // structure minimap (built from visible .msg)
  function catOf(m){
    var cats=(m.getAttribute('data-cats')||'').split(' ');
    var role=m.className.split(' ')[1];
    if(cats.indexOf('error')>=0)return 'error';
    if(role==='you')return 'you';
    if(cats.indexOf('edit')>=0)return 'edit';
    if(cats.indexOf('command')>=0)return 'command';
    if(role==='assistant')return 'claude';
    if(role==='orchestrator')return 'orch';
    return 'other';
  }
  var PRIO=['error','you','edit','command','orch','claude','other'];
  function buildMinimap(){
    var mm=document.getElementById('minimap');if(!mm)return;mm.innerHTML='';
    var msgs=Array.prototype.slice.call(document.querySelectorAll('.msg')).filter(function(m){return m.style.display!=='none';});
    if(!msgs.length)return;
    var N=msgs.length, buckets=N, per=1;
    if(N>1200){buckets=600;per=Math.ceil(N/buckets);}
    for(var bi=0;bi<N;bi+=per){
      var slice=msgs.slice(bi,bi+per), best='other', bp=99;
      slice.forEach(function(m){var c=catOf(m),p=PRIO.indexOf(c);if(p>=0&&p<bp){bp=p;best=c;}});
      (function(target){
        var d=document.createElement('div');d.className='seg mm-'+best;
        d.addEventListener('click',function(){target.scrollIntoView({block:'center',behavior:'smooth'});});
        mm.appendChild(d);
      })(slice[0]);
    }
  }
  window.addEventListener('load',function(){
    var p=document.getElementById('perf');
    if(p&&window.performance){p.textContent=' \u00b7 browser render '+Math.round(performance.now())+'ms';}
    document.querySelectorAll('.starbtn').forEach(paintStar);
    buildMinimap();
  });
})();
</script>
</body></html>"""

SCOPES = {"all": "All", "human": "🧑 Only me", "claude": "✦ Only Claude",
          "chat": "Conversation only (no tools/system)", "code": "🧩 Code/edits", "tool": "🔧 Commands/files"}
DAY_CHOICES = {"": "All time", "7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days"}

def shell(title, body, q="", scope="all", root=None, days="", from_="", to=""):
    root = root if root in ROOTS else ROOT
    multi = len(ROOTS) > 1
    home = ("/?root=" + urllib.parse.quote(root)) if multi else "/"
    hidden = f'<input type=hidden name=root value="{esc(root)}">' if multi else ""
    def _rootlink(r):
        # on a search page, keep the query when switching folders (re-run search there)
        if q:
            params = {"q": q, "scope": scope, "root": r}
            for k, v in (("days", days), ("from", from_), ("to", to)):
                if v:
                    params[k] = v
            return "/search?" + urllib.parse.urlencode(params)
        return "/?root=" + urllib.parse.quote(r)
    links = []
    for r in ROOTS:
        on = "on" if r == root else ""
        rm = (f'<a class=rmroot href="/delroot?path={urllib.parse.quote(r)}" title="{esc(tr("remove from list"))}">✕</a>'
              if r in SAVED_ROOTS else "")
        glyph = root_glyph(r)
        links.append(f'<span class=rootitem><a class="{on}" href="{_rootlink(r)}">'
                     f'{glyph}{esc(short_path(r))}</a>{rm}</span>')
    addform = ('<form class=addroot action="/addroot" method=get>'
               f'<input name=path placeholder="{esc(tr("Add a folder — paste a path (…/.claude/projects)"))}">'
               f'<button>{tr("➕ Add")}</button></form>')
    rootbar = f'<div class=rootbar><span class=lbl>📁 {tr("Folders")}:</span>{"".join(links)}{addform}</div>'
    scopeopts = "".join(f'<option value="{k}"{" selected" if k == scope else ""}>{esc(tr(v))}</option>'
                        for k, v in SCOPES.items())
    daysopts = "".join(f'<option value="{k}"{" selected" if k == days else ""}>{esc(tr(v))}</option>'
                       for k, v in DAY_CHOICES.items())
    adv_active = bool(days or from_ or to)
    langs = available_langs()
    langsw = ""
    if len(langs) > 1:
        cur = cur_lang()
        parts = [(f'<b>{c}</b>' if c == cur else f'<a href="?lang={c}" data-lang="{c}">{c}</a>') for c in langs]
        langsw = f'<span class=langsw title="{esc(tr("language"))}">🌐 ' + " ".join(parts) + '</span>'
    install_modal = (
        '<div id=installmodal class=modal-ov><div class=modal role=dialog aria-modal=true>'
        f'<button class=modal-x id=installclose aria-label="close">&times;</button>'
        f'<h2 class=modal-h>{esc(tr("Install as an app"))}</h2>'
        f'<p class=modal-sub>{esc(tr("Runs in its own window — no browser tab, no address bar. It stays a local, read-only viewer."))}</p>'
        f'<div class=modal-ill>{SVG_CMDTAB}<div class=modal-cap>✓ {esc(tr("Shows up in ⌘-Tab and the Dock as its own app — most people never realize a web app can do this."))}</div></div>'
        f'<div class=modal-ill>{SVG_EXT}<div class=modal-cap>✓ {esc(tr("Your Chrome extensions still work inside it (it is still Chrome under the hood)."))}</div></div>'
        f'<div class=modal-actions><button id=installnow class=modal-primary>{esc(tr("⬇ Install now"))}</button>'
        f'<button id=installlater class=modal-secondary>{esc(tr("Maybe later"))}</button></div>'
        f'<p class=modal-note id=installhow style="display:none">{tr("If it does not prompt, use the Chrome ⋮ menu → “Cast, save &amp; share” → “Install page as app”.")}</p>'
        '</div></div>')
    repl = {
        "%%INSTALLMODAL%%": install_modal,
        "%%TITLE%%": esc(title), "%%BODY%%": body, "%%Q%%": esc(q),
        "%%SCOPEOPTS%%": scopeopts, "%%DAYSOPTS%%": daysopts,
        "%%FROM%%": esc(from_), "%%TO%%": esc(to),
        "%%ADVOPEN%%": "open" if adv_active else "", "%%ADVDOT%%": " ●" if adv_active else "",
        "%%HOMEHREF%%": home, "%%ROOTHIDDEN%%": hidden, "%%ROOTBAR%%": rootbar,
        "%%HOMELABEL%%": esc(tr("AI Session Search")),
        "%%QPH%%": esc(tr('Search: words = AND · "exact phrase"  ( / key )')),
        "%%SCOPETITLE%%": esc(tr("search scope")), "%%SEARCHBTN%%": esc(tr("Search")),
        "%%ADVTITLE%%": esc(tr("advanced search (date range, …)")), "%%ADVLABEL%%": esc(tr("Tools")),
        "%%PERIODLBL%%": esc(tr("Period")), "%%DAYSTITLE%%": esc(tr("quick period")),
        "%%ORLBL%%": esc(tr("or exact")), "%%FROMTITLE%%": esc(tr("start date")),
        "%%TOTITLE%%": esc(tr("end date")), "%%LANGSW%%": langsw,
        "%%INSTALLLBL%%": esc(tr("⬇ Install app")),
        "%%INSTALLTITLE%%": esc(tr("install as a standalone app (own window, shows in the app switcher)")),
    }
    out = SHELL
    for k, v in repl.items():
        out = out.replace(k, v)
    return out

# ---- handlers ---------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body):
        b = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _redirect(self, loc):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        # DNS-rebinding guard: a hostile site pointing its own hostname at
        # 127.0.0.1 would send its Host header — reject anything non-local.
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        if host not in ("127.0.0.1", "localhost", "::1", ""):
            return self.send_error(403, "forbidden host")
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        g = lambda k, d="": qs.get(k, [d])[0]

        # language: ?lang=xx sets a cookie then redirects clean; else cookie → default.
        if "lang" in qs:
            code = re.sub(r"[^a-zA-Z_-]", "", g("lang"))[:12]
            rest = {k: v for k, v in qs.items() if k != "lang"}
            loc = u.path + ("?" + urllib.parse.urlencode(rest, doseq=True) if rest else "")
            self.send_response(302)
            self.send_header("Location", loc or "/")
            self.send_header("Set-Cookie", f"cchlang={code}; Path=/; Max-Age=31536000; SameSite=Lax")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        cm = re.search(r"cchlang=([a-zA-Z_-]+)", self.headers.get("Cookie", "") or "")
        set_lang(cm.group(1) if cm else _DEFAULT_LANG)

        def gint(k, d=0):
            try:
                return max(0, int(g(k, str(d)) or d))
            except ValueError:
                return d

        if u.path in ("/favicon.svg", "/favicon.ico"):
            b = ICON_SVG.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if u.path == "/manifest.webmanifest":
            # lets Chrome/Edge "Install as app" → standalone window (own Cmd+Tab/Dock entry)
            man = json.dumps({
                "name": "AI Session Search", "short_name": "CC History",
                "start_url": "/", "scope": "/", "display": "standalone",
                "background_color": "#13151a", "theme_color": "#1f6feb",
                "icons": [{"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml",
                           "purpose": "any maskable"}],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(man)))
            self.end_headers()
            return self.wfile.write(man)
        root = active_root(g("root"))
        if u.path == "/":
            return self._send(self.index(g("proj"), g("sort", "date"), g("dir", ""), root))
        if u.path == "/search":
            return self._send(self.search(g("q"), g("scope", "all"), root,
                                          g("days", ""), g("proj", ""), g("from", ""), g("to", "")))
        if u.path == "/session":
            return self._send(self.session(g("p"), g("q"), g("filter", "all"),
                                           gint("off"), g("lim", ""), g("thread", ""), g("view", ""),
                                           g("goto", ""), g("sq", "")))
        if u.path == "/subagent":
            return self._send(self.subagent(g("p"), g("parent"), g("q")))
        if u.path in ("/addroot", "/delroot"):
            # CSRF guard for state-changing routes: modern browsers send
            # Sec-Fetch-Site; block explicit cross-site, allow same-origin,
            # direct navigation, and header-less clients (curl).
            sfs = (self.headers.get("Sec-Fetch-Site") or "").lower()
            if sfs in ("cross-site", "same-site"):
                return self.send_error(403, "cross-site request rejected")
            return self.addroot(g("path")) if u.path == "/addroot" else self.delroot(g("path"))
        self.send_error(404)

    # ---- add / remove a project folder at runtime (persisted) ----
    def addroot(self, path):
        np = normalize_root(path)
        if np:
            with _ROOTLOCK:
                if np not in ROOTS:
                    ROOTS.append(np)
                if np not in DEFAULT_ROOTS and np not in SAVED_ROOTS:
                    SAVED_ROOTS.append(np)
                    _save_saved(SAVED_ROOTS)
            return self._redirect("/?root=" + urllib.parse.quote(np))
        body = (f'<div class=card><b>{tr("Could not add that folder.")}</b>'
                f'<p class=meta>{tr("Input")}: <code class=sid>{esc(path)}</code></p>'
                f'<p>{tr("It must be a <b>projects</b> folder that exists and contains <code>*/*.jsonl</code> sessions. ")}'
                f'{tr("(Giving the <code>.claude</code> folder or its parent also works — it finds <code>projects</code> automatically.)")}<br>'
                f'{tr("e.g.")} <code>/Volumes/backup/.claude/projects</code></p>'
                f'<p><a href="/">{tr("← Back")}</a></p></div>')
        return self._send(shell(tr("Add folder failed"), body))

    def delroot(self, path):
        p = os.path.abspath(os.path.expanduser(path or ""))
        with _ROOTLOCK:
            if p in SAVED_ROOTS:
                SAVED_ROOTS.remove(p)
                _save_saved(SAVED_ROOTS)
            if p in ROOTS and p not in DEFAULT_ROOTS:
                ROOTS.remove(p)
        return self._redirect("/")

    # ---- index ----
    def index(self, proj_filter="", sort="date", dir_="", root=None):
        root = root if root in ROOTS else ROOT
        all_items = get_index(root)
        proj_cwd = {}
        for it in all_items:
            if it["proj"] not in proj_cwd and it.get("cwd"):
                proj_cwd[it["proj"]] = short_path(it["cwd"])
        projs = sorted({it["proj"] for it in all_items}, key=lambda p: proj_cwd.get(p, p).lower())
        items = [it for it in all_items if it["proj"] == proj_filter] if proj_filter else list(all_items)

        # sort: field + direction
        SORTF = {"date": "Date", "mine": "My messages", "title": "Title", "size": "Size"}
        SORTKEY = {"date": lambda x: x["mtime"], "mine": lambda x: x["n"]["you"],
                   "title": lambda x: x["title"].lower(), "size": lambda x: x["size"]}
        DEFDIR = {"date": "desc", "mine": "desc", "title": "asc", "size": "desc"}
        if sort not in SORTF:
            sort = "date"
        if dir_ not in ("asc", "desc"):
            dir_ = DEFDIR[sort]
        items = sorted(items, key=SORTKEY[sort], reverse=(dir_ == "desc"))

        def q(**kw):
            parts = [f"{k}={urllib.parse.quote(str(v))}" for k, v in kw.items() if v]
            if len(ROOTS) > 1:
                parts.append("root=" + urllib.parse.quote(root))
            return "/?" + "&".join(parts) if parts else "/"

        # ---- project insight ----
        def _toktip(tk):
            return (f'{tr("Input")} {tk["in"]:,} · {tr("Output")} {tk["out"]:,} · {tr("Cache write")} {tk["cw"]:,} · '
                    f'{tr("Cache read")} {tk["cr"]:,} ({tr("cache read is reused context, cheap")})')
        if proj_filter:
            st = agg_stats(items)
            label = proj_cwd.get(proj_filter, proj_filter)
            loopline = (f' · <span class=loopchip>🔁 {tr("autonomous build-loop")} {st["loop"]}</span>') if st["loop"] else ""
            hidden_root = f'<input type=hidden name=root value="{esc(root)}">' if len(ROOTS) > 1 else ""
            statsblock = (
                f'<div class="card digest"><b>📁 {esc(label)}</b>{loopline}'
                f'<div style="margin-top:6px">{tr("Total")} <b>{st["sessions"]}</b> {tr("sessions")} · '
                f'🧑 {tr("sessions I joined")} <b>{st["my_sessions"]}</b> · {tr("my messages")} <b>{st["my_msgs"]}</b></div>'
                f'<div>{tr("Total size")} <b>{fmt_size(st["size"])}</b> · 🧑 {tr("size of sessions I joined")} <b>{fmt_size(st["my_size"])}</b></div>'
                f'<div style="margin-top:6px" title="{esc(_toktip(st["tok"]))}"><b>{tr("Tokens")}</b> {tok_badge(st["tok"])} '
                f'<span class=meta>{tr("Input")} {st["tok"]["in"]:,} · {tr("Output")} {st["tok"]["out"]:,} · '
                f'{tr("Cache")} {st["tok"]["cw"]+st["tok"]["cr"]:,}</span></div>'
                + (f'<div style="margin-top:4px"><b>{tr("Models")}</b> {models_badge(st["models"])}</div>' if st["models"] else "")
                + f'<div class=meta>✦ Claude {st["asst"]} · ⚙ {tr("tool results")} {st["tool"]}</div>'
                f'<form class=ssearch method=get action=/search style="margin-top:8px">'
                f'<input type=hidden name=proj value="{esc(proj_filter)}">{hidden_root}'
                f'<input type=search name=q placeholder="🔎 {tr("Search this folder only…")}"><button>{tr("Search")}</button></form></div>')
        else:
            by = {}
            for it in all_items:
                by.setdefault(it["proj"], []).append(it)
            proj_stats = {p: agg_stats(its) for p, its in by.items()}
            ov = []
            for p, s in sorted(proj_stats.items(), key=lambda kv: -kv[1]["tok"]["out"]):
                lc = f'🔁 {s["loop"]}' if s["loop"] else ""
                ov.append(f'<tr><td><a href="{q(proj=p, sort=sort, dir=dir_)}">{esc(proj_cwd.get(p, p))}</a></td>'
                          f'<td>{s["sessions"]}</td><td>{s["my_sessions"]}</td><td>{s["my_msgs"]}</td>'
                          f'<td title="{esc(_toktip(s["tok"]))}">{fmt_tok(s["tok"]["out"])}</td>'
                          f'<td class=mdlcell>{models_badge(s["models"])}</td>'
                          f'<td>{fmt_size(s["size"])}</td><td>{lc}</td></tr>')
            tot = agg_stats(all_items)
            table = (f'<table class=stab><thead><tr><th>{tr("Project (folder)")}</th><th title="{esc(tr("session count"))}">{tr("Sessions")}</th>'
                     f'<th title="{esc(tr("sessions a human joined"))}">{tr("My part")}</th><th title="{esc(tr("my total messages"))}">{tr("My msgs")}</th>'
                     f'<th title="{esc(tr("output (generated) tokens. hover = full input/output/cache breakdown"))}">{tr("Out tokens")}</th>'
                     f'<th title="{esc(tr("models used in this folder and response counts"))}">{tr("Models")}</th>'
                     f'<th title="{esc(tr("total size of all sessions"))}">{tr("Size")}</th>'
                     f'<th title="{esc(tr("autonomous build-loop sessions"))}">🔁</th></tr></thead><tbody>' + "".join(ov)
                     + f'<tr class=tot><td>{tr("Total")} {len(by)} {tr("folders")}</td><td>{tot["sessions"]}</td><td>{tot["my_sessions"]}</td>'
                     f'<td>{tot["my_msgs"]}</td><td title="{esc(_toktip(tot["tok"]))}">{fmt_tok(tot["tok"]["out"])}</td>'
                     f'<td class=mdlcell>{models_badge(tot["models"])}</td><td>{fmt_size(tot["size"])}</td>'
                     f'<td>{tot["loop"] or ""}</td></tr></tbody></table>')
            statsblock = (f'<details class="card" open><summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                          f'📊 {tr("Project stats")} ({len(by)} {tr("folders")}) · {tr("by output tokens")}</summary>{table}'
                          f'<p class=meta style="padding:0 4px">💡 {tr("Cache-read tokens are reused each turn (cheap) — ")}'
                          f'{tr("gauge real usage by output/input/cache-write.")}</p></details>')

        arrow = "▼" if dir_ == "desc" else "▲"
        sortbar = [f'<div class=bar><span class=meta>{tr("Sort")}:</span>']
        for k, lbl in SORTF.items():
            if k == sort:
                nd = "asc" if dir_ == "desc" else "desc"
                sortbar.append(f'<a class=on href="{q(proj=proj_filter, sort=k, dir=nd)}" '
                               f'title="{esc(tr("click to flip direction"))}">{tr(lbl)} {arrow}</a>')
            else:
                sortbar.append(f'<a href="{q(proj=proj_filter, sort=k, dir=DEFDIR[k])}">{tr(lbl)}</a>')
        sortbar.append("</div>")

        projbar = [f'<div class=bar><span class=meta>{tr("Projects")}:</span>',
                   f'<a class="{"" if proj_filter else "on"}" href="{q(sort=sort, dir=dir_)}">{tr("All")}</a>']
        for p in projs:
            projbar.append(f'<a class="{"on" if p==proj_filter else ""}" '
                           f'href="{q(proj=p, sort=sort, dir=dir_)}">{esc(proj_cwd.get(p, p))}</a>')
        projbar.append("</div>")
        rows = []
        for it in items:
            link = "/session?p=" + urllib.parse.quote(it["path"])
            loopchip = f' <span class=loopchip>🔁 {tr("autonomous build-loop")}</span>' if it.get("loop") else ""
            tk = it.get("tok")
            tokbit = f' · {tok_badge(tk)}' if (tk and any(tk.values())) else ""
            mdlbit = ""
            if it.get("models"):
                sh = model_short(max(it["models"].items(), key=lambda kv: kv[1])[0])
                if sh:
                    mdlbit = f' · <span class=mdl>{esc(sh)}</span>'
            rows.append(
                f'<div class=card data-sid="{esc(it["sid"])}">'
                f'<button class=starbtn data-sid="{esc(it["sid"])}">☆</button> '
                f'<a class=t href="{link}">{esc(it["title"])}</a>{loopchip}'
                f'<div class=meta><span class=chip>{esc(proj_label(it))}</span>'
                f'{counts_html(it["n"])}{tokbit}{mdlbit} · '
                f'{fmt_mtime(it["mtime"])} · {fmt_size(it["size"])} · '
                f'<span class=sid>id {esc(it["sid"])}</span></div>'
                + (f'<div class=preview>{esc(it["preview"])}</div>' if it["preview"] else "") + '</div>')
        head = (f'<p class=meta>{len(items)} {tr("sessions")} · <b>🧑 {tr("You")}</b> {tr("marks — by a verified ruleset —")} '
                f'<b>{tr("only what you actually typed")}</b> · {esc(root)}</p>'
                f'<p class=meta>{tr("Legend")}: 🧑 {tr("You")} · ✦ Claude · ⚙ {tr("Tool result")} · ⓘ {tr("System / injected")} '
                f'<span class=hint>{tr("(hover a number for its meaning; expand ❓ below for the full legend)")}</span></p>'
                + legend_html())
        if not items and not proj_filter:
            head += (f'<div class=card><b>{tr("No sessions.")}</b>'
                     f'<p class=meta>{tr("No <code>&lt;project&gt;/&lt;uuid&gt;.jsonl</code> files found under")} {esc(root)}. '
                     + tr('Make sure this is a folder where Claude Code has run at least once, or add another folder with ➕ above.') + '</p></div>')
        return shell(tr("AI Session Search"), head + statsblock + "".join(sortbar) + "".join(projbar) + "".join(rows), root=root)

    # ---- search ----
    def search(self, q, scope, root=None, days="", proj="", from_="", to=""):
        root = root if root in ROOTS else ROOT
        if scope not in SCOPES:
            scope = "all"
        if days not in DAY_CHOICES:
            days = ""
        q = (q or "")[:200]                                # query length cap (CPU/output guard)
        sq = parse_search_query(q)
        terms, phrases, fields, neg = sq["terms"], sq["phrases"], sq["fields"], sq["neg"]
        if fields.get("role"):                             # role:me / role:claude override scope
            scope = {"me": "human", "i": "human", "you": "human", "human": "human",
                     "claude": "claude", "assistant": "claude"}.get(fields["role"][0], scope)
        id_vals = fields.get("id", [])
        field_terms = {k: v for k, v in fields.items() if k in FIELD_KIND}
        hl_terms = terms + phrases + [v for k, vals in field_terms.items() for v in vals]
        hlq = " ".join([f'"{t}"' for t in hl_terms])
        if not (terms or phrases or fields or neg):
            return shell(tr("Search"), f'<p class=meta>{tr("Enter a query. Multiple words = all must match (AND), ")}'
                                 f'{tr("&quot;quotes&quot; = exact phrase. Each word gets its own color. ")}'
                                 f'{tr("(press <kbd>/</kbd> to focus the search box)")}</p>',
                         q, scope, root, days, from_, to)
        t0 = time.perf_counter()
        index = get_index(root)
        proj_cwd = {}
        for it in index:
            if it["proj"] not in proj_cwd and it.get("cwd"):
                proj_cwd[it["proj"]] = short_path(it["cwd"])
        mtimes = {it["path"]: it["mtime"] for it in index}
        titles = {it["path"]: it["title"] for it in index}
        metas = {it["path"]: it for it in index}

        # date window: explicit from/to overrides the preset days dropdown
        lo = _date_ts(from_)
        hi = _date_ts(to, end=True)
        if lo is None and hi is None and days:
            lo = time.time() - int(days) * 86400

        RESULT_CAP = 300
        results = []
        for path in session_files(root):
            mt = mtimes.get(path, 0)
            if (lo is not None and mt < lo) or (hi is not None and mt >= hi):
                continue
            it = metas.get(path, {})
            if proj and it.get("proj") != proj:
                continue
            sid = it.get("sid") or os.path.basename(path)[:-6]
            forked = it.get("forked", "")
            # session-level metadata match: session-id / branched-from / workspace / path / title
            meta_terms = terms + id_vals
            meta_blob = " ".join(filter(None, [sid, forked, it.get("cwd", ""),
                                               it.get("start_cwd", ""), path, titles.get(path, "")])).lower()
            meta_hit = bool(meta_terms) and all(t in meta_blob for t in meta_terms)
            is_ref = meta_hit and any(_looks_ref(t) and (t in sid or (forked and t in forked)) for t in meta_terms)

            rows, blob, tokens = _rows_blob(path)
            need = terms + phrases
            # cheap pre-filter (substring over the cached blob, ~C-speed): a match needs
            # every term somewhere in the body or metadata — skip the expensive work otherwise.
            if need and not is_ref and not field_terms and not meta_hit:
                if any((t not in blob) and (t not in meta_blob) for t in need):
                    continue

            active = [r for r in rows if _scope_ok(r, scope)]
            if neg and any(nt in blob for nt in neg):
                continue
            fields_ok = (not field_terms) or _fields_ok(active, field_terms)
            hit = match_session(active, terms, phrases, blob, tokens) if (fields_ok and (terms or phrases)) else None
            field_only = fields_ok and bool(field_terms) and not (terms or phrases)
            if not hit and not field_only and not meta_hit:
                continue

            # highlight/snippet terms: plain terms/phrases, plus field values for a field-only query
            fvals = [v for vals in field_terms.values() for v in vals]
            snip_terms = (terms + phrases) or fvals
            by_gi = {}
            for r in active:
                by_gi.setdefault(r["gi"], []).append(r)
            hit_gis = hit["gis"][:6] if hit else (
                [r["gi"] for r in active if any(v in r["text"].lower() for v in fvals)][:6] if field_only else [])
            hits = []
            for gi in hit_gis:
                rs = by_gi.get(gi, [])
                row = next((r for r in rs if any(t in r["text"].lower() for t in snip_terms)), rs[0] if rs else None)
                if row:
                    hits.append((gi, row["role"], _snippet(row["text"], snip_terms)))

            # title matches are a strong intent signal (users recall session titles)
            title_low = titles.get(path, "").lower()
            ntitle = sum(1 for t in terms + phrases if t in title_low)
            score = 0.0
            if is_ref:
                score += 3000
            score += 450 * ntitle
            if meta_hit:
                score += 20
            if hit:
                ww = hit["ww"]
                if hit["kind"] == "row":
                    score += 1000 + (200 if hit["all_word"] else 0) + sum(10 * min(c, 5) for c in ww)
                elif hit["kind"] == "cluster":
                    score += (400 if hit["span"] <= 3 else 250) + sum(5 * min(c, 5) for c in ww)
                else:
                    score += 100
                if phrases:
                    score += 300
            elif field_only:
                score += 500
            score += 300 * bool(fields.get("file")) + 200 * bool(fields.get("code")) + 200 * bool(fields.get("cmd"))
            results.append({"path": path, "title": titles.get(path, tr("(untitled)")),
                            "proj": it.get("proj") or os.path.basename(os.path.dirname(path)),
                            "n": len(hits), "score": score, "mtime": mt,
                            "all_word": bool(hit) and hit.get("all_word"),
                            "hit_kind": hit["kind"] if hit else "", "hits": hits,
                            "meta_hit": meta_hit, "sid": sid, "forked": forked, "cwd": it.get("cwd", "")})
        results.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)
        truncated = len(results) - RESULT_CAP
        results = results[:RESULT_CAP]
        ms = int((time.perf_counter() - t0) * 1000)

        def searchurl(**kw):
            params = {"q": q, "scope": scope}
            for k, v in (("days", days), ("from", from_), ("to", to)):
                if v:
                    params[k] = v
            if len(ROOTS) > 1:
                params["root"] = root
            params.update({k: v for k, v in kw.items() if v})
            return "/search?" + urllib.parse.urlencode(params)

        projbar = ""
        matched_projs = sorted({r["proj"] for r in results} | ({proj} if proj else set()),
                               key=lambda p: proj_cwd.get(p, p).lower())
        if matched_projs and (len(matched_projs) > 1 or proj):
            chips = [f'<a class="{"on" if not proj else ""}" href="{searchurl()}">{tr("All")}</a>']
            for p in matched_projs:
                chips.append(f'<a class="{"on" if p == proj else ""}" href="{searchurl(proj=p)}">'
                             f'{esc(proj_cwd.get(p, p))}</a>')
            projbar = f'<div class=bar><span class=meta>{tr("Projects")}:</span>' + "".join(chips) + '</div>'

        KIND_CHIP = {"cluster": tr("nearby"), "session": tr("in session")}
        rows = []
        for r in results:
            def jump(gi):
                return ("/session?p=" + urllib.parse.quote(r["path"]) + "&q=" + urllib.parse.quote(hlq)
                        + f"&goto={gi}")
            openurl = jump(r["hits"][0][0]) if r["hits"] else (
                "/session?p=" + urllib.parse.quote(r["path"]) + (("&q=" + urllib.parse.quote(hlq)) if hlq else ""))
            exact = "" if (r["all_word"] or not r["hits"]) else f' <span class=hint title="{esc(tr("some words matched only as a substring of another word"))}">≈ {tr("partial")}</span>'
            kchip = f' <span class="chip kindchip">{KIND_CHIP[r["hit_kind"]]}</span>' if r["hit_kind"] in KIND_CHIP else ""
            metaline = ""
            if r.get("meta_hit"):
                bits = [f'🔗 <code class=sid>{hl(r["sid"], hlq)}</code>']
                if r.get("cwd"):
                    bits.append(f'📂 {hl(short_path(r["cwd"]), hlq)}')
                if r.get("forked"):
                    bits.append(f'⑂ <code class=sid>{hl(r["forked"], hlq)}</code>')
                metaline = f'<div class=snip><span class=chip>{tr("ref")}</span> ' + " · ".join(bits) + '</div>'
            snips = "".join(
                f'<div class=snip><a class=snipjump href="{jump(gi)}">'
                f'<span class=chip>{ROLE_LABEL.get(role, role)}</span></a>{hl(s, hlq)}</div>'
                for gi, role, s in r["hits"])
            cnt = f'({r["n"]})' if r["hits"] else tr('reference match')
            short = proj_cwd.get(r["proj"], r["proj"])
            rows.append(f'<div class=card><a class=t href="{openurl}">{hl(r["title"], hlq)}</a> '
                        f'<span class=meta>{cnt}</span>{exact}{kchip}'
                        f'<div class=meta><span class=chip>{esc(short)}</span></div>{metaline}{snips}</div>')

        keys = " ".join(f'<span class="hlkey hl{i % HL_COLORS}">{esc(t)}</span>' for i, t in enumerate(hl_terms))
        when = (f' · {esc(from_ or "…")}~{esc(to or "…")}' if (from_ or to) else
                (" · " + tr(DAY_CHOICES[days]) if days else ""))
        more = f' · <span class=hint>(+{truncated} {tr("more, refine to narrow")})</span>' if truncated > 0 else ""
        head = (f'<p class=meta>{keys} — {len(results)} {tr("sessions matched")} ({tr("by relevance")}) · {tr(SCOPES[scope])}{when} · {ms}ms{more} · '
                f'📁 {esc(short_path(root))} · <span class=hint>{tr("click a snippet to jump there")}</span></p>')
        return shell(f"{tr('Search')}: {q}", head + projbar + ("".join(rows) or f"<p class=meta>{tr('No results.')}</p>"),
                     q, scope, root, days, from_, to)

    # ---- session ----
    def session(self, path, q="", filt="all", off=0, lim_raw="", thread="", view="", goto="", sq=""):
        rt = root_for_path(path)
        if not path or not os.path.exists(path) or rt is None:
            return shell("?", f"<p>{tr('Session not found.')}</p>")
        t0 = time.perf_counter()
        loaded = load_session(path)          # one cached pass (turns + meta + per-question tokens)
        turns, meta = loaded["turns"], loaded["meta"]
        prov = provider_of(path)
        sid = ({"codex": _codex_sid, "gemini": _gemini_sid}.get(prov, lambda p: os.path.basename(p)[:-6]))(path)
        you_idx = [i for i, t in enumerate(turns) if t["role"] == "you"]

        def url(**kw):
            params = {"p": path}
            params.update({k: v for k, v in kw.items() if v not in (None, "")})
            return "/session?" + urllib.parse.urlencode(params)

        workspace, started, forked = meta.get("cwd", ""), meta.get("start_cwd", ""), meta.get("forked", "")
        def _srow(lbl, val):
            return f'<div class=srow><span class=slbl>{lbl}</span><span class=sval>{val}</span></div>'
        mrows = []
        if workspace:
            mrows.append(_srow("Workspace", f'<code class=spath>{esc(workspace)}</code>'))
        if started and started != workspace:
            mrows.append(_srow("Started in",
                               f'<code class=spath>{esc(started)}</code>'
                               f' <span class=hint>· {tr("folder the session started in (the file moved to a different workspace)")}</span>'))
        mrows.append(_srow(tr("Session file"), f'<code class=spath>{esc(path)}</code>'))
        mrows.append(_srow("session-id", f'<code class=sid>{esc(sid)}</code>'))
        if forked:
            pf = find_session_by_sid(rt, forked)
            fv = (f'<a class=slink href="/session?p={urllib.parse.quote(pf)}"><code class=sid>{esc(forked)}</code></a>'
                  if pf else f'<code class=sid>{esc(forked)}</code> <span class=hint>· {tr("not in this folder")}</span>')
            mrows.append(_srow("Branched from", fv))
        if meta.get("branch"):
            mrows.append(_srow("git", f'<code class=sid>{esc(meta["branch"])}</code>'))
        resume = {"codex": f"codex resume {esc(sid)}", "claude": f"claude --resume {esc(sid)}"}.get(prov)
        if resume:
            mrows.append(_srow(tr("Resume"), f'<code class=sid>{resume}</code>'))
        mrows.append(_srow(tr("Stored in"), f'📁 {esc(short_path(rt))} · {fmt_ts(meta["last_ts"])}'))
        refcard = f'<details class="card srefcard" open><summary>📍 {tr("Session info (Session Reference)")}</summary><div class=srefbody>{"".join(mrows)}</div></details>'
        star = f'<button class=starbtn data-sid="{esc(sid)}" title="{esc(tr("star this session (saved in your browser)"))}">☆</button>'
        PROV_LABEL = {"codex": "🌀 Codex", "gemini": "✨ Gemini", "claude": "✴️ Claude Code"}
        pbadge = f'<span class="chip provbadge {prov}">{PROV_LABEL.get(prov, prov)}</span> '
        head = (f'<h3 style="margin:4px 0 8px">{star} {pbadge}{esc(meta["title"])}'
                + (f' <span class=loopchip>🔁 {tr("autonomous build-loop")}</span>' if meta.get("loop") else "") + '</h3>')
        # prev/next session in the same project (work spans sessions)
        prev, nxt = adjacent_sessions(rt, path)
        if prev or nxt:
            pl = (f'<a href="/session?p={urllib.parse.quote(prev["path"])}">← {tr("prev")}: {esc(prev["title"][:38])}</a>'
                  if prev else "<span></span>")
            nl = (f'<a href="/session?p={urllib.parse.quote(nxt["path"])}">{tr("next")}: {esc(nxt["title"][:38])} →</a>'
                  if nxt else "")
            head += f'<div class="bar sessnav">{pl}{nl}</div>'
        head += refcard + legend_html()

        # subagent banner
        subs = [subagent_brief(s) for s in subagent_files(path)]
        if subs:
            sub_items = "".join(
                f'<div class=card style="margin:6px 0"><a class=t '
                f'href="/subagent?p={urllib.parse.quote(sb["path"])}&parent={urllib.parse.quote(path)}'
                f'{("&q="+urllib.parse.quote(q)) if q else ""}">🤖 {esc(sb["brief"])}</a>'
                f'<div class=meta>{(tr("workflow")+" "+esc(sb["wf"])+" · ") if sb["wf"] else ""}'
                f'{sb["n"]} {tr("messages")} · agent {esc(sb["agentId"][:10])}</div></div>'
                for sb in subs)
            head += (f'<details class=fold style="margin:10px 0;border:1px solid #d9c8f5;border-radius:11px" open>'
                     f'<summary style="padding:9px 14px;color:#6b3fb5;font-weight:600">'
                     f'🤖 {tr("Sub-agents this session spawned")}: {len(subs)} — {tr("expand")}</summary>'
                     f'<div style="padding:0 12px 8px">{sub_items}</div></details>')

        # extracted-fact digest
        d = session_digest(turns)
        dl = []
        if any(meta["tok"].values()):
            tk = meta["tok"]
            dl.append(f'<div style="margin-bottom:6px"><b>{tr("Tokens")}</b> {tok_badge(tk)} '
                      f'<span class=meta>{tr("Input")} {tk["in"]:,} · {tr("Output")} {tk["out"]:,} · '
                      f'{tr("Cache write")} {tk["cw"]:,} · {tr("Cache read")} {tk["cr"]:,}</span></div>')
        if meta["models"]:
            dl.append(f'<div style="margin-bottom:6px"><b>{tr("Models")}</b> {models_badge(meta["models"])}</div>')
        dl.append(f'✏️ {tr("edits")} {d["edits"]} ({len(d["files"])} {tr("files")}) · ❯ {tr("commands")} {d["cmds"]} · '
                  f'🧪 {tr("tests")} {d["tests"]} · ⚠️ {tr("errors")} {d["errors"]} · ⎇ {tr("commits")} {len(d["commits"])} · 🌐 {tr("web")} {d["webs"]}')
        if d["files"]:
            dl.append(f'<div style="margin-top:7px"><b>{tr("Files touched")}</b> ' +
                      "".join(f'<span class=dfile>{esc(short_path(f))}</span>' for f in d["files"][:25]) +
                      (f'<span class=meta>… +{len(d["files"])-25} {tr("more")}</span>' if len(d["files"]) > 25 else "") + '</div>')
        if d["commits"]:
            dl.append(f'<div style="margin-top:7px"><b>{tr("Commits")}</b> ' +
                      "".join(f'<span class=dfile>⎇ {esc(c)}</span>' for c in d["commits"][:12]) + '</div>')
        if d["prs"]:
            dl.append(f'<div style="margin-top:7px"><b>{tr("PRs / issues")}</b> ' +
                      "".join(f'<a class=dfile href="{esc(u)}" target=_blank>{esc(u)}</a>' for u in d["prs"][:10]) + '</div>')
        digest = (f'<details class="card digest" open><summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                  f'📊 {tr("Session summary (extracted facts)")}</summary><div style="margin-top:8px">{"".join(dl)}</div></details>')
        head += digest

        # in-session search box (always available)
        head += (f'<form class=ssearch method=get action=/session>'
                 f'<input type=hidden name=p value="{esc(path)}">'
                 f'<input type=search name=sq value="{esc(sq)}" placeholder="🔎 {tr("Search this session… (words=AND, &quot;phrase&quot;)")}">'
                 f'<button>{tr("Search")}</button>'
                 + (f'<a class=ssclear href="{url()}">✕ {tr("clear")}</a>' if sq else "") + '</form>')

        # ---- in-session search (sq) ----
        if sq.strip():
            terms = parse_query(sq)
            match_gis = [gi for gi, role, txt in search_turns(path)
                         if terms and all(t in txt.lower() for t in terms)]
            body = [render_turn(gi, turns[gi], sq, url(thread=gi) if turns[gi]["role"] == "you" else None)
                    for gi in match_gis]
            ms = int((time.perf_counter() - t0) * 1000)
            bar = (f'<div class=bar><a href="{url()}">← {tr("full conversation")}</a>'
                   f'<span class=meta>🔎 <b>{esc(sq)}</b> — {len(match_gis)} {tr("messages matched in this session")} · {ms}ms'
                   f'<span id=perf></span></span></div>')
            return shell(meta["title"][:50], head + bar
                         + ("".join(body) or f"<p class=meta>{tr('No matches in this session.')}</p>"), q, root=rt)

        # ---- CODE view ----
        if view == "code":
            arts = extract_code(turns)
            bar = (f'<div class=bar><a href="{url(q=q)}">← {tr("to conversation")}</a>'
                   f'<a class=on href="{url(view="code", q=q)}">🧩 {tr("Code only")}</a>'
                   f'<span class=meta>{len(arts)} {tr("code/edit blocks")} · {tr("server")} {int((time.perf_counter()-t0)*1000)}ms<span id=perf></span></span></div>')
            body = []
            for a in arts:
                lbl = ("✏️ " + short_path(a["label"])) if a["kind"] == "edit" else ("``` " + a["label"])
                body.append(
                    f'<div class=codeart><div class=codehead><span><a href="{url(q=q)}#t{a["gi"]}" '
                    f'style="text-decoration:none">{esc(lbl)}</a> <span class=time>{fmt_ts_short(a["ts"])}</span></span>'
                    f'<button class=copy>{tr("Copy")}</button></div><pre class=code>{esc(a["body"])}</pre></div>')
            return shell(meta["title"][:50], head + bar + ("".join(body) or f"<p class=meta>{tr('No code/edits.')}</p>"), q, root=rt)

        # ---- thread mode ----
        if thread != "":
            try:
                gi = int(thread)
            except ValueError:
                gi = -1
            if gi < 0 or gi >= len(turns) or turns[gi]["role"] != "you":
                return shell("?", head + f"<p class=meta>{tr('Thread not found.')}</p>", q, root=rt)
            nxt = next((i for i in you_idx if i > gi), len(turns))
            body = [render_turn(i, turns[i], q, url(thread=i, q=q) if turns[i]["role"] == "you" else None)
                    for i in range(gi, nxt)]
            ms = int((time.perf_counter() - t0) * 1000)
            bar = ('<div class=bar>'
                   f'<a href="{url(filter="human", q=q)}">← {tr("Only-me list")}</a>'
                   f'<a href="{url(q=q)}#t{gi}">{tr("see in full")}</a>'
                   f'<span class=meta>🧑 {tr("question → answer thread")} ({nxt-gi}) · {tr("server")} {ms}ms<span id=perf></span></span></div>')
            return shell(meta["title"][:50], head + bar + "".join(body), q, root=rt)

        # ---- normal / human-filtered + pagination ----
        lim = parse_lim(lim_raw) if lim_raw != "" else DEFAULT_LIM
        idxs = you_idx if filt == "human" else range(len(turns))
        view_turns = [(i, turns[i]) for i in idxs]
        total = len(view_turns)
        # goto=<gi>: jump straight to that turn — flip to the page containing it
        goto_gi = None
        if goto != "":
            try:
                goto_gi = int(goto)
            except ValueError:
                goto_gi = None
        if goto_gi is not None:
            pos = next((k for k, (i, _) in enumerate(view_turns) if i == goto_gi), None)
            if pos is None and filt == "human":       # match is a non-human turn
                filt = "all"
                view_turns = [(i, turns[i]) for i in range(len(turns))]
                total = len(view_turns)
                pos = goto_gi if goto_gi < total else None
            if pos is not None and lim is not None:
                off = (pos // lim) * lim
        page = view_turns if lim is None else view_turns[off:off + lim]
        body = []
        for gi, t in page:
            tl = url(thread=gi, q=q) if t["role"] == "you" else None
            body.append(render_turn(gi, t, q, tl))
        if goto_gi is not None:
            body.append(
                '<script>window.addEventListener("load",function(){'
                f'var el=document.getElementById("t{goto_gi}");'
                'if(el){el.classList.add("kfocus");el.scrollIntoView({block:"center"});}});</script>')
        ms = int((time.perf_counter() - t0) * 1000)

        n = meta["n"]
        toggles = ('<div class=bar>'
                   f'<a class="{"on" if filt=="all" else ""}" href="{url(q=q, lim=lim_raw)}">{tr("Show all")}</a>'
                   f'<a class="{"on" if filt=="human" else ""}" href="{url(filter="human", q=q, lim=lim_raw)}">🧑 {tr("Only me")}</a>'
                   f'<a href="{url(view="code", q=q)}">🧩 {tr("Code only")}</a>'
                   f'<span class=meta>{counts_html(n, system=True)}</span>'
                   '</div>')
        # event-filter chips (counts over ALL turns)
        cc = {"you": 0, "error": 0, "edit": 0, "command": 0, "commit": 0, "test": 0, "url": 0}
        for t in turns:
            if t["role"] == "you":
                cc["you"] += 1
            for c in t["tags"]:
                if c in cc:
                    cc[c] += 1
        CHIP_LBL = {"you": "🧑 My messages", "error": "⚠️ Errors", "edit": "✏️ Edits", "command": "❯ Commands",
                    "commit": "⎇ Commits", "test": "🧪 Tests", "url": "🔗 URL"}
        chips = [f'<div class=chips><button class=chip-f data-cat="*">{tr("All")}</button>']
        for c, lbl in CHIP_LBL.items():
            if cc[c]:
                chips.append(f'<button class=chip-f data-cat="{c}">{tr(lbl)}<span class=cnt>{cc[c]}</span></button>')
        chips.append('</div>')

        opts = []
        for v in LIM_OPTIONS:
            opts.append(f'<option value="{v}"{" selected" if (lim is not None and lim == v) else ""}>{v}</option>')
        opts.append(f'<option value="all"{" selected" if lim is None else ""}>{tr("all")}({total})</option>')
        sizeform = ('<form class=psize method=get action=/session>'
                    f'<input type=hidden name=p value="{esc(path)}">'
                    + (f'<input type=hidden name=q value="{esc(q)}">' if q else "")
                    + (f'<input type=hidden name=filter value="{esc(filt)}">' if filt == "human" else "")
                    + f'{tr("per page")} <select name=lim onchange="this.form.submit()">' + "".join(opts) + '</select>'
                    + f'<span class=hint>· {tr("server")} {ms}ms<span id=perf></span> · {tr("showing")} {len(page)}/{total} · '
                      f'<kbd>j</kbd>/<kbd>k</kbd> {tr("my messages")}, <kbd>Enter</kbd> {tr("answer thread")} · {tr("chips/minimap reflect the current page")}</span>'
                    + '</form>')
        pg = []
        if lim is not None:
            if off > 0:
                pg.append(f'<a href="{url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=max(0, off-lim))}">← {tr("Prev")}</a>')
            if off + lim < total:
                pg.append(f'<a href="{url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=off+lim)}">{tr("Next")} {min(lim, total-off-lim)} →</a>')
        pgbar = f'<div class=pg>{"".join(pg)}</div>' if pg else ""
        return shell(meta["title"][:50], head + toggles + "".join(chips) + sizeform + pgbar + "".join(body) + pgbar, q, root=rt)

    # ---- subagent thread ----
    def subagent(self, path, parent="", q=""):
        rt = root_for_path(path)
        if not path or not os.path.exists(path) or rt is None:
            return shell("?", f"<p>{tr('Sub-agent transcript not found.')}</p>")
        t0 = time.perf_counter()
        turns = classify_turns(path, sub=True)
        sb = subagent_brief(path)
        body = [render_turn(i, t, q, None) for i, t in enumerate(turns)]
        ms = int((time.perf_counter() - t0) * 1000)
        back = ""
        if parent and os.path.exists(parent):
            back = f'<a href="/session?p={urllib.parse.quote(parent)}{("&q="+urllib.parse.quote(q)) if q else ""}">← {tr("to parent session")}</a>'
        bar = ('<div class=bar>' + back
               + f'<span class=meta>🤖 {tr("Sub-agent")} · {(tr("workflow")+" "+esc(sb["wf"])+" · ") if sb["wf"] else ""}'
               f'agent {esc(sb["agentId"][:12])} · {len(turns)} {tr("messages")} · {tr("server")} {ms}ms<span id=perf></span></span></div>')
        head = (f'<p class=meta>📋 {tr("Instruction")}: {esc(sb["brief"])}</p><h3 style="margin:4px 0">🤖 {tr("Sub-agent conversation")}</h3>')
        return shell(tr("Sub-agent"), head + bar + "".join(body), q, root=rt)

# ---- main -------------------------------------------------------------------
def make_server(host="127.0.0.1", port=DEFAULT_PORT):
    """Build the HTTP server (port 0 → ephemeral; used by tests)."""
    return ThreadingHTTPServer((host, port), H)

def _warm_cache(root):
    """Pre-parse index + search rows so the first request isn't cold. Best-effort."""
    try:
        get_index(root)
        for p in session_files(root):
            _rows_blob(p)
    except Exception:
        pass

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ai-session-search",
        description="Read-only local web viewer for Claude Code session transcripts.")
    ap.add_argument("root", nargs="?", default=None,
                    help="projects dir to browse (default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to listen on (default {DEFAULT_PORT})")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1; changing this exposes your transcripts to the network)")
    ap.add_argument("--roots", default="", metavar="DIR[,DIR...]",
                    help="extra project roots to offer in the in-app folder switcher")
    ap.add_argument("--open", action="store_true", help="open the browser after starting")
    ap.add_argument("--lang", default=os.environ.get("CCH_LANG", "en"),
                    help="default UI language code (e.g. en, ko); needs locales/<code>.json. "
                         "Also via CCH_LANG; switch live in the header. Default: en")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)
    global _DEFAULT_LANG
    _DEFAULT_LANG = (args.lang or "en").strip() or "en"

    # Windows: redirected stdout defaults to cp1252 and crashes on non-Latin text/emoji
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    # Validate the EXPLICITLY requested root before configure() — otherwise a
    # typo'd path silently falls back to the default root and serves that.
    if args.root and not os.path.isdir(os.path.expanduser(args.root)):
        ap.exit(2, f"projects dir not found: {args.root}\n")
    extra = [p for p in args.roots.split(",") if p]
    configure(args.root, extra)
    if not os.path.isdir(ROOT):
        ap.exit(2, f"projects dir not found: {ROOT}\n")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"  \u26a0\ufe0f  Binding {args.host}: your transcripts are exposed on the network. Use only on a trusted network.")

    try:
        srv = make_server(args.host, args.port)
    except OSError:
        print(f"  \u26a0\ufe0f  Port {args.port} is in use — opening on a temporary port instead. (set one with --port)")
        srv = make_server(args.host, 0)
    url = f"http://{args.host}:{srv.server_address[1]}"
    print(f"\n  AI Session Search v{__version__} → {url}")
    print(f"  Browsing: {ROOT}" + (f"  (+{len(ROOTS)-1} more, switchable)" if len(ROOTS) > 1 else ""))
    print("  (close this window or press Ctrl-C to stop)\n")
    if args.open:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    # warm the index + search cache for every root in the background, so the FIRST
    # search is fast too (even after switching folders).
    threading.Thread(target=lambda: [_warm_cache(r) for r in ROOTS], daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
