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
import base64
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

from ._icons import ICON_PNG_192, ICON_PNG_256

__version__ = "3.1.0"

# App icon — a speech bubble with a person mark (🧑 = "you"), the app's core idea.
# App icon: glass "AI" on a blue→green gradient with purple/cyan glows. Used as the
# favicon, PWA/apple-touch icon (rasterized by the browser), and the selected app in
# the install-screen ⌘-Tab strap. The brand gradient here matches the title-bar band.
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1" gradientTransform="rotate(-50,0.5,0.5)"><stop offset="0" stop-color="#0084ff"/><stop offset="0.52" stop-color="#1061b7"/><stop offset="0.93" stop-color="#b0ff29"/></linearGradient><radialGradient id="g0" cx="0.4" cy="0.21" r="0.684"><stop offset="0" stop-color="rgb(169,138,255)" stop-opacity="1"/><stop offset="1" stop-color="rgb(169,138,255)" stop-opacity="0"/></radialGradient><radialGradient id="g1" cx="0.84" cy="0.86" r="0.684"><stop offset="0" stop-color="rgb(105,245,247)" stop-opacity="0.88"/><stop offset="1" stop-color="rgb(105,245,247)" stop-opacity="0"/></radialGradient><clipPath id="sq"><rect x="100" y="100" width="824" height="824" rx="180"/></clipPath><filter id="fx0" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceAlpha" stdDeviation="14" result="shb"/><feOffset in="shb" dy="10" result="sho"/><feFlood flood-color="#04352C" flood-opacity="0.45" result="shc"/><feComposite in="shc" in2="sho" operator="in" result="shadow"/><feGaussianBlur in="SourceAlpha" stdDeviation="40" result="glb"/><feFlood flood-color="#CFFFEE" flood-opacity="1" result="glc"/><feComposite in="glc" in2="glb" operator="in" result="glow"/><feComponentTransfer in="SourceGraphic" result="body"><feFuncA type="linear" slope="1"/></feComponentTransfer><feOffset in="SourceAlpha" dx="-7.5" dy="-7.5" result="lo1"/><feComposite in="SourceAlpha" in2="lo1" operator="out" result="lo2"/><feGaussianBlur in="lo2" stdDeviation="6.5" result="lo3"/><feFlood flood-color="#0A4A3E" flood-opacity="0.77" result="lo4"/><feComposite in="lo4" in2="lo3" operator="in" result="lowlight"/><feOffset in="SourceAlpha" dx="7.5" dy="7.5" result="hi1"/><feComposite in="SourceAlpha" in2="hi1" operator="out" result="hi2"/><feGaussianBlur in="hi2" stdDeviation="6.5" result="hi3"/><feFlood flood-color="#FFFFFF" flood-opacity="0.79" result="hi4"/><feComposite in="hi4" in2="hi3" operator="in" result="highlight"/><feMerge><feMergeNode in="shadow"/><feMergeNode in="glow"/><feMergeNode in="body"/><feMergeNode in="lowlight"/><feMergeNode in="highlight"/></feMerge></filter></defs>
<g clip-path="url(#sq)"><rect x="100" y="100" width="824" height="824" fill="url(#bg)"/><rect x="100" y="100" width="824" height="824" fill="url(#g0)"/><rect x="100" y="100" width="824" height="824" fill="url(#g1)"/></g>
<g filter="url(#fx0)"><text x="512" y="512" font-family="-apple-system,Helvetica,Arial,sans-serif" font-size="730" font-weight="700" fill="#FFFFFF" text-anchor="middle" dominant-baseline="central">AI</text></g>
</svg>"""

# App icons for the install-screen ⌘-Tab strap. Finder is the REAL macOS Tahoe icon
# (Wikimedia Commons, embedded as a data URI) — Apple artwork; revisit before any public
# release. The rest are hand-drawn lookalikes. The strap itself is real CSS liquid glass
# (backdrop-filter) — see the .ct-* rules in PAGE CSS.
_IC_FINDER = """<img alt="Finder" src="data:image/png;base64,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">"""
_IC_SAFARI = """<svg viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><defs>
<linearGradient id="icsb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fdfeff"/><stop offset="1" stop-color="#e3ecf9"/></linearGradient>
<linearGradient id="ics" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4fb0ff"/><stop offset="1" stop-color="#1d6ced"/></linearGradient></defs>
<rect width="56" height="56" rx="13" fill="url(#icsb)"/><circle cx="28" cy="28" r="17.5" fill="url(#ics)"/>
<g stroke="#ffffff" stroke-opacity="0.75" stroke-width="1.1"><path d="M28 12.5v3M28 40.5v3M12.5 28h3M40.5 28h3"/></g>
<path d="M37.5 18.5 30.3 30.3 25.7 25.7 Z" fill="#ff4b4b"/><path d="M18.5 37.5 25.7 25.7 30.3 30.3 Z" fill="#ffffff"/></svg>"""
_IC_MSG = """<svg viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><defs>
<linearGradient id="icm" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5ce27a"/><stop offset="1" stop-color="#12a94b"/></linearGradient></defs>
<rect width="56" height="56" rx="13" fill="url(#icm)"/>
<path d="M28 13.5c8.8 0 16 5.7 16 12.7S36.8 38.9 28 38.9c-1.9 0-3.7-.2-5.4-.7L15 41.8l2.7-6.3c-3.5-2.3-5.7-5.6-5.7-9.3 0-7 7.2-12.7 16-12.7Z" fill="#ffffff"/></svg>"""
_IC_STORE = """<svg viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><defs>
<linearGradient id="ica" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#31b3ff"/><stop offset="1" stop-color="#0a6ff0"/></linearGradient></defs>
<rect width="56" height="56" rx="13" fill="url(#ica)"/>
<path d="M28 16.5 20 39.5 M28 16.5 36 39.5 M22.8 32.5h10.4" stroke="#ffffff" stroke-width="3.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

# ---- config -----------------------------------------------------------------
DEFAULT_PORT = 8777
if os.name == "nt":
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ai-session-search")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/ai-session-search")
ROOTS_FILE = os.path.join(CONFIG_DIR, "roots.txt")
STARS_FILE = os.path.join(CONFIG_DIR, "stars.json")   # starred session-ids, persisted per machine
_ROOTLOCK = threading.Lock()
_STARLOCK = threading.Lock()
_STARS = set()

def load_stars():
    try:
        with open(STARS_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        return set(d if isinstance(d, list) else d.get("stars", []))
    except (OSError, ValueError):
        return set()

def save_stars(stars):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(STARS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"stars": sorted(stars)}, fh, ensure_ascii=False, indent=0)
    except OSError:
        pass

def set_stars(sids, on):
    """Star/unstar the given sids; persist; return the full starred set."""
    global _STARS
    with _STARLOCK:
        s = set(_STARS)
        (s.update if on else s.difference_update)(x for x in sids if x)
        _STARS = s
        save_stars(s)
        return sorted(s)

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
    global ROOT, ROOTS, DEFAULT_ROOTS, SAVED_ROOTS, _STARS
    _STARS = load_stars()
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
DEFAULT_LIM = 10000
LIM_OPTIONS = [1000, 2000, 5000, 10000, 20000, 50000]

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
# An agent-memory write: a Markdown file under a `memory/` dir (e.g. ~/.claude/projects/<slug>/memory/*.md).
MEMORY_RE = re.compile(r"/memory/[^/]+\.md$", re.I)
_MEM_IN = re.compile(r"/memory/[^\"'\\/\s]+\.md", re.I)   # a memory path anywhere in a tool_use blob
def is_memory_path(fp):
    return bool(fp) and MEMORY_RE.search(str(fp).replace("\\", "/")) is not None
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
                if _MEM_IN.search(txt):
                    tags.add("memory")            # writing an agent-memory note (a special kind of edit)
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
    files, commits, urls, mem_files = set(), [], set(), set()
    cmds = tests = errors = edits = webs = memory = 0
    for t in turns:
        if "error" in t["tags"]:
            errors += 1
        for kind, txt in t["segs"]:
            if kind == "tool_use":
                name, inp = _toolinput(txt)
                if name in EDIT_TOOLS:
                    edits += 1                    # memory writes are edits too — just a special kind
                    fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
                    if fp:
                        files.add(fp)
                        if is_memory_path(fp):
                            memory += 1
                            mem_files.add(fp)
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
            "errors": errors, "edits": edits, "urls": sorted(urls), "prs": prs, "webs": webs,
            "memory": memory, "mem_files": sorted(mem_files)}

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

# ---- data API (pure data; powers both the JSON HTTP endpoints and the MCP server) ----
def search_api(root, q, scope="all", proj="", limit=30):
    """Search one root → list of result dicts (no HTML). Mirrors the web search."""
    root = root if root in ROOTS else ROOT
    if scope not in SCOPES:
        scope = "all"
    sq = parse_search_query((q or "")[:200])
    terms, phrases, fields, neg = sq["terms"], sq["phrases"], sq["fields"], sq["neg"]
    if fields.get("role"):
        scope = {"me": "human", "i": "human", "you": "human", "human": "human",
                 "claude": "claude", "assistant": "claude"}.get(fields["role"][0], scope)
    id_vals = fields.get("id", [])
    field_terms = {k: v for k, v in fields.items() if k in FIELD_KIND}
    if not (terms or phrases or fields or neg):
        return []
    metas = {it["path"]: it for it in get_index(root)}
    fvals = [v for vals in field_terms.values() for v in vals]
    snip_terms = (terms + phrases) or fvals
    need = terms + phrases
    out = []
    for path in session_files(root):
        it = metas.get(path, {})
        if proj and it.get("proj") != proj:
            continue
        sid = it.get("sid") or os.path.basename(path)[:-6]
        forked = it.get("forked", "")
        meta_terms = terms + id_vals
        meta_blob = " ".join(filter(None, [sid, forked, it.get("cwd", ""), it.get("start_cwd", ""),
                                           path, it.get("title", "")])).lower()
        meta_hit = bool(meta_terms) and all(t in meta_blob for t in meta_terms)
        is_ref = meta_hit and any(_looks_ref(t) and (t in sid or (forked and t in forked)) for t in meta_terms)
        rows, blob, tokens = _rows_blob(path)
        if need and not is_ref and not field_terms and not meta_hit and any(
                (t not in blob) and (t not in meta_blob) for t in need):
            continue
        active = [r for r in rows if _scope_ok(r, scope)]
        if neg and any(nt in blob for nt in neg):
            continue
        fields_ok = (not field_terms) or _fields_ok(active, field_terms)
        hit = match_session(active, terms, phrases, blob, tokens) if (fields_ok and need) else None
        field_only = fields_ok and bool(field_terms) and not need
        if not hit and not field_only and not meta_hit:
            continue
        by_gi = {}
        for r in active:
            by_gi.setdefault(r["gi"], []).append(r)
        hit_gis = hit["gis"][:5] if hit else (
            [r["gi"] for r in active if any(v in r["low"] for v in fvals)][:5] if field_only else [])
        snips = []
        for gi in hit_gis:
            rs = by_gi.get(gi, [])
            row = next((r for r in rs if any(t in r["low"] for t in snip_terms)), rs[0] if rs else None)
            if row:
                snips.append({"turn": gi, "role": row["role"], "text": _snippet(row["text"], snip_terms).strip()})
        title_low = (it.get("title", "") or "").lower()
        score = 450 * sum(1 for t in need if t in title_low) + (3000 if is_ref else 0)
        if hit:
            score += {"row": 1000, "cluster": 350, "session": 100}.get(hit["kind"], 0)
        elif field_only:
            score += 500
        out.append({"sid": sid, "provider": it.get("provider", "claude"), "title": it.get("title", ""),
                    "workspace": short_path(it.get("cwd", "")) or it.get("proj", ""), "path": path,
                    "match": (hit["kind"] if hit else ("reference" if meta_hit else "field")),
                    "snippets": snips, "score": round(score, 1), "mtime": it.get("mtime", 0)})
    out.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)
    for r in out:
        r.pop("mtime", None)
    return out[:max(1, min(int(limit or 30), 100))]

def search_all(q, scope="all", limit=30):
    """Search every configured root (all providers) and merge, best-first."""
    merged = []
    for r in ROOTS:
        merged += search_api(r, q, scope, "", limit)
    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged[:max(1, min(int(limit or 30), 100))]

def sessions_api(root=None, limit=100):
    """Recent sessions in a root (newest first)."""
    root = root if root in ROOTS else ROOT
    out = []
    for it in get_index(root)[:max(1, min(int(limit or 100), 500))]:
        out.append({"sid": it["sid"], "provider": it.get("provider", "claude"), "title": it["title"],
                    "workspace": short_path(it.get("cwd", "")) or it["proj"], "path": it["path"],
                    "counts": it["n"], "date": fmt_ts(it.get("last_ts", "")) or fmt_mtime(it["mtime"])})
    return out

def find_by_sid(sid):
    """Locate a session file by its id across all roots (any provider)."""
    for r in ROOTS:
        for it in get_index(r):
            if it["sid"] == sid or it["sid"].startswith(sid):
                return it["path"]
    return None

def session_api(path=None, sid=None, limit=400):
    """Full session content (meta + turns as plain text) for an agent to read."""
    if not path and sid:
        path = find_by_sid(sid)
    if not path:
        return None
    rt = root_for_path(path)
    if not os.path.exists(path) or rt is None:
        return None
    data = load_session(path)
    m = data["meta"]
    turns = []
    for gi, t in enumerate(data["turns"][:max(1, min(int(limit or 400), 2000))]):
        parts = []
        for k, v in t["segs"]:
            if k == "channel":
                pc = parse_channel(v)
                parts.append(pc[1] if pc else v)
            elif k == "tool_use":
                parts.append(_tool_use_search_text(v))
            elif k in ("text", "thinking", "tool_result", "injected"):
                parts.append(v)
        text = " ".join(parts).strip()
        if text:
            turns.append({"turn": gi, "role": t["role"], "text": text[:4000]})
    prov = provider_of(path)
    real_sid = ({"codex": _codex_sid, "gemini": _gemini_sid}.get(prov, lambda p: os.path.basename(p)[:-6]))(path)
    return {"sid": real_sid, "provider": prov, "title": m["title"], "workspace": m.get("cwd", ""),
            "counts": m["n"], "tokens": m.get("tok"), "models": m.get("models"),
            "path": path, "turns": turns}

def roots_api():
    return [{"path": r, "label": short_path(r), "provider":
             ("codex" if is_codex_root(r) else "gemini" if is_gemini_root(r) else "claude")} for r in ROOTS]

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
    total = (n.get("you", 0) + n.get("assistant", 0) + n.get("tool-result", 0)
             + n.get("system", 0) + n.get("subagent", 0))
    # one combined tooltip for the whole line (not a separate popup per number)
    legend = tr("Total msgs = all messages · 🧑 you (typed) · ✦ assistant replies · "
                "⚙ tool results (Bash/Edit/Read…) · ⓘ system / injected (not a human)")
    parts = [f'<b>{total}</b> {tr("msgs")}', f'🧑 {n["you"]}', f'✦ {n["assistant"]}', f'⚙ {n["tool-result"]}']
    if system:
        parts.append(f'ⓘ {n["system"]}')
    return f'<span class=cnt-line title="{esc(legend)}">' + " · ".join(parts) + '</span>'

def star_btn(sid):
    """A star toggle, pre-painted from the server-side starred set (persisted per machine)."""
    on = sid in _STARS
    return (f'<button class="starbtn{" on" if on else ""}" data-sid="{esc(sid)}"'
            f' title="{esc(tr("star this session (kept on this machine — export/import to move)"))}">{"★" if on else "☆"}</button>')

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

def _tk_file(fp):
    """Tool-block file header — flags agent-memory writes (🧠) distinctly from normal files (📄)."""
    if is_memory_path(fp):
        return f'<div class="tk-file tk-mem">🧠 {tr("Memory note")} · {esc(fp)}</div>'
    return f'<div class="tk-file">📄 {esc(fp)}</div>'

def _patch_html(patch, filepath="", cap=800):
    """Render Claude's structuredPatch (a ready-made unified diff) as GitHub-style diff."""
    rows = [_tk_file(filepath)] if filepath else []
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
    rows = [_tk_file(filepath)] if filepath else []
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
                rows.append(_tk_file(fp))
            rows.append(_tk_pre(inp.get("content", ""), "tk-out tk-add"))
        elif isinstance(inp.get("edits"), list):              # MultiEdit → each hunk
            if fp:
                rows.append(_tk_file(fp))
            for e in inp["edits"]:
                if isinstance(e, dict) and isinstance(e.get("old_string"), str) and isinstance(e.get("new_string"), str):
                    rows.append(_difflib_html(e["old_string"], e["new_string"]))
        elif fp:
            rows.append(_tk_file(fp))
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
    has_prose = any(k in ("text", "channel") for k, _ in segs)
    if role != "you" and not has_prose:
        data += ' data-tool="1"'    # non-prose (tool call/result/system) — hidable in "conversation only"
    cats = " ".join((["you"] if role == "you" else [])
                    + (["agent"] if role == "assistant" and has_prose else [])   # the AI's actual replies
                    + sorted(tags))
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
<meta name="theme-color" content="#8a9dff">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="AI Session Search">
<title>%%TITLE%%</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{font:14.5px/1.65 -apple-system,system-ui,'Apple SD Gothic Neo',sans-serif;margin:0;background:#f5f6f8;color:#1a1a1a}
@media(prefers-color-scheme:dark){body{background:#13151a;color:#e7e9ec}}
header{position:sticky;top:0;z-index:9;background:radial-gradient(700px circle at 0% 21%,rgba(138,157,255,1),rgba(138,157,255,0)),radial-gradient(700px circle at 84% 86%,rgba(105,245,247,.88),rgba(105,245,247,0)),linear-gradient(18deg,#0084ff 0%,#1061b7 39%,#b0ff29 100%);color:#fff;padding:11px 18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
/* Installed-app window chrome (no effect in a normal browser tab) */
.titlebar{display:none}
@media(display-mode:window-controls-overlay){
  .titlebar{display:flex;align-items:center;justify-content:center;position:fixed;left:0;top:0;width:100%;height:env(titlebar-area-height,33px);z-index:60;-webkit-app-region:drag;color:#fff;font-size:12px;font-weight:600;letter-spacing:.02em;text-shadow:0 1px 5px rgba(8,25,80,.45);background:radial-gradient(700px circle at 0% 21%,rgba(138,157,255,1),rgba(138,157,255,0)),radial-gradient(700px circle at 84% 86%,rgba(105,245,247,.88),rgba(105,245,247,0)),linear-gradient(18deg,#0084ff 0%,#1061b7 39%,#b0ff29 100%)}
  body{padding-top:env(titlebar-area-height,33px)}
  header{top:env(titlebar-area-height,33px)}
}
header a.home{color:#fff;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap}
header form{margin:0;flex:1;display:flex;gap:7px;min-width:240px}
header input[type=search]{flex:1;padding:7px 12px;border:0;border-radius:8px;font-size:14px}
header select,header button{padding:7px 11px;border:0;border-radius:8px;font-size:13px;cursor:pointer}
header button{background:#fff;color:#0d4ea6;font-weight:600}
header .advbtn{background:rgba(255,255,255,.18);color:#fff;font-weight:500;border:1px solid rgba(255,255,255,.34);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}
header a.home{text-shadow:0 1px 6px rgba(8,25,80,.4)}
.langsw{color:#fff;font-size:12px;white-space:nowrap;opacity:.95;text-shadow:0 1px 5px rgba(8,25,80,.4)}
.langsw a{color:#fff;text-decoration:none;padding:0 2px;opacity:.85}
.langsw a:hover{text-decoration:underline}
.langsw b{padding:0 2px}
.modal-ov{display:none;position:fixed;inset:0;z-index:50;overflow:hidden;color:#fff;align-items:center;justify-content:center;padding:30px 20px;background:
radial-gradient(1600px 1100px at 6% -18%,rgba(255,96,210,.55),rgba(255,96,210,0) 64%),
radial-gradient(1700px 1200px at 110% 115%,rgba(56,224,255,.55),rgba(56,224,255,0) 64%),
radial-gradient(1400px 950px at 102% -12%,rgba(255,150,80,.48),rgba(255,150,80,0) 64%),
radial-gradient(1500px 1050px at -12% 112%,rgba(150,110,255,.6),rgba(150,110,255,0) 65%),
radial-gradient(1100px 750px at 46% -22%,rgba(124,58,237,.4),rgba(124,58,237,0) 62%),
radial-gradient(1100px 700px at 58% 122%,rgba(110,255,200,.25),rgba(110,255,200,0) 62%),
linear-gradient(158deg,#4667ec 0%,#2b4fd8 46%,#0d8ec6 100%)}
.modal-ov.open{display:flex}
@media(prefers-color-scheme:dark){.modal-ov{background:
radial-gradient(1600px 1100px at 6% -18%,rgba(255,96,210,.4),rgba(255,96,210,0) 64%),
radial-gradient(1700px 1200px at 110% 115%,rgba(56,224,255,.4),rgba(56,224,255,0) 64%),
radial-gradient(1400px 950px at 102% -12%,rgba(255,150,80,.34),rgba(255,150,80,0) 64%),
radial-gradient(1500px 1050px at -12% 112%,rgba(150,110,255,.45),rgba(150,110,255,0) 65%),
radial-gradient(1100px 750px at 46% -22%,rgba(124,58,237,.3),rgba(124,58,237,0) 62%),
radial-gradient(1100px 700px at 58% 122%,rgba(110,255,200,.18),rgba(110,255,200,0) 62%),
linear-gradient(158deg,#3450c4 0%,#20369b 46%,#0a6d9d 100%)}}
.modal{position:relative;z-index:1;background:transparent;max-width:1020px;width:100%;padding:12px 8px;max-height:100%;overflow:auto;text-align:center}
.modal-h{margin:0 0 12px;font-size:34px;font-weight:700;letter-spacing:-.02em;text-shadow:0 2px 14px rgba(10,25,80,.25)}
.modal-sub{margin:0 0 42px;color:rgba(255,255,255,.8);font-size:16px}
.modal-ills{display:flex;gap:48px;justify-content:center;align-items:stretch;flex-wrap:wrap}
.modal-ill{flex:1 1 380px;max-width:460px;display:flex;flex-direction:column}
.ill-stage{flex:1;min-height:236px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
.modal-cap{font-size:14px;color:rgba(255,255,255,.92);margin-top:18px;text-align:center}
.modal-actions{display:flex;justify-content:center;margin-top:46px}
.modal-primary{padding:16px 58px;border:0;border-radius:999px;background:#fff;color:#1c49cf;font-size:16px;font-weight:700;cursor:pointer;box-shadow:0 12px 34px rgba(6,18,64,.35);transition:transform .15s,box-shadow .15s}
.modal-primary:hover{transform:translateY(-1px);box-shadow:0 16px 40px rgba(6,18,64,.42)}
.modal-note{font-size:12px;color:rgba(255,255,255,.75);margin:18px 0 0;line-height:1.6}
/* -- install screen: liquid-glass ⌘-Tab strap -- */
.ct-strap{display:inline-flex;flex-direction:column;align-items:center;gap:12px;padding:20px 24px 14px;border-radius:30px;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);box-shadow:0 18px 50px rgba(8,20,70,.35),inset 0 1px 0 rgba(255,255,255,.55);-webkit-backdrop-filter:blur(22px) saturate(1.7);backdrop-filter:blur(22px) saturate(1.7)}
.ct-row{display:flex;align-items:center;gap:16px}
.ct-ic{width:52px;height:52px;flex:none;filter:drop-shadow(0 5px 10px rgba(8,20,70,.28))}
.ct-ic svg,.ct-ic img{display:block;width:100%;height:100%}
.ct-sel{display:flex;padding:8px;border-radius:19px;background:rgba(255,255,255,.34);border:1px solid rgba(255,255,255,.65);box-shadow:inset 0 1px 0 rgba(255,255,255,.6)}
.ct-name{font-size:12px;font-weight:600;color:#fff;letter-spacing:.01em;text-shadow:0 1px 6px rgba(10,30,90,.5)}
.ct-keys{display:flex;gap:10px;justify-content:center}
.ct-keys kbd{min-width:34px;padding:6px 13px;border-radius:9px;background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.42);box-shadow:inset 0 1px 0 rgba(255,255,255,.5);color:#fff;font-size:12.5px;font-family:inherit;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
/* -- install screen: floating mini browser window -- */
.ext-win{width:100%;max-width:410px;border:3px solid transparent;border-radius:16px;background:linear-gradient(#fff,#fff) padding-box,linear-gradient(18deg,#0084ff 0%,#1061b7 39%,#b0ff29 100%) border-box;box-shadow:0 26px 60px rgba(6,16,60,.42);overflow:hidden;text-align:left;color:#3a3f47}
.ext-top{display:flex;align-items:center;gap:7px;padding:11px 13px;background:radial-gradient(600px circle at 0% 21%,rgba(138,157,255,.9),rgba(138,157,255,0)),radial-gradient(600px circle at 84% 86%,rgba(105,245,247,.8),rgba(105,245,247,0)),linear-gradient(18deg,#0084ff 0%,#1061b7 39%,#b0ff29 100%)}
.ext-dot{width:11px;height:11px;border-radius:50%;flex:none;box-shadow:inset 0 0 0 1px rgba(0,0,0,.08)}
.ext-title{flex:1;text-align:center;font-size:11.5px;font-weight:600;color:#fff;white-space:nowrap;overflow:hidden;margin:0 6px;text-shadow:0 1px 5px rgba(8,25,80,.45)}
.ext-puz{position:relative;width:26px;height:26px;border-radius:8px;background:rgba(255,255,255,.9);border:1px solid rgba(255,255,255,.6);display:flex;align-items:center;justify-content:center;font-size:13px;flex:none}
.ext-puz i{position:absolute;top:-3px;right:-3px;width:9px;height:9px;border-radius:50%;background:#22c55e;border:1.5px solid #fff}
.ext-body{position:relative;padding:44px 16px 18px}
.ext-find{position:absolute;top:9px;right:12px;display:flex;align-items:center;gap:9px;background:#fff;border:1px solid #e0e4eb;border-radius:10px;padding:6px 11px;font-size:11px;color:#4a505a;box-shadow:0 8px 22px rgba(15,25,60,.14)}
.ext-find b{color:#1f6feb;font-weight:600}
.ext-find span{color:#9aa1ab}
.ext-row{display:flex;align-items:center;gap:9px;margin:12px 0}
.ext-av{width:20px;height:20px;border-radius:6px;flex:none}
.ext-bar{height:9px;border-radius:5px;background:#e9edf2;flex:1}
.ext-bar.hit{flex:none;width:54px;background:#ffe08a}
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
a.chiplink{text-decoration:none;cursor:pointer}
a.chiplink:hover{background:#dbe5ff;color:#1f6feb}
@media(prefers-color-scheme:dark){a.chiplink:hover{background:#1a3763;color:#cfe0ff}}
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
.favbar{font-size:12px;color:#8a8f98;margin:4px 0 10px;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.favbar a,.favbar .favimp{color:#1f6feb;text-decoration:none;cursor:pointer}
.favbar a:hover,.favbar .favimp:hover{text-decoration:underline}
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
table.stab thead th.sortable{cursor:pointer}
table.stab thead th.sortable:hover{color:#1f6feb;text-decoration:underline}
table.stab thead th .sarr{color:#1f6feb}
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
.crumbs{position:fixed;left:0;right:0;bottom:0;z-index:45;background:rgba(255,255,255,.94);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border-top:1px solid #e4e7eb;padding:5px 14px;font-size:11px;color:#8a8f98;display:flex;flex-wrap:wrap;align-items:center;gap:5px;line-height:1.5}
.crumbs a.crumb{color:#1f6feb;text-decoration:none}
.crumbs a.crumb:hover{text-decoration:underline}
.crumbsep{color:#c0c5cc}
.crumbcur{color:#333;font-weight:600}
.crumbs code.sid{font-size:10px}
body:has(.crumbs){padding-bottom:34px}
@media(prefers-color-scheme:dark){.crumbs{background:rgba(18,21,26,.94);border-color:#2a2e35}.crumbcur{color:#e7e9ec}.crumbsep{color:#4a4f57}}
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
.tk-file.tk-mem{color:#6b3fb5;font-weight:600}
.dfile.tk-mem{display:inline-block;background:#f1e9fc;color:#6b3fb5;border-radius:4px;padding:0 6px;margin:2px 3px 0 0}
@media(prefers-color-scheme:dark){.tk-file.tk-mem{color:#c2a8f0}.dfile.tk-mem{background:#251a3a;color:#c2a8f0}}
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
.card.rowfocus{outline:3px solid #1f6feb;outline-offset:1px}
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
.cnt-line{cursor:help;border-bottom:1px dotted rgba(150,153,163,.5)}
.copybtn{cursor:pointer;opacity:.55;font-size:.92em;padding:1px 5px;border-radius:5px;user-select:none;white-space:nowrap}
.copybtn:hover{opacity:1;background:rgba(31,111,235,.16)}
.copyval{cursor:pointer;border-radius:4px;padding:0 3px;transition:background .12s}
.copyval:hover{background:rgba(31,111,235,.14)}
.copyval.copied{background:rgba(38,190,110,.3)}
.copyval.copied::after{content:" ✓";color:#189a55}
.srow a.slink{display:inline-flex;align-items:center;gap:5px;color:#1f6feb;text-decoration:none;background:rgba(31,111,235,.1);border:1px solid rgba(31,111,235,.28);border-radius:7px;padding:2px 9px;font-weight:500}
.srow a.slink:hover{background:rgba(31,111,235,.2)}
.srow a.slink code{background:transparent;color:inherit;padding:0}
.livepill{position:fixed;left:50%;transform:translateX(-50%);bottom:52px;z-index:80;background:#1f6feb;color:#fff;border:0;border-radius:999px;padding:11px 22px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 10px 28px rgba(15,25,60,.4)}
.livepill:hover{background:#1a63d6}
.msg.khide{display:none}
#convflag{position:fixed;left:16px;bottom:46px;z-index:70;background:#6b3fb5;color:#fff;border-radius:999px;padding:7px 14px;font-size:12.5px;box-shadow:0 6px 18px rgba(15,25,60,.32)}
.kbov{display:none;position:fixed;inset:0;z-index:90;background:rgba(10,15,25,.55);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);align-items:center;justify-content:center;padding:20px}
.kbov.open{display:flex}
.kbcard{background:#fff;color:#1a1a1a;border-radius:14px;padding:22px 26px;max-width:460px;width:100%;box-shadow:0 22px 60px rgba(0,0,0,.42)}
@media(prefers-color-scheme:dark){.kbcard{background:#1b1e24;color:#e7e9ec}}
.kbtab{width:100%;border-collapse:collapse;font-size:13.5px}
.kbtab td{padding:5px 6px;border-bottom:1px solid #eef1f4}
.kbtab td:first-child{width:104px;white-space:nowrap}
@media(prefers-color-scheme:dark){.kbtab td{border-color:#2a2e35}}
.kbtab kbd{background:#eef1f4;border:1px solid #d4d9e0;border-radius:5px;padding:1px 7px;font-family:ui-monospace,Menlo,monospace;font-size:12px}
@media(prefers-color-scheme:dark){.kbtab kbd{background:#2a2e35;border-color:#3a3f47}}
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
<div class=titlebar>%%HOMELABEL%%</div>
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
  <button type=button id=copyurl class=advbtn title="%%COPYURLTITLE%%">🔗</button>
  <button type=button id=installbtn class=advbtn style="display:none" title="%%INSTALLTITLE%%">%%INSTALLLBL%%</button>
  %%LANGSW%%
</header>
%%ROOTBAR%%
<div class=wrap>%%BODY%%</div>
%%INSTALLMODAL%%
%%KBHELP%%
<div id=convflag style="display:none">🧹 %%CONVONLY%%</div>
<div id=minimap></div>
<script>
(function(){
  var cur=-1;
  function ys(){return Array.prototype.slice.call(document.querySelectorAll('.msg.you'));}
  function focusYou(i){var a=ys();if(!a.length)return;cur=((i%a.length)+a.length)%a.length;
    a.forEach(function(e){e.classList.remove('kfocus');});var el=a[cur];
    el.classList.add('kfocus');el.scrollIntoView({block:'center'});}   // instant — smooth is slow on huge pages
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
  var nk=document.getElementById('navkeys');
  function nav(attr){var v=nk&&nk.getAttribute(attr);if(v)location.href=v;}
  var toolsHidden=false;
  function toggleTools(){toolsHidden=!toolsHidden;
    document.querySelectorAll('.msg[data-tool]').forEach(function(m){m.classList.toggle('khide',toolsHidden);});
    var f=document.getElementById('convflag');if(f)f.style.display=toolsHidden?'inline':'none';}
  function toggleHelp(){var h=document.getElementById('kbhelp');if(h)h.classList.toggle('open');}
  // thread-list (index/search) row navigation — Gmail-style j/k over session cards
  var inSession=!!nk, rcur=-1, _rowcache=null, rprev=null;
  function rrows(){if(!_rowcache)_rowcache=Array.prototype.slice.call(document.querySelectorAll('.card[data-sid]'));return _rowcache;}
  function focusRow(i){var a=rrows();if(!a.length)return;rcur=((i%a.length)+a.length)%a.length;
    if(rprev)rprev.classList.remove('rowfocus');var el=a[rcur];rprev=el;   // touch only the previous row, not all
    el.classList.add('rowfocus');el.scrollIntoView({block:'nearest'});}   // minimal scroll — not dizzying
  function openRow(){var el=rrows()[rcur];var lk=el&&el.querySelector('a.t');if(lk)location.href=lk.href;}
  function starNow(){var sb=inSession?document.querySelector('.starbtn'):(rcur>=0&&rrows()[rcur]&&rrows()[rcur].querySelector('.starbtn'));if(sb)sb.click();}
  document.addEventListener('keydown',function(e){
    var tag=(e.target.tagName||'').toLowerCase();
    var typing=(tag==='input'||tag==='select'||tag==='textarea');
    // e.code (physical key) so shortcuts work under non-Latin layouts (Korean/…)
    var C=e.code;
    if(e.key==='Escape'){var hp=document.getElementById('kbhelp');
      if(hp&&hp.classList.contains('open')){hp.classList.remove('open');return;}
      if(typing){e.target.blur();return;}
      var bf=document.querySelector('a.backfull');if(bf){location.href=bf.getAttribute('href');return;}  // exit in-session search
      var af=document.querySelector('.chip-f.active');                      // a filter chip is active → back to All
      if(af){var all=document.querySelector('.chip-f[data-cat="*"]');if(all)all.click();return;}
      return;}
    if(typing||e.metaKey||e.ctrlKey||e.altKey)return;
    if(C==='Slash'&&e.shiftKey){e.preventDefault();toggleHelp();return;}          // ? = help
    if(C==='Slash'){e.preventDefault();var s=document.getElementById('qbox');if(s){s.focus();s.select();}return;}
    if(C==='KeyF'){var sb=document.querySelector('input[name=sq]');if(sb){e.preventDefault();sb.focus();sb.select();}return;}  // find in this session
    if(C==='KeyN'){if(ys().length){e.preventDefault();focusYou(cur+1);}return;}   // next my message
    if(C==='KeyP'){if(ys().length){e.preventDefault();focusYou(cur-1);}return;}   // prev my message
    if(e.key==='Enter'){
      if(inSession&&cur>=0){var a=ys();var l=a[cur]&&a[cur].getAttribute('data-thread');if(l)location.href=l;return;}
      if(!inSession){e.preventDefault();openRow();}return;}                       // open the focused list row
    if(C==='KeyJ'){e.preventDefault();if(inSession)nav('data-prevsess');else focusRow(rcur+1);return;} // down / older
    if(C==='KeyK'){e.preventDefault();if(inSession)nav('data-nextsess');else focusRow(rcur-1);return;} // up / newer
    if(C==='BracketRight'){e.preventDefault();nav('data-nextpage');return;}       // next page
    if(C==='BracketLeft'){e.preventDefault();nav('data-prevpage');return;}        // prev page
    if(C==='KeyM'){e.preventDefault();nav((nk&&nk.getAttribute('data-filt')==='human')?'data-showall':'data-onlyme');return;}
    if(C==='KeyT'){e.preventDefault();toggleTools();return;}                      // conversation only
    if(C==='KeyC'){e.preventDefault();                                            // code-only ↔ conversation
      var cd=nk&&nk.getAttribute('data-code');if(cd){location.href=cd;return;}
      var bf2=document.querySelector('a.backfull');if(bf2)location.href=bf2.getAttribute('href');return;}
    if(C==='KeyS'){e.preventDefault();starNow();return;}                         // toggle star
    if(C==='KeyU'){e.preventDefault();nav('data-list');return;}                   // back to the session (thread) list
    if(C==='KeyH'&&e.shiftKey){e.preventDefault();location.href='/';return;}      // home (all workspaces)
    if(C==='KeyG'){e.preventDefault();window.scrollTo(0,e.shiftKey?document.body.scrollHeight:0);return;}
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
  // "running as the installed app" — cover every installed display mode, not just standalone
  // (our app installs in window-controls-overlay mode, where display-mode:standalone is false).
  var mm=function(q){return window.matchMedia&&window.matchMedia(q).matches;};
  var standalone=mm('(display-mode: standalone)')||mm('(display-mode: window-controls-overlay)')
                 ||mm('(display-mode: minimal-ui)')||mm('(display-mode: fullscreen)')||navigator.standalone===true;
  function mark(){try{localStorage.setItem('aiss:installed','1');}catch(_){}}
  function installed(){try{return standalone||localStorage.getItem('aiss:installed')==='1';}catch(_){return standalone;}}
  if(standalone)mark();  // remember (per-origin) that this machine has the app installed
  function openInstall(){if(mov)mov.classList.add('open');}
  function closeInstall(){if(mov)mov.classList.remove('open');}
  if(ibtn)ibtn.addEventListener('click',openInstall);
  // No visible dismiss — only "Confirm" (or ESC as an escape hatch). Feels like a finish-setup step.
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&mov&&mov.classList.contains('open'))closeInstall();});
  var inow=document.getElementById('installnow');
  if(inow)inow.addEventListener('click',function(){
    if(deferredPrompt){
      var dp=deferredPrompt;deferredPrompt=null;dp.prompt();
      // keep our full-screen behind the native prompt; close only AFTER the user chooses,
      // so the real app never shows through the browser's install dialog.
      if(dp.userChoice&&dp.userChoice.then){
        dp.userChoice.then(function(res){if(res&&res.outcome==='accepted'){mark();if(ibtn)ibtn.style.display='none';}closeInstall();});
      }
    }
    else{var h=document.getElementById('installhow');if(h)h.style.display='';}
  });
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferredPrompt=e;
    if(installed()){return;}                         // already installed → no button, no auto-modal
    if(ibtn)ibtn.style.display='';                    // offer manual install (button) on any page…
    // …but only auto-pop the big modal on the home page — never on a deep permalink/session link.
    try{if(location.pathname==='/'&&!localStorage.getItem('aiss:installtip')){localStorage.setItem('aiss:installtip','1');openInstall();}}catch(_){}
  });
  window.addEventListener('appinstalled',function(){mark();if(ibtn)ibtn.style.display='none';closeInstall();});
  if(installed()&&ibtn)ibtn.style.display='none';
  // Project-stats table: click a column header to sort (client-side; Total row stays last)
  document.querySelectorAll('table.stab thead th.sortable').forEach(function(th){
    th.style.cursor='pointer';
    th.addEventListener('click',function(){
      var table=th.closest('table'), tb=table.tBodies[0];
      var idx=[].indexOf.call(th.parentNode.children, th);
      var tot=tb.querySelector('tr.tot');
      var rows=[].slice.call(tb.querySelectorAll('tr:not(.tot)'));
      var asc=th.getAttribute('data-asc')!=='1';
      table.querySelectorAll('th').forEach(function(h){h.removeAttribute('data-asc');var a=h.querySelector('.sarr');if(a)a.remove();});
      th.setAttribute('data-asc',asc?'1':'0');
      rows.sort(function(a,b){
        var ca=a.children[idx], cb=b.children[idx];
        var va=ca.getAttribute('data-v'), vb=cb.getAttribute('data-v'), r;
        if(va!==null&&vb!==null){r=(parseFloat(va)||0)-(parseFloat(vb)||0);}
        else{r=(ca.textContent||'').trim().localeCompare((cb.textContent||'').trim());}
        return asc?r:-r;
      });
      rows.forEach(function(r){tb.insertBefore(r,tot);});
      var s=document.createElement('span');s.className='sarr';s.textContent=asc?' ▲':' ▼';th.appendChild(s);
    });
  });
  // copy the current page's URL (the installed app has no address bar to copy from)
  var cpu=document.getElementById('copyurl');
  if(cpu)cpu.addEventListener('click',function(){
    var u=location.href;
    if(navigator.clipboard){navigator.clipboard.writeText(u);}
    else{var t=document.createElement('input');t.value=u;document.body.appendChild(t);t.select();try{document.execCommand('copy');}catch(_){}document.body.removeChild(t);}
    var o=cpu.textContent;cpu.textContent='✓';cpu.disabled=true;setTimeout(function(){cpu.textContent=o;cpu.disabled=false;},1000);
  });
  function copyText(s){
    if(navigator.clipboard){navigator.clipboard.writeText(s);return;}
    var t=document.createElement('textarea');t.value=s;document.body.appendChild(t);t.select();try{document.execCommand('copy');}catch(_){}document.body.removeChild(t);
  }
  // progressive load: the server paints the first chunk instantly; stream the rest in the background
  var lz=document.getElementById('lazyload');
  if(lz){
    var lp=lz.getAttribute('data-p'),lsince=+lz.getAttribute('data-since'),lend=+lz.getAttribute('data-end'),lq=lz.getAttribute('data-q')||'';
    var idle=window.requestIdleCallback||function(f){return setTimeout(f,40);};
    var loadChunk=function(){
      if(!lz||lsince>=lend){if(lz){lz.remove();lz=null;}return;}
      var take=Math.min(400,lend-lsince);
      fetch('/api/session_tail?p='+encodeURIComponent(lp)+'&since='+lsince+'&limit='+take+(lq?'&q='+encodeURIComponent(lq):''))
        .then(function(r){return r.json();}).then(function(d){
          if(d&&d.html&&lz)lz.insertAdjacentHTML('beforebegin',d.html);
          lsince=(d&&d.end)?d.end:(lsince+take);
          if(toolsHidden)document.querySelectorAll('.msg[data-tool]').forEach(function(x){x.classList.add('khide');});
          if(lz&&lsince<lend)idle(loadChunk); else if(lz){lz.remove();lz=null;}
        }).catch(function(){});
    };
    idle(loadChunk);
  }
  // live-update: poll the session file and APPEND new messages in place, like a chat — no reload.
  try{if(sessionStorage.getItem('aiss:tail')){sessionStorage.removeItem('aiss:tail');window.scrollTo(0,document.body.scrollHeight);}}catch(_){}
  var ls=document.getElementById('livesess');
  if(ls){
    var sp=ls.getAttribute('data-p'), base=null, pill=null, busy=false;
    function lastGi(){var m=document.querySelectorAll('.msg');if(!m.length)return -1;
      var n=parseInt((m[m.length-1].id||'').replace('t',''),10);return isNaN(n)?-1:n;}
    function showPill(){if(pill)return;pill=document.createElement('button');pill.className='livepill';
      pill.textContent='🔄 '+(ls.getAttribute('data-new')||'New messages')+' — '+(ls.getAttribute('data-load')||'load');
      pill.addEventListener('click',function(){try{sessionStorage.setItem('aiss:tail','1');}catch(_){}location.reload();});
      document.body.appendChild(pill);}
    function appendNew(){
      if(busy)return; busy=true;
      var q=new URLSearchParams(location.search).get('q')||'';
      var nearBottom=(window.innerHeight+window.scrollY)>=(document.body.scrollHeight-180);
      fetch('/api/session_tail?p='+encodeURIComponent(sp)+'&since='+(lastGi()+1)+(q?'&q='+encodeURIComponent(q):''))
        .then(function(r){return r.json();}).then(function(d){busy=false;
          if(!d||!d.html)return;
          var m=document.querySelectorAll('.msg');
          if(m.length)m[m.length-1].insertAdjacentHTML('afterend',d.html);
          if(toolsHidden)document.querySelectorAll('.msg[data-tool]').forEach(function(x){x.classList.add('khide');});
          if(nearBottom)window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});
        }).catch(function(){busy=false;});
    }
    setInterval(function(){
      if(document.getElementById('lazyload'))return;   // wait until the progressive load finishes
      fetch('/api/session_stat?p='+encodeURIComponent(sp)).then(function(r){return r.json();}).then(function(d){
        if(!d||d.error)return; var cur=d.mtime+'/'+d.size;
        if(base===null){base=cur;return;}
        if(cur!==base){base=cur;
          // append in place on the last page; on a middle (paginated) page just offer a reload pill
          if(nk&&nk.getAttribute('data-nextpage'))showPill(); else appendNew();
        }
      }).catch(function(){});
    },4000);
  }
  // stars are server-side (persisted to CONFIG_DIR/stars.json), pre-painted on render
  function paintStar(b,on){b.textContent=on?'\u2605':'\u2606';b.classList.toggle('on',on);}
  // one-time migration of any old browser-local stars into the server file
  try{var mig=[],i,k;for(i=0;i<localStorage.length;i++){k=localStorage.key(i);if(k&&k.indexOf('aiss:star:')===0&&localStorage.getItem(k)==='1')mig.push(k.slice(10));}
    if(mig.length){fetch('/api/star?sid='+encodeURIComponent(mig.join(','))+'&on=1').then(function(){
      mig.forEach(function(s){try{localStorage.removeItem('aiss:star:'+s);}catch(_){}
        document.querySelectorAll('.starbtn[data-sid="'+s+'"]').forEach(function(x){paintStar(x,true);});});});}
  }catch(_){}
  // import a stars file (merges into the server-side set)
  var si=document.getElementById('starimport');
  if(si)si.addEventListener('change',function(){var f=si.files&&si.files[0];if(!f)return;
    var r=new FileReader();
    r.onload=function(){try{var d=JSON.parse(r.result);var arr=Array.isArray(d)?d:((d&&d.stars)||[]);
      arr=arr.filter(function(x){return typeof x==='string'&&x;});
      if(arr.length){fetch('/api/star?sid='+encodeURIComponent(arr.join(','))+'&on=1').then(function(){location.reload();});}
      else alert('No starred ids found in that file.');
    }catch(_){alert('Not a valid stars JSON file.');}};
    r.readAsText(f);});
  document.addEventListener('click',function(e){
    // click the 📋 icon to copy (for values that also have a click action, e.g. navigate)
    var cv=e.target.closest&&e.target.closest('.copybtn');
    if(cv){e.preventDefault();copyText(cv.getAttribute('data-copy')||'');
      var oc=cv.textContent;cv.textContent='✓';cv.classList.add('copied');
      setTimeout(function(){cv.textContent=oc;cv.classList.remove('copied');},900);return;}
    // click a plain value (no navigation) → copy it directly
    var cvv=e.target.closest&&e.target.closest('.copyval');
    if(cvv){e.preventDefault();copyText((cvv.textContent||'').trim());
      cvv.classList.add('copied');setTimeout(function(){cvv.classList.remove('copied');},900);return;}
    var b=e.target.closest&&e.target.closest('.starbtn');
    if(b){e.preventDefault();var sid=b.getAttribute('data-sid');var on=!b.classList.contains('on');
      document.querySelectorAll('.starbtn[data-sid="'+sid+'"]').forEach(function(x){paintStar(x,on);});
      fetch('/api/star?sid='+encodeURIComponent(sid)+'&on='+(on?1:0)).catch(function(){});return;}
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
    # the ⌘-Tab strap demo (CSS liquid glass) and a floating mini browser window
    ill_cmdtab = (
        '<div class=ill-stage><div class=ct-strap><div class=ct-row>'
        f'<span class=ct-ic>{_IC_FINDER}</span>'
        f'<span class=ct-ic>{_IC_SAFARI}</span>'
        f'<span class=ct-sel><span class=ct-ic>{ICON_SVG}</span></span>'
        f'<span class=ct-ic>{_IC_MSG}</span>'
        f'<span class=ct-ic>{_IC_STORE}</span>'
        '</div><div class=ct-name>AI Session Search</div></div>'
        '<div class=ct-keys><kbd>&#8984;</kbd><kbd>tab &#8677;</kbd></div></div>')
    ill_chrome = (
        '<div class=ill-stage><div class=ext-win>'
        '<div class=ext-top>'
        '<span class=ext-dot style="background:#ff5f57"></span>'
        '<span class=ext-dot style="background:#febc2e"></span>'
        '<span class=ext-dot style="background:#28c840"></span>'
        '<span class=ext-title>AI Session Search</span>'
        '<span class=ext-puz>&#129513;<i></i></span>'
        '</div><div class=ext-body>'
        '<span class=ext-find>&#8984;F <b>docker</b><span>3/14</span></span>'
        '<div class=ext-row><span class=ext-av style="background:#1f6feb"></span><span class=ext-bar style="max-width:58%"></span></div>'
        '<div class=ext-row><span class=ext-av style="background:#8b5cf6"></span><span class=ext-bar style="max-width:34%"></span><span class="ext-bar hit"></span></div>'
        '<div class=ext-row><span class=ext-av style="background:#0ea5e9"></span><span class=ext-bar style="max-width:66%"></span></div>'
        '</div></div></div>')
    install_modal = (
        '<div id=installmodal class=modal-ov><div class=modal role=dialog aria-modal=true>'
        f'<h2 class=modal-h>{esc(tr("Almost done!"))}</h2>'
        f'<p class=modal-sub>{esc(tr("One last step — click Confirm to finish setting up the app."))}</p>'
        '<div class=modal-ills>'
        f'<div class=modal-ill>{ill_cmdtab}<div class=modal-cap>✓ {esc(tr("Shows up in ⌘-Tab and the Dock as its own app."))}</div></div>'
        f'<div class=modal-ill>{ill_chrome}<div class=modal-cap>✓ {esc(tr("It is still Chrome inside — ⌘-F Find and your extensions keep working."))}</div></div>'
        '</div>'
        f'<div class=modal-actions><button id=installnow class=modal-primary>{esc(tr("Confirm"))}</button></div>'
        f'<p class=modal-note id=installhow style="display:none">{tr("If it does not prompt, use the Chrome ⋮ menu → “Cast, save &amp; share” → “Install page as app”.")}</p>'
        '</div></div>')
    kbrows = [
        ("j / k", tr("down / up — session-list rows, or prev / next session")),
        ("Enter", tr("open the focused session (or its answer thread)")),
        ("n / p", tr("next / previous message of yours")),
        ("s", tr("toggle star")),
        ("u", tr("back to the session list")),
        ("m", tr("toggle: only my messages")),
        ("t", tr("toggle: conversation only (hide tool calls/results)")),
        ("c", tr("code-only view ↔ conversation")),
        ("[ / ]", tr("previous / next page")),
        ("g / G", tr("jump to top / bottom")),
        ("/", tr("search all sessions")),
        ("f", tr("find within THIS session")),
        ("Shift + H", tr("home (all workspaces)")),
        ("?", tr("this help")),
        ("Esc", tr("step back: clear filter / exit search / close")),
    ]
    kbhelp = ('<div id=kbhelp class=kbov><div class=kbcard role=dialog aria-modal=true>'
              f'<h3 style="margin:0 0 12px">⌨️ {esc(tr("Keyboard shortcuts"))}</h3><table class=kbtab>'
              + "".join(f'<tr><td><kbd>{esc(k)}</kbd></td><td>{esc(v)}</td></tr>' for k, v in kbrows)
              + '</table></div></div>')
    repl = {
        "%%KBHELP%%": kbhelp,
        "%%CONVONLY%%": esc(tr("conversation only — press t to show tools")),
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
        "%%COPYURLTITLE%%": esc(tr("copy this page's link (handy in the installed app — no address bar)")),
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

    def _send_json(self, obj, status=200):
        b = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
        if u.path in ("/icon-256.png", "/icon-192.png"):
            # raster icons for the PWA/Dock/Cmd-Tab (macOS needs a PNG, not just the SVG)
            b = base64.b64decode(ICON_PNG_256 if u.path == "/icon-256.png" else ICON_PNG_192)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if u.path == "/api/session_stat":
            # cheap change-detector for live updates: mtime+size only, no parse (path must be in a root)
            p = g("p")
            if p and os.path.exists(p) and root_for_path(p) is not None:
                st = os.stat(p)
                return self._send_json({"mtime": st.st_mtime, "size": st.st_size})
            return self._send_json({"error": "not found"}, 404)
        if u.path == "/api/star":
            # star/unstar sessions (persisted to CONFIG_DIR/stars.json). sid may be comma-separated.
            sfs = (self.headers.get("Sec-Fetch-Site") or "").lower()
            if sfs in ("cross-site", "same-site"):
                return self._send_json({"error": "cross-site rejected"}, 403)
            sids = [s for s in (g("sid") or "").split(",") if s.strip()]
            starred = set_stars(sids, g("on") == "1")
            return self._send_json({"starred": starred, "count": len(starred)})
        if u.path == "/api/stars.json":
            b = json.dumps({"stars": sorted(_STARS)}, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="aiss-stars.json"')
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if u.path == "/api/session_tail":
            # render turns [since, since+limit) so the client can append them (progressive / live, no reload)
            p = g("p")
            if not (p and os.path.exists(p) and root_for_path(p) is not None):
                return self._send_json({"error": "not found"}, 404)
            try:
                since = max(0, int(g("since") or 0))
                lim = int(g("limit") or 0)
            except ValueError:
                since, lim = 0, 0
            turns = load_session(p)["turns"]
            qq = g("q", "")
            end = len(turns) if lim <= 0 else min(len(turns), since + lim)

            def _tl(gi, t):     # keep the answer-thread link on lazily-loaded human turns
                if t["role"] != "you":
                    return None
                params = {"p": p, "thread": gi}
                if qq:
                    params["q"] = qq
                return "/session?" + urllib.parse.urlencode(params)
            html = "".join(render_turn(gi, turns[gi], qq, _tl(gi, turns[gi])) for gi in range(since, end))
            return self._send_json({"n": len(turns), "end": end, "html": html})
        if u.path == "/manifest.webmanifest":
            # lets Chrome/Edge "Install as app" → standalone window (own Cmd+Tab/Dock entry)
            man = json.dumps({
                "name": "AI Session Search", "short_name": "AI Search",
                "start_url": "/", "scope": "/", "display": "standalone",
                "display_override": ["window-controls-overlay"],
                "background_color": "#0b1220", "theme_color": "#8a9dff",
                "icons": [
                    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                    {"src": "/icon-256.png", "sizes": "256x256", "type": "image/png", "purpose": "any"},
                    {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
                ],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(man)))
            self.end_headers()
            return self.wfile.write(man)
        # ---- JSON API (local only; same data as the web UI, for agents/scripts/MCP) ----
        if u.path in ("/api/search", "/api/sessions", "/api/session", "/api/roots") or (
                u.path == "/search" and g("format") == "json"):
            try:
                if u.path == "/api/roots":
                    return self._send_json({"roots": roots_api()})
                if u.path == "/api/sessions":
                    r = g("root") or None
                    return self._send_json({"root": r or ROOT, "sessions": sessions_api(r if r in ROOTS else None, gint("limit", 100))})
                if u.path == "/api/session":
                    d = session_api(g("p") or None, g("sid") or None, gint("limit", 400))
                    return self._send_json(d, 200 if d else 404) if d else self._send_json({"error": "not found"}, 404)
                # search: /api/search (all roots) or /search?format=json (active root)
                lim = gint("limit", 30) or 30
                if u.path == "/search":
                    res = search_api(active_root(g("root")), g("q"), g("scope", "all"), g("proj", ""), lim)
                else:
                    r = g("root")
                    res = search_api(r, g("q"), g("scope", "all"), g("proj", ""), lim) if r in ROOTS else search_all(g("q"), g("scope", "all"), lim)
                return self._send_json({"query": g("q"), "count": len(res), "results": res})
            except Exception as e:
                return self._send_json({"error": str(e)}, 500)
        root = active_root(g("root"))
        if u.path == "/":
            return self._send(self.index(g("proj"), g("sort", "date"), g("dir", ""), root))
        if u.path == "/search":
            return self._send(self.search(g("q"), g("scope", "all"), root,
                                          g("days", ""), g("proj", ""), g("from", ""), g("to", "")))
        if u.path == "/session":
            return self._send(self.session(g("p"), g("q"), g("filter", "all"),
                                           gint("off"), g("lim", ""), g("thread", ""), g("view", ""),
                                           g("goto", ""), g("sq", ""), g("sqtools", "")))
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
                          f'<td data-v="{s["sessions"]}">{s["sessions"]}</td>'
                          f'<td data-v="{s["my_sessions"]}">{s["my_sessions"]}</td>'
                          f'<td data-v="{s["my_msgs"]}">{s["my_msgs"]}</td>'
                          f'<td data-v="{s["tok"]["out"]}" title="{esc(_toktip(s["tok"]))}">{fmt_tok(s["tok"]["out"])}</td>'
                          f'<td class=mdlcell>{models_badge(s["models"])}</td>'
                          f'<td data-v="{s["size"]}">{fmt_size(s["size"])}</td>'
                          f'<td data-v="{s["loop"]}">{lc}</td></tr>')
            tot = agg_stats(all_items)
            table = (f'<table class=stab><thead><tr><th class=sortable>{tr("Project (folder)")}</th>'
                     f'<th class=sortable title="{esc(tr("session count"))}">{tr("Sessions")}</th>'
                     f'<th class=sortable title="{esc(tr("sessions a human joined"))}">{tr("My part")}</th>'
                     f'<th class=sortable title="{esc(tr("my total messages"))}">{tr("My msgs")}</th>'
                     f'<th class=sortable title="{esc(tr("output (generated) tokens. hover = full input/output/cache breakdown"))}">{tr("Out tokens")}</th>'
                     f'<th title="{esc(tr("models used in this folder and response counts"))}">{tr("Models")}</th>'
                     f'<th class=sortable title="{esc(tr("total size of all sessions"))}">{tr("Size")}</th>'
                     f'<th class=sortable title="{esc(tr("autonomous build-loop sessions"))}">🔁</th></tr></thead><tbody>' + "".join(ov)
                     + f'<tr class=tot><td>{tr("Total")} {len(by)} {tr("folders")}</td><td>{tot["sessions"]}</td><td>{tot["my_sessions"]}</td>'
                     f'<td>{tot["my_msgs"]}</td><td title="{esc(_toktip(tot["tok"]))}">{fmt_tok(tot["tok"]["out"])}</td>'
                     f'<td class=mdlcell>{models_badge(tot["models"])}</td><td>{fmt_size(tot["size"])}</td>'
                     f'<td>{tot["loop"] or ""}</td></tr></tbody></table>')
            statsblock = (f'<details class="card" open><summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                          f'📊 {tr("Project stats")} ({len(by)} {tr("folders")}) · {tr("click a column header to sort")}</summary>{table}'
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
                f'{star_btn(it["sid"])} '
                f'<a class=t href="{link}">{esc(it["title"])}</a>{loopchip}'
                f'<div class=meta><a class="chip chiplink" href="{q(proj=it["proj"], sort=sort, dir=dir_)}" title="{esc(tr("show this workspace only"))}">{esc(proj_label(it))}</a> '
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
        favbar = (f'<div class=favbar>⭐ <b>{len(_STARS)}</b> {tr("favorites")} · '
                  f'<a href="/api/stars.json" download>⬇ {tr("export")}</a> · '
                  f'<label class=favimp>⬆ {tr("import")}<input type=file id=starimport accept="application/json,.json" hidden></label>'
                  f' <span class=hint>{tr("kept on this machine; export to move to another computer")}</span></div>')
        # fixed bottom status bar — where you are (folder, and workspace when filtered)
        if proj_filter:
            crumb_root = f'<a class=crumb href="/?{urllib.parse.urlencode({"root": root})}" title="{esc(tr("this folder"))}">📁 {esc(short_path(root))}</a>'
            crumb = (f'<div class=crumbs>{crumb_root} <span class=crumbsep>›</span> '
                     f'<span class=crumbcur>📂 {esc(proj_cwd.get(proj_filter, proj_filter))}</span></div>')
        else:
            crumb = f'<div class=crumbs><span class=crumbcur>📁 {esc(short_path(root))}</span> <span class=hint>{len(items)} {tr("sessions")}</span></div>'
        return shell(tr("AI Session Search"), crumb + head + favbar + statsblock + "".join(sortbar) + "".join(projbar) + "".join(rows), root=root)

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
            proj_href = "/?" + urllib.parse.urlencode({"proj": r["proj"], "root": root})
            rows.append(f'<div class=card><a class=t href="{openurl}">{hl(r["title"], hlq)}</a> '
                        f'<span class=meta>{cnt}</span>{exact}{kchip}'
                        f'<div class=meta><a class="chip chiplink" href="{proj_href}" title="{esc(tr("show this workspace only"))}">{esc(short)}</a></div>{metaline}{snips}</div>')

        keys = " ".join(f'<span class="hlkey hl{i % HL_COLORS}">{esc(t)}</span>' for i, t in enumerate(hl_terms))
        when = (f' · {esc(from_ or "…")}~{esc(to or "…")}' if (from_ or to) else
                (" · " + tr(DAY_CHOICES[days]) if days else ""))
        more = f' · <span class=hint>(+{truncated} {tr("more, refine to narrow")})</span>' if truncated > 0 else ""
        head = (f'<p class=meta>{keys} — {len(results)} {tr("sessions matched")} ({tr("by relevance")}) · {tr(SCOPES[scope])}{when} · {ms}ms{more} · '
                f'📁 {esc(short_path(root))} · <span class=hint>{tr("click a snippet to jump there")}</span></p>')
        return shell(f"{tr('Search')}: {q}", head + projbar + ("".join(rows) or f"<p class=meta>{tr('No results.')}</p>"),
                     q, scope, root, days, from_, to)

    # ---- session ----
    def session(self, path, q="", filt="all", off=0, lim_raw="", thread="", view="", goto="", sq="", sqtools=""):
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
        proj = next((it["proj"] for it in get_index(rt) if it["path"] == path), "")
        cc = esc(tr("click to copy"))
        def copyicon(text):   # 📋 button — for values that ALSO have a click action (navigate)
            return f' <span class=copybtn data-copy="{esc(text)}" title="{cc}">📋</span>'
        def copycode(text, cls):   # nothing to navigate to → click the value itself to copy
            return f'<code class="{cls} copyval" title="{cc}">{esc(text)}</code>'
        mrows = []
        if workspace:
            if proj:  # click the path → jump to this workspace's sessions; 📋 = copy
                ws_href = "/?" + urllib.parse.urlencode({"proj": proj, "root": rt})
                ws_val = (f'<a class=slink href="{ws_href}" title="{esc(tr("see all sessions in this workspace"))}">'
                          f'📂 <code class=spath>{esc(workspace)}</code></a>{copyicon(workspace)}')
            else:
                ws_val = copycode(workspace, "spath")
            mrows.append(_srow("Workspace", ws_val))
        if started and started != workspace:
            mrows.append(_srow("Started in",
                               f'{copycode(started, "spath")} <span class=hint>· {tr("folder the session started in (the file moved to a different workspace)")}</span>'))
        mrows.append(_srow(tr("Session file"), copycode(path, "spath")))
        mrows.append(_srow("session-id", copycode(sid, "sid")))
        if forked:
            pf = find_session_by_sid(rt, forked)
            fv = (f'<a class=slink href="/session?p={urllib.parse.quote(pf)}"><code class=sid>{esc(forked)}</code></a>{copyicon(forked)}'
                  if pf else f'{copycode(forked, "sid")} <span class=hint>· {tr("not in this folder")}</span>')
            mrows.append(_srow("Branched from", fv))
        if meta.get("branch"):
            mrows.append(_srow("git", copycode(meta["branch"], "sid")))
        resume = {"codex": f"codex resume {sid}", "claude": f"claude --resume {sid}"}.get(prov)
        if resume:
            mrows.append(_srow(tr("Resume"), copycode(resume, "sid")))
        mrows.append(_srow(tr("Stored in"), f'📁 {esc(short_path(rt))} · {fmt_ts(meta["last_ts"])}'))
        refcard = f'<details class="card srefcard" open><summary>📍 {tr("Session info (Session Reference)")}</summary><div class=srefbody>{"".join(mrows)}</div></details>'
        star = star_btn(sid)
        PROV_LABEL = {"codex": "🌀 Codex", "gemini": "✨ Gemini", "claude": "✴️ Claude Code"}
        pbadge = f'<span class="chip provbadge {prov}">{PROV_LABEL.get(prov, prov)}</span> '
        # breadcrumb: folder › workspace › this session · id (folder/workspace click to filter, id copies)
        crumb_root = f'<a class=crumb href="/?{urllib.parse.urlencode({"root": rt})}" title="{esc(tr("this folder"))}">📁 {esc(short_path(rt))}</a>'
        crumb_ws = (f' <span class=crumbsep>›</span> <a class=crumb href="/?{urllib.parse.urlencode({"proj": proj, "root": rt})}" title="{esc(tr("this workspace"))}">📂 {esc(short_path(workspace) or proj)}</a>'
                    if (workspace and proj) else "")
        crumb = (f'<div class=crumbs>{crumb_root}{crumb_ws}'
                 f' <span class=crumbsep>›</span> <span class=crumbcur>{esc(meta["title"])}</span>'
                 f' <code class="sid copyval" title="{esc(tr("click to copy"))}">{esc(sid)}</code></div>')
        head = (crumb + f'<h3 style="margin:4px 0 8px">{star} {pbadge}{esc(meta["title"])}'
                + (f' <span class=loopchip>🔁 {tr("autonomous build-loop")}</span>' if meta.get("loop") else "") + '</h3>')
        # prev/next session in the same project (work spans sessions)
        prev, nxt = adjacent_sessions(rt, path)
        if prev or nxt:
            pl = (f'<a href="/session?p={urllib.parse.quote(prev["path"])}">← {tr("prev")}: {esc(prev["title"][:38])}</a>'
                  if prev else "<span></span>")
            nl = (f'<a href="/session?p={urllib.parse.quote(nxt["path"])}">{tr("next")}: {esc(nxt["title"][:38])} →</a>'
                  if nxt else "")
            head += f'<div class="bar sessnav">{pl}{nl}</div>'
            # prefetch the adjacent sessions so j/k feels instant (browser renders them in the background)
            for _s in (prev, nxt):
                if _s:
                    head += f'<link rel=prefetch href="/session?p={urllib.parse.quote(_s["path"])}">'
        head += refcard + legend_html()
        # marker for the live-update poller (new messages appear without a manual reload)
        head += (f'<span id=livesess hidden data-p="{esc(path)}"'
                 f' data-new="{esc(tr("New messages"))}" data-load="{esc(tr("load"))}"></span>')

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
            head += (f'<details class="card" style="margin:10px 0">'
                     f'<summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                     f'🤖 {tr("Sub-agents this session spawned")}: {len(subs)}</summary>'
                     f'<div style="padding:8px 4px 2px">{sub_items}</div></details>')

        # extracted-fact digest — collapsed by default; a compact stat line stays in the summary
        d = session_digest(turns)
        mem_bit = f' · 🧠 {d["memory"]}' if d["memory"] else ''
        stat_preview = (f'<span class=meta style="font-weight:400" title="{esc(tr("edits (🧠 = agent-memory notes) · commands · tests · errors · commits · web pages"))}">'
                        f' — ✏️ {d["edits"]}{mem_bit} · ❯ {d["cmds"]} · 🧪 {d["tests"]} · ⚠️ {d["errors"]} · ⎇ {len(d["commits"])} · 🌐 {d["webs"]}</span>')
        dl = []
        if any(meta["tok"].values()):
            tk = meta["tok"]
            dl.append(f'<div style="margin-bottom:6px"><b>{tr("Tokens")}</b> {tok_badge(tk)} '
                      f'<span class=meta>{tr("Input")} {tk["in"]:,} · {tr("Output")} {tk["out"]:,} · '
                      f'{tr("Cache write")} {tk["cw"]:,} · {tr("Cache read")} {tk["cr"]:,}</span></div>')
        if meta["models"]:
            dl.append(f'<div style="margin-bottom:6px"><b>{tr("Models")}</b> {models_badge(meta["models"])}</div>')
        if d["mem_files"]:
            dl.append(f'<div style="margin-top:7px"><b>🧠 {tr("Memory notes written")}</b> ' +
                      "".join(f'<span class="dfile tk-mem">{esc(os.path.basename(f))}</span>' for f in d["mem_files"][:20]) +
                      (f'<span class=meta>… +{len(d["mem_files"])-20} {tr("more")}</span>' if len(d["mem_files"]) > 20 else "") + '</div>')
        if d["files"]:
            dl.append(f'<div style="margin-top:7px"><b>{tr("Files touched")}</b> ' +
                      "".join(f'<span class=dfile>{esc(short_path(f))}</span>' for f in d["files"][:25]) +
                      (f'<span class=meta>… +{len(d["files"])-25} {tr("more")}</span>' if len(d["files"]) > 25 else "") + '</div>')
        if d["commits"]:
            seen = {}
            for c in d["commits"]:
                seen[c] = seen.get(c, 0) + 1        # dedupe identical commits → show ×count
            items = "".join(f'<span class=dfile>⎇ {esc(c)}{(" ×"+str(k)) if k > 1 else ""}</span>'
                            for c, k in list(seen.items())[:12])
            more = f'<span class=meta>… +{len(seen)-12} {tr("more")}</span>' if len(seen) > 12 else ""
            dl.append(f'<div style="margin-top:7px"><b>{tr("Commits")}</b> ({len(d["commits"])}) {items}{more}</div>')
        if d["prs"]:
            dl.append(f'<div style="margin-top:7px"><b>{tr("PRs / issues")}</b> ' +
                      "".join(f'<a class=dfile href="{esc(u)}" target=_blank>{esc(u)}</a>' for u in d["prs"][:10]) + '</div>')
        digest = (f'<details class="card digest"><summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                  f'📊 {tr("Session summary (extracted facts)")}{stat_preview}</summary>'
                  f'<div style="margin-top:8px">{"".join(dl)}</div></details>')
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
            hits = [(gi, role) for gi, role, txt in search_turns(path)
                    if terms and all(t in txt.lower() for t in terms)]
            noise = {"tool-result", "system"}      # tool output / injected — usually search noise
            n_noise = sum(1 for _, role in hits if role in noise)
            show = [gi for gi, role in hits if sqtools or role not in noise]
            body = [render_turn(gi, turns[gi], sq, url(thread=gi) if turns[gi]["role"] == "you" else None)
                    for gi in show]
            ms = int((time.perf_counter() - t0) * 1000)
            if n_noise and not sqtools:
                extra = f' · <a href="{url(sq=sq, sqtools=1)}">+{n_noise} {tr("in tool results / system")}</a>'
            elif sqtools and n_noise:
                extra = f' · <a href="{url(sq=sq)}">{tr("hide tool results / system")}</a>'
            else:
                extra = ""
            bar = (f'<div class=bar><a class=backfull href="{url()}">← {tr("full conversation")}</a>'
                   f'<span class=meta>🔎 <b>{esc(sq)}</b> — {len(show)} {tr("messages matched in this session")}{extra} · {ms}ms'
                   f'<span id=perf></span></span></div>')
            return shell(meta["title"][:50], head + bar
                         + ("".join(body) or f"<p class=meta>{tr('No matches in the conversation (try “+… in tool results” above).')}</p>"), q, root=rt)

        # ---- CODE view ----
        if view == "code":
            arts = extract_code(turns)
            bar = (f'<div class=bar><a class=backfull href="{url(q=q)}">← {tr("to conversation")}</a>'
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
        # progressive render: paint the first chunk instantly, stream the rest in the background
        # (only for the plain conversation view — filtered/goto/search need everything up front)
        INIT_CHUNK = 120
        lazy = filt == "all" and goto_gi is None and len(page) > INIT_CHUNK
        body = []
        for gi, t in (page[:INIT_CHUNK] if lazy else page):
            tl = url(thread=gi, q=q) if t["role"] == "you" else None
            body.append(render_turn(gi, t, q, tl))
        if lazy:
            body.append(f'<div id=lazyload hidden data-p="{esc(path)}" data-since="{page[INIT_CHUNK][0]}" '
                        f'data-end="{page[-1][0] + 1}" data-q="{esc(q)}"></div>')
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
        cc = {"you": 0, "agent": 0, "error": 0, "edit": 0, "memory": 0, "command": 0, "commit": 0, "test": 0, "url": 0}
        for t in turns:
            if t["role"] == "you":
                cc["you"] += 1
            elif t["role"] == "assistant" and any(k in ("text", "channel") for k, _ in t["segs"]):
                cc["agent"] += 1
            for c in t["tags"]:
                if c in cc:
                    cc[c] += 1
        # "you" is intentionally NOT a chip — the "🧑 Only me" toggle above already does that (server-side).
        CHIP_LBL = {"agent": "✦ Agent", "error": "⚠️ Errors", "edit": "✏️ Edits",
                    "memory": "🧠 Memory", "command": "❯ Commands", "commit": "⎇ Commits", "test": "🧪 Tests", "url": "🔗 URL"}
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
                    + f'<span class=hint>· {tr("server")} {ms}ms<span id=perf></span> · {tr("showing")} {len(page)}/{total} {tr("msgs")} · '
                      f'<kbd>n</kbd>/<kbd>p</kbd> {tr("my messages")} · <kbd>j</kbd>/<kbd>k</kbd> {tr("sessions")} · <kbd>?</kbd> {tr("all shortcuts")}</span>'
                    + '</form>')
        pg = []
        if lim is not None:
            if off > 0:
                pg.append(f'<a href="{url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=max(0, off-lim))}">← {tr("Prev")}</a>')
            if off + lim < total:
                pg.append(f'<a href="{url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=off+lim)}">{tr("Next")} {min(lim, total-off-lim)} →</a>')
        pgbar = f'<div class=pg>{"".join(pg)}</div>' if pg else ""
        # targets for the keyboard shortcuts (j/k session, [/] page, m only-me toggle)
        def _sh(s): return f'/session?p={urllib.parse.quote(s["path"])}' if s else ""
        navkeys = ('<span id=navkeys hidden'
                   f' data-prevsess="{esc(_sh(prev))}" data-nextsess="{esc(_sh(nxt))}"'
                   f' data-prevpage="{esc(url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=max(0, off-lim)) if (lim is not None and off > 0) else "")}"'
                   f' data-nextpage="{esc(url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=off+lim) if (lim is not None and off+lim < total) else "")}"'
                   f' data-onlyme="{esc(url(filter="human", q=q, lim=lim_raw))}" data-showall="{esc(url(q=q, lim=lim_raw))}"'
                   f' data-list="{esc(("/?" + urllib.parse.urlencode({"proj": proj, "root": rt})) if proj else "/")}"'
                   f' data-code="{esc(url(view="code", q=q))}" data-filt="{esc(filt)}"></span>')
        return shell(meta["title"][:50], head + navkeys + toggles + "".join(chips) + sizeform + pgbar + "".join(body) + pgbar, q, root=rt)

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

# ---- MCP server (stdio JSON-RPC) --------------------------------------------
# A tiny, dependency-free Model Context Protocol server so coding agents can
# search the user's own past sessions (across Claude Code / Codex / Gemini)
# before re-solving something. Speaks newline-delimited JSON-RPC 2.0 on stdio.
MCP_TOOLS = [
    {"name": "search_sessions",
     "description": "Search the user's OWN past AI coding sessions (Claude Code, Codex, Gemini CLI) — their real "
                    "prompts, the assistant's answers, tool commands, file paths, and code. Returns matching "
                    "sessions with snippets. Use this BEFORE re-solving something to recall a prior decision, a "
                    "command that worked, code you wrote before, or 'how did we do X last time'.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description":
                   "words are AND-ed; \"quote\" for phrases; field filters file: cmd: code: error: role:me id:<uuid>; "
                   "-word to exclude"},
         "scope": {"type": "string", "enum": list(SCOPES),
                   "description": "all | human (the user's prompts) | claude (assistant) | chat | code | tool",
                   "default": "all"},
         "limit": {"type": "integer", "default": 20}},
         "required": ["query"]}},
    {"name": "get_session",
     "description": "Fetch the full content (all turns as plain text) of one past session by its id (or file path). "
                    "Use after search_sessions to read the details of a hit.",
     "inputSchema": {"type": "object", "properties": {
         "sid": {"type": "string", "description": "session id (full or prefix) from search_sessions"},
         "path": {"type": "string", "description": "absolute transcript path (alternative to sid)"},
         "limit": {"type": "integer", "default": 400, "description": "max turns to return"}}}},
    {"name": "list_recent_sessions",
     "description": "List the user's most recent past sessions (optionally one provider). Use to see what was "
                    "worked on lately across projects.",
     "inputSchema": {"type": "object", "properties": {
         "provider": {"type": "string", "enum": ["claude", "codex", "gemini"]},
         "limit": {"type": "integer", "default": 20}}}},
]

def _mcp_call(name, args):
    """Dispatch one MCP tool call to the data API. Returns a JSON-able object."""
    args = args or {}
    if name == "search_sessions":
        return search_all(args.get("query", ""), args.get("scope", "all"), int(args.get("limit", 20) or 20))
    if name == "get_session":
        res = session_api(args.get("path") or None, args.get("sid") or None, int(args.get("limit", 400) or 400))
        return res if res is not None else {"error": "session not found"}
    if name == "list_recent_sessions":
        prov, lim = args.get("provider"), int(args.get("limit", 20) or 20)
        seen, out = set(), []
        for r in ROOTS:
            for s in sessions_api(r, lim):
                if prov and s["provider"] != prov:
                    continue
                if s["path"] in seen:
                    continue
                seen.add(s["path"])
                out.append(s)
        out.sort(key=lambda x: x.get("date", ""), reverse=True)
        return out[:lim]
    return {"error": "unknown tool: " + str(name)}

def run_mcp():
    """Serve the MCP protocol on stdin/stdout. Nothing else may write to stdout."""
    def send(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    # warm caches quietly in the background (never prints) so the first search is fast
    threading.Thread(target=lambda: [_warm_cache(r) for r in ROOTS], daemon=True).start()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid, method = msg.get("id"), msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ai-session-search", "version": __version__}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": MCP_TOOLS}})
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                res = _mcp_call(p.get("name"), p.get("arguments"))
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": "error: " + str(e)}], "isError": True}})
        elif method is not None and mid is None:
            continue  # a notification (e.g. notifications/initialized) — no reply
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": "method not found: " + str(method)}})
    return 0

def _run_cli(args):
    """One-shot CLI queries (--search / --get / --sessions) for agents & scripts."""
    lim = max(1, min(int(args.limit or 20), 200))
    if args.get is not None:
        p = args.get if os.path.exists(os.path.expanduser(args.get)) else None
        res = session_api(os.path.expanduser(args.get) if p else None,
                          None if p else args.get, 2000)
        if res is None:
            print("session not found: " + args.get, file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"{res['title']}  [{res['provider']}]  {res['sid']}")
            print(f"workspace: {res['workspace']}")
            if res.get("models"):
                print("models: " + ", ".join(res["models"]))
            print("-" * 60)
            for t in res["turns"][:lim]:
                who = {"you": "🧑 You", "assistant": "🤖 Assistant"}.get(t["role"], t["role"])
                print(f"\n[{t['turn']}] {who}\n{t['text']}")
        return 0
    if args.sessions:
        rows = []
        for r in ROOTS:
            rows += sessions_api(r, lim)
        rows.sort(key=lambda x: x.get("date", ""), reverse=True)
        rows = rows[:lim]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for s in rows:
                print(f"{s['date']}  [{s['provider']}]  {s['sid']}  {s['title']}  · {s['workspace']}")
        return 0
    # --search
    res = search_all(args.search or "", args.scope, lim)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not res:
        print("(no matching sessions)")
        return 0
    for r in res:
        print(f"\n[{r['match']}]  {r['title']}  ({r['provider']})  {r['sid']}  · {r['workspace']}")
        for sn in r["snippets"][:3]:
            who = {"you": "🧑", "assistant": "🤖"}.get(sn["role"], "·")
            print(f"    {who} {sn['text'][:200]}")
    return 0

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
    ap.add_argument("--mcp", action="store_true",
                    help="run as an MCP server on stdio (no web UI) so coding agents can search your past sessions")
    ap.add_argument("--search", metavar="QUERY",
                    help="search past sessions and print results, then exit (no server). "
                         "Supports field filters file:/cmd:/code:/error:/role:/id: and \"phrases\"")
    ap.add_argument("--get", metavar="SID|PATH",
                    help="print the full content of one session (by id or path), then exit")
    ap.add_argument("--sessions", action="store_true", help="list recent sessions, then exit")
    ap.add_argument("--scope", default="all", choices=sorted(SCOPES),
                    help="search scope for --search (default: all)")
    ap.add_argument("--limit", type=int, default=20, help="max results for --search/--get/--sessions")
    ap.add_argument("--json", action="store_true", help="emit JSON for --search/--get/--sessions")
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
    if args.mcp:
        # stdio MCP mode: no web server, no banner (stdout is the JSON-RPC channel)
        return run_mcp()
    if args.search is not None or args.get is not None or args.sessions:
        return _run_cli(args)
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
