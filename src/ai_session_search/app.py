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
import bisect
import datetime
import difflib
import glob
import gzip
import hashlib
import hmac
import html
import json
import os
import pickle
import re
import sys
import threading
import time
import urllib.parse
from array import array
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ._icons import ICON_PNG_192, ICON_PNG_256

__version__ = "4.0.17"

# App icon — a speech bubble with a person mark (🧑 = "you"), the app's core idea.
# App icon: glass "AI" on a blue→green gradient with purple/cyan glows. Used as the
# favicon, PWA/apple-touch icon (rasterized by the browser), and the selected app in
# the install-screen ⌘-Tab strap. The brand gradient here matches the title-bar band.
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1" gradientTransform="rotate(-50,0.5,0.5)"><stop offset="0" stop-color="#0084ff"/><stop offset="0.52" stop-color="#1061b7"/><stop offset="0.93" stop-color="#b0ff29"/></linearGradient><radialGradient id="g0" cx="0.4" cy="0.21" r="0.684"><stop offset="0" stop-color="rgb(169,138,255)" stop-opacity="1"/><stop offset="1" stop-color="rgb(169,138,255)" stop-opacity="0"/></radialGradient><radialGradient id="g1" cx="0.84" cy="0.86" r="0.684"><stop offset="0" stop-color="rgb(105,245,247)" stop-opacity="0.88"/><stop offset="1" stop-color="rgb(105,245,247)" stop-opacity="0"/></radialGradient><clipPath id="sq"><rect x="100" y="100" width="824" height="824" rx="180"/></clipPath><filter id="fx0" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceAlpha" stdDeviation="14" result="shb"/><feOffset in="shb" dy="10" result="sho"/><feFlood flood-color="#04352C" flood-opacity="0.45" result="shc"/><feComposite in="shc" in2="sho" operator="in" result="shadow"/><feGaussianBlur in="SourceAlpha" stdDeviation="40" result="glb"/><feFlood flood-color="#CFFFEE" flood-opacity="1" result="glc"/><feComposite in="glc" in2="glb" operator="in" result="glow"/><feComponentTransfer in="SourceGraphic" result="body"><feFuncA type="linear" slope="1"/></feComponentTransfer><feOffset in="SourceAlpha" dx="-7.5" dy="-7.5" result="lo1"/><feComposite in="SourceAlpha" in2="lo1" operator="out" result="lo2"/><feGaussianBlur in="lo2" stdDeviation="6.5" result="lo3"/><feFlood flood-color="#0A4A3E" flood-opacity="0.77" result="lo4"/><feComposite in="lo4" in2="lo3" operator="in" result="lowlight"/><feOffset in="SourceAlpha" dx="7.5" dy="7.5" result="hi1"/><feComposite in="SourceAlpha" in2="hi1" operator="out" result="hi2"/><feGaussianBlur in="hi2" stdDeviation="6.5" result="hi3"/><feFlood flood-color="#FFFFFF" flood-opacity="0.79" result="hi4"/><feComposite in="hi4" in2="hi3" operator="in" result="highlight"/><feMerge><feMergeNode in="shadow"/><feMergeNode in="glow"/><feMergeNode in="body"/><feMergeNode in="lowlight"/><feMergeNode in="highlight"/></feMerge></filter></defs>
<g clip-path="url(#sq)"><rect x="100" y="100" width="824" height="824" fill="url(#bg)"/><rect x="100" y="100" width="824" height="824" fill="url(#g0)"/><rect x="100" y="100" width="824" height="824" fill="url(#g1)"/></g>
<g filter="url(#fx0)"><text x="512" y="512" font-family="-apple-system,Helvetica,Arial,sans-serif" font-size="730" font-weight="700" fill="#FFFFFF" text-anchor="middle" dominant-baseline="central">AI</text></g>
</svg>"""

# App icons for the install-screen ⌘-Tab strap — all hand-drawn generic lookalikes (no
# vendor artwork), in the same 56×56 rounded-square style. "Files" stands in for a
# file-manager slot. The strap itself is real CSS liquid glass (backdrop-filter) — see
# the .ct-* rules in PAGE CSS.
_IC_FINDER = """<svg viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg"><defs>
<linearGradient id="icfb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5ea6ff"/><stop offset="1" stop-color="#2a6fe0"/></linearGradient>
<linearGradient id="icff" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#e6f0ff"/></linearGradient></defs>
<rect width="56" height="56" rx="13" fill="url(#icfb)"/>
<path d="M13 21c0-1.7 1.3-3 3-3h7.2c.9 0 1.7.4 2.3 1.1l1.6 1.9H40c1.7 0 3 1.3 3 3v11c0 1.7-1.3 3-3 3H16c-1.7 0-3-1.3-3-3V21Z" fill="url(#icff)"/>
<path d="M13 24.5h30V35c0 1.7-1.3 3-3 3H16c-1.7 0-3-1.3-3-3V24.5Z" fill="#cfe1ff"/></svg>"""
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
UPDATE_FILE = os.path.join(CONFIG_DIR, "update.json")  # cached latest-release check (throttled to 1/day)
REPO_SLUG = "kim-dongryeong/ai-session-search"
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

# ---- update check -----------------------------------------------------------
# Privacy: this is the ONLY thing the app ever sends over the network. It is a plain
# unauthenticated GET of the public GitHub releases endpoint — no identifiers, no query,
# and never any transcript content. It runs at most once/24h (cached to update.json),
# and is fully disabled by AISS_NO_UPDATE_CHECK=1 (or CCH_NO_UPDATE_CHECK=1).
_UPDLOCK = threading.Lock()

def _ver_tuple(v):
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) if nums else (0,)

def update_disabled():
    return bool(os.environ.get("AISS_NO_UPDATE_CHECK") or os.environ.get("CCH_NO_UPDATE_CHECK"))

def check_update(force=False):
    """Return {current, latest, newer, url, frozen, checked, disabled}. Never raises."""
    frozen = bool(getattr(sys, "frozen", False))
    info = {"current": __version__, "latest": None, "newer": False, "frozen": frozen,
            "url": f"https://github.com/{REPO_SLUG}/releases/latest", "checked": 0,
            "disabled": update_disabled()}
    if info["disabled"]:
        return info
    with _UPDLOCK:
        cache = {}
        try:
            with open(UPDATE_FILE, encoding="utf-8") as fh:
                cache = json.load(fh)
        except (OSError, ValueError):
            cache = {}
        fresh = (time.time() - float(cache.get("checked", 0))) < 86400
        if not (fresh and cache.get("latest") and not force):
            try:
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{REPO_SLUG}/releases/latest",
                    headers={"Accept": "application/vnd.github+json",
                             "User-Agent": f"ai-session-search/{__version__}"})
                with urllib.request.urlopen(req, timeout=3) as r:
                    data = json.load(r)
                latest = (data.get("tag_name") or "").lstrip("vV").strip() or None
                cache = {"checked": time.time(), "latest": latest,
                         "url": data.get("html_url") or info["url"]}
                try:
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    with open(UPDATE_FILE, "w", encoding="utf-8") as fh:
                        json.dump(cache, fh)
                except OSError:
                    pass
            except Exception:
                pass  # offline / rate-limited / DNS — stay silent, reuse any cached value
    info["latest"] = cache.get("latest")
    info["checked"] = float(cache.get("checked", 0) or 0)
    if cache.get("url"):
        info["url"] = cache["url"]
    if info["latest"]:
        info["newer"] = _ver_tuple(info["latest"]) > _ver_tuple(__version__)
    return info

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
             os.path.expanduser(os.path.join("~", ".gemini", "antigravity", "brain")), # Antigravity
             os.path.expanduser(os.path.join("~", ".gemini", "antigravity-cli", "brain")), # Antigravity CLI
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
    raw = path.strip()
    # paths pasted from Finder/터미널 often arrive quoted ('/My Drive/…') or with
    # shell-escaped spaces (My\ Drive) — unwrap both before resolving
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1].strip()
    p = os.path.abspath(os.path.expanduser(raw))
    if not os.path.isdir(p) and "\\ " in raw:
        p = os.path.abspath(os.path.expanduser(raw.replace("\\ ", " ")))
    if not os.path.isdir(p):
        return None
    for cand in (p, os.path.join(p, "projects"), os.path.join(p, ".claude", "projects")):
        if os.path.isdir(cand) and glob.glob(os.path.join(cand, "*", "*.jsonl")):
            return cand
    return None

def configure(primary_root=None, extra_roots=(), exclusive=False):
    """(Re)initialize app state. Called by main(); tests call it directly.
    exclusive=True uses ONLY primary + extra_roots (no auto-discovery, no saved roots) —
    used by --demo so it never touches your real Claude/Codex/Gemini history."""
    global ROOT, ROOTS, DEFAULT_ROOTS, SAVED_ROOTS, _STARS, _EXCLUSIVE
    _EXCLUSIVE = exclusive   # demo/test data must never read or write the disk cache
    _STARS = load_stars()
    primary = os.path.abspath(os.path.expanduser(primary_root or default_primary_root()))
    if exclusive:
        DEFAULT_ROOTS = [primary] + [os.path.abspath(os.path.expanduser(p))
                                     for p in extra_roots if p and os.path.isdir(os.path.expanduser(p))]
        SAVED_ROOTS = []
    else:
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
        _INDEX["slow"].clear()
    with _SEARCH["lock"]:
        _SEARCH["by_path"].clear()
    with _SESSION["lock"]:
        _SESSION["by_path"].clear()
    with _DISK["lock"]:
        _DISK["loaded"].clear()
        _DISK["rows_loaded"].clear()
        _DISK["dirty"].clear()
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

def active_roots(v):
    """Selected roots from a `root` param — multi-select. None/''/'*' → all roots;
    a comma-separated list (or a single root, back-compat) → that subset, in ROOTS order."""
    if not v or v == "*":
        return list(ROOTS)
    picked = set(v.split(","))
    sel = [r for r in ROOTS if r in picked]
    return sel or list(ROOTS)

def root_param(sel):
    """Canonical `root` URL param for a selection: '' when it means all roots."""
    return "" if len(sel) >= len(ROOTS) else ",".join(sel)
DEFAULT_LIM = 1000
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
    if "/antigravity/brain/" in q or "/antigravity-cli/brain/" in q or b == "transcript.jsonl":
        return "agy"
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

_TASK_FIELD_RE = re.compile(
    r"<(task-id|tool-use-id|output-file|status|summary|note|result|usage)>(.*?)</\1>", re.S)

def parse_task_notification(text):
    """Extract the useful payload from a Claude Code ``<task-notification>``.

    Recent Claude Code versions persist completed background-agent results first as a
    ``queue-operation/enqueue`` record, then mirror the same payload in attachment/remove
    records.  Only the enqueue record should become a turn; the mirrors are duplicates.
    """
    if not isinstance(text, str) or not text.lstrip().startswith("<task-notification>"):
        return None
    fields = {k: html.unescape(v.strip()) for k, v in _TASK_FIELD_RE.findall(text)}
    result = fields.get("result", "").strip()
    if not result:
        return None
    return {"task_id": fields.get("task-id", ""), "status": fields.get("status", ""),
            "summary": fields.get("summary", ""), "result": result}

def task_notification_text(text):
    """Search/API text for a parsed task notification."""
    task = parse_task_notification(text)
    if not task:
        return str(text or "")
    return "\n\n".join(x for x in (task["summary"], task["result"]) if x)

_CHANNEL_NAMES = [("telegram", "Telegram"), ("slack", "Slack"), ("discord", "Discord"),
                  ("whatsapp", "WhatsApp"), ("sms", "SMS"), ("email", "Email")]

def channel_label(attrs):
    src = (attrs.get("source") or "").lower()
    name = next((nm for key, nm in _CHANNEL_NAMES if key in src), "Channel")
    user = attrs.get("user") or attrs.get("user_id") or ""
    return f"💬 {esc(tr(name))}" + (f" · @{esc(user)}" if user else "")

def classify_line(o, sub=False):
    t = o.get("type")
    # Claude Code 2.x may store a completed background-agent result only in the queue
    # lifecycle records.  Keep the first (enqueue) copy and skip attachment/remove mirrors.
    if t == "queue-operation" and o.get("operation") == "enqueue":
        content = o.get("content")
        if parse_task_notification(content):
            return ("system", [("task_notification", content)])
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
            if s.startswith("<task-notification>") and parse_task_notification(content):
                return ("system", [("task_notification", content)])
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
    if prov == "agy":
        return _agy_load(path)["turns"]
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

# ---- Antigravity support (~/.gemini/antigravity/brain/<session>/.system_generated/logs/transcript.jsonl) --------
def _agy_sid(path):
    m = re.search(r"/brain/([0-9a-f\-]+)/", path.replace(os.sep, "/"))
    return m.group(1) if m else os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path))))

def _agy_uri_to_path(uri):
    from urllib.parse import unquote
    m = re.search(r"file://(/[^\s\"']+)", uri or "")
    return unquote(m.group(1)) if m else ""

_AGY_TITLES = {"ts": {}, "data": {}}
def get_agy_meta(path):
    """(title, cwd) for an Antigravity session, from its summary stores."""
    root = root_for_path(path)
    if not root: return (None, "")
    sid = _agy_sid(path)
    if not sid: return (None, "")
    title, cwd = None, ""

    # 1. Check annotations/<sid>.pbtxt for renamed titles
    anno_path = os.path.join(root, "..", "annotations", f"{sid}.pbtxt")
    if os.path.exists(anno_path):
        try:
            with open(anno_path, "r", encoding="utf-8") as f:
                content = f.read()
            m = re.search(r'title\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', content)
            if m:
                title = json.loads('"' + m.group(1) + '"')
        except Exception:
            pass

    # 2. Check SQLite DB (used by CLI)
    db_path = os.path.join(root, "..", "conversation_summaries.db")
    if os.path.exists(db_path):
        import sqlite3
        try:
            mtime = os.stat(db_path).st_mtime_ns
            if _AGY_TITLES["ts"].get(db_path) != mtime:
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                try:
                    c.execute("SELECT conversation_id, title, workspace_uris FROM conversation_summaries")
                    res = {row[0]: (row[1], _agy_uri_to_path(row[2])) for row in c.fetchall()}
                except sqlite3.OperationalError:
                    c.execute("SELECT conversation_id, title FROM conversation_summaries")
                    res = {row[0]: (row[1], "") for row in c.fetchall()}
                conn.close()
                _AGY_TITLES["data"][db_path] = res
                _AGY_TITLES["ts"][db_path] = mtime
            hit = _AGY_TITLES["data"].get(db_path, {}).get(sid)
            if hit:
                return (title or hit[0], hit[1])
        except Exception:
            pass

    # 3. Check Protobuf (used by standard GUI)
    pb_path = os.path.join(root, "..", "agyhub_summaries_proto.pb")
    if os.path.exists(pb_path):
        try:
            mtime = os.stat(pb_path).st_mtime_ns
            if _AGY_TITLES["ts"].get(pb_path) != mtime:
                with open(pb_path, "rb") as f:
                    data = f.read()
                res = {}
                for m in re.finditer(b"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", data):
                    m_sid = m.group(1).decode("utf-8")
                    idx = m.end()
                    pb_title, pb_cwd = res.get(m_sid, ("", ""))
                    n_idx = data.find(b'\n', idx, idx + 20)
                    if n_idx != -1:
                        strlen = data[n_idx+1]
                        try:
                            dec = data[n_idx+2:n_idx+2+strlen].decode("utf-8")
                            if dec:
                                pb_title = dec
                        except Exception:
                            pass
                    # a workspace mapping puts a length-prefixed file:// URI right after the sid
                    w = data.find(b"file://", idx, idx + 20)
                    if w != -1 and not pb_cwd:
                        strlen = data[w-1]
                        if strlen < 0x80 and w >= 2 and data[w-2] & 0x80:  # 2-byte varint length
                            strlen = (data[w-2] & 0x7f) | (strlen << 7)
                        pb_cwd = _agy_uri_to_path(data[w:w+strlen].decode("utf-8", "replace"))
                    res[m_sid] = (pb_title, pb_cwd)
                _AGY_TITLES["data"][pb_path] = res
                _AGY_TITLES["ts"][pb_path] = mtime
            hit = _AGY_TITLES["data"].get(pb_path, {}).get(sid)
            if hit:
                return (title or hit[0], hit[1])
        except Exception:
            pass

    return (title, cwd)

def get_agy_title(path):
    return get_agy_meta(path)[0]


def classify_agy_line(o):
    t = o.get("type")
    content = o.get("content", "")
    source = o.get("source")

    def strip_eph(text):
        if "<EPHEMERAL_MESSAGE>" in text:
            text = re.sub(r"<EPHEMERAL_MESSAGE>.*?</EPHEMERAL_MESSAGE>", "", text, flags=re.DOTALL).strip()
        return text

    if t == "USER_INPUT" and source in ("USER_EXPLICIT", "SYSTEM", "USER"):
        text = content
        if "<USER_REQUEST>" in text:
            m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", text, re.DOTALL)
            if m:
                text = m.group(1).strip()
        else:
            text = strip_eph(text)
        return ("you", [("text", text)]) if text.strip() else None

    if t == "PLANNER_RESPONSE" and source == "MODEL":
        segs = []
        if o.get("thinking"):
            segs.append(("thinking", o.get("thinking").strip()))
        if content.strip():
            segs.append(("text", content))
        for tc in o.get("tool_calls", []):
            name = tc.get("name", "tool")
            args = tc.get("arguments", tc.get("args", {}))
            segs.append(("tool_use", f"{name}\n{json.dumps(args, ensure_ascii=False)}"))
        return ("assistant", segs) if segs else None

    if source == "MODEL" and t not in ("PLANNER_RESPONSE", "USER_INPUT"):
        text = strip_eph(content)
        return ("tool-result", [("tool_result", text)]) if text else None

    if t == "SYSTEM_MESSAGE" or source == "SYSTEM":
        text = strip_eph(content)
        return ("system", [("injected", text)]) if text else None

    return None

def _agy_load(path):
    cwd = model = last_ts = first_human = ""
    n = {"you": 0, "assistant": 0, "tool-result": 0, "system": 0, "subagent": 0}
    turns = []
    for o in iter_lines(path):
        if o.get("created_at"):
            last_ts = o["created_at"]
        for tc in o.get("tool_calls") or []:
            args = tc.get("arguments", tc.get("args", {}))
            c = (args.get("Cwd") or "").strip().strip('"') if isinstance(args, dict) else ""
            # keep the shortest ancestor seen, so a repo root beats its subdirs
            if c.startswith("/") and (not cwd or cwd.startswith(c)):
                cwd = c
        r = classify_agy_line(o)
        if not r:
            continue
        role, segs = r
        turn = {"role": role, "segs": segs, "ts": o.get("created_at", ""), "tags": turn_tags(o, role, segs)}
        if role == "assistant":
            turn["model"] = "Antigravity"
        turns.append(turn)
        if role in n:
            n[role] += 1
        if role == "you" and not first_human:
            first_human = " ".join(x[1] for x in segs if x[0] == "text").strip()
    meta_title, meta_cwd = get_agy_meta(path)
    cwd = meta_cwd or cwd
    title = (meta_title or first_human or tr("(untitled)")).strip()[:120]
    meta = {"title": title, "preview": first_human.strip()[:140], "n": n, "last_ts": last_ts,
            "cwd": cwd, "start_cwd": cwd, "branch": "", "forked": "", "loop": False,
            "tok": {"in": 0, "out": 0, "cw": 0, "cr": 0}, "models": {"Antigravity": 1}}
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
    ctx = ""   # the most recent human message — "what was being worked on" for the blocks that follow
    for gi, t in enumerate(turns):
        if t["role"] == "you":
            prose = CODE_FENCE_RE.sub("", " ".join(x for k, x in t["segs"] if k in ("text", "channel")))
            prose = " ".join(prose.split())
            if prose:
                ctx = prose
        for kind, txt in t["segs"]:
            if kind == "text" and t["role"] in ("assistant", "you"):   # code you pasted counts too
                who = "you" if t["role"] == "you" else "agent"
                for m in CODE_FENCE_RE.finditer(txt):
                    body = m.group(2)
                    if body.strip():
                        arts.append({"gi": gi, "label": (m.group(1) or "code"), "kind": "block",
                                     "who": who, "ctx": ctx, "body": body, "ts": t["ts"]})
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
                        arts.append({"gi": gi, "label": fp, "kind": "edit", "who": "agent",
                                     "ctx": ctx, "body": str(body), "ts": t["ts"]})
    return arts

# ---- per-file summary -------------------------------------------------------
def summarize_file(path):
    prov = provider_of(path)
    if prov == "codex":
        return _codex_load(path)["meta"]
    if prov == "agy":
        return _agy_load(path)["meta"]
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
    elif prov == "agy":
        data = _agy_load(path)
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
_INDEX = {"by_root": {}, "slow": {}, "lock": threading.Lock()}

# ---- persistent cache (disk) -------------------------------------------------
# The in-memory index/search caches are rebuilt from CONFIG_DIR/cache/ on start, so
# a fresh server (reboot, update, relaunch) skips reparsing unchanged transcripts.
# Safety: entries loaded from disk go through the SAME (mtime_ns, size) revalidation
# as always — a stale disk entry is simply reparsed. Bump _CACHE_SCHEMA whenever the
# shape of _index_item() output or search rows changes, so old caches are discarded.
_CACHE_SCHEMA = 6
_DISK = {"loaded": set(), "rows_loaded": set(), "dirty": set(), "lock": threading.Lock(),
         "io_idx": threading.Lock(), "io_rows": threading.Lock()}
_EXCLUSIVE = False   # set by configure(); demo/exclusive data never touches the cache

def _cache_base(root):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", root).strip("-")[-80:]
    h = hashlib.md5(root.encode("utf-8")).hexdigest()[:8]
    return os.path.join(CONFIG_DIR, "cache", f"{slug}-{h}")

def _load_disk_cache(root, rows=False):
    """Merge the on-disk cache for `root` into the in-memory caches (once per root).
    The tiny index cache always loads; the big search-rows cache only when rows=True
    (search entry points / warm-up) so the landing page never waits on it.
    Best-effort: a missing/corrupt/old-schema file is ignored and rebuilt by parsing."""
    if _EXCLUSIVE:
        return
    # The io locks serialize loads AND make concurrent callers wait for completion —
    # marking the root loaded up front let a racing search thread skip the load and
    # reparse hundreds of files while the warm thread was still merging (40s search).
    # idx and rows lock separately so the tiny index load never queues behind the
    # multi-hundred-MB rows load.
    with _DISK["io_idx"]:
        with _DISK["lock"]:
            need_idx = root not in _DISK["loaded"]
        if need_idx:
            _load_disk_cache_locked(root, True, False)
            with _DISK["lock"]:
                _DISK["loaded"].add(root)
    if not rows:
        return
    with _DISK["io_rows"]:
        with _DISK["lock"]:
            need_rows = root not in _DISK["rows_loaded"]
        if need_rows:
            _load_disk_cache_locked(root, False, True)
            with _DISK["lock"]:
                _DISK["rows_loaded"].add(root)

def _load_disk_cache_locked(root, need_idx, need_rows):
    base = _cache_base(root)
    if need_idx:
        try:
            with gzip.open(base + ".idx.json.gz", "rt", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("schema") == _CACHE_SCHEMA:
                entries = {p: (tuple(v[0]), v[1]) for p, v in d["items"].items()}
                with _INDEX["lock"]:
                    cache = _INDEX["by_root"].setdefault(root, {})
                    for p, v in entries.items():
                        cache.setdefault(p, v)
        except Exception:
            pass
    if need_rows:
        # one pickle record per file, merged as we go — a single giant dict load
        # fragments the allocator and retains ~1.4GB it never gives back
        try:
            with gzip.open(base + ".rows.pkl.gz", "rb") as f:
                head = pickle.load(f)
                if head.get("schema") == _CACHE_SCHEMA:
                    while True:
                        try:
                            p, key, rws, blob, tokens = pickle.load(f)
                        except EOFError:
                            break
                        with _SEARCH["lock"]:
                            _SEARCH["by_path"].setdefault(p, (key, rws, blob, tokens))
        except Exception:
            pass

def _save_disk_cache(root):
    """Persist `root`'s caches (atomic replace). Called after warm-up and on exit."""
    if _EXCLUSIVE:
        return
    try:
        os.makedirs(os.path.join(CONFIG_DIR, "cache"), exist_ok=True)
        base = _cache_base(root)
        with _INDEX["lock"]:
            idx = {p: [list(v[0]), v[1]] for p, v in _INDEX["by_root"].get(root, {}).items()}
        tmp = base + ".idx.json.gz.tmp"
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump({"schema": _CACHE_SCHEMA, "items": idx}, f, ensure_ascii=False)
        os.replace(tmp, base + ".idx.json.gz")
        with _SEARCH["lock"]:   # only this root's files; blob stored too — rebuilding it on
            rows = {p: v for p, v in _SEARCH["by_path"].items() if p in idx}   # load churned
        tmp = base + ".rows.pkl.gz.tmp"                    # ~1GB the allocator never returned
        with gzip.open(tmp, "wb", compresslevel=1) as f:   # level 1: big data, speed wins
            pickle.dump({"schema": _CACHE_SCHEMA}, f, protocol=pickle.HIGHEST_PROTOCOL)
            for p, (key, rws, blob, tokens) in rows.items():   # one record per file (streamed load)
                pickle.dump((p, key, rws, blob, tokens), f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, base + ".rows.pkl.gz")
        with _DISK["lock"]:
            _DISK["dirty"].discard(root)
    except Exception:
        pass

def _save_dirty_caches():
    with _DISK["lock"]:
        dirty = list(_DISK["dirty"])
    for r in dirty:
        _save_disk_cache(r)

def is_codex_root(root):
    q = (root or "").replace(os.sep, "/")
    return "/.codex/" in q or q.rstrip("/").endswith("/.codex/sessions")

def is_gemini_root(root):
    q = (root or "").replace(os.sep, "/")
    return "/.gemini/" in q or q.rstrip("/").endswith("/.gemini/tmp")

def is_agy_root(root):
    q = (root or "").replace(os.sep, "/")
    return "/.gemini/antigravity/brain" in q or "/.gemini/antigravity-cli/brain" in q or q.rstrip("/").endswith("/brain")

def root_glyph(root):
    """Provider glyph for a folder — by kind or by 'codex'/'gemini'/'claude'/'agy' in its path."""
    q = (root or "").lower().replace(os.sep, "/")
    if is_codex_root(root) or "codex" in q:
        return "🌀 "
    if is_agy_root(root) or "agy" in q or "antigravity" in q:
        return "✨ "
    if is_gemini_root(root) or "gemini" in q:
        return "✨ "
    if "claude" in q:
        return "✴️ "
    return ""

PROV_LABEL = {"codex": "🌀 Codex", "gemini": "✨ Gemini", "claude": "✴️ Claude Code", "agy": "✨ Antigravity"}

def prov_badge(prov, root=None):
    """Small provider chip; the tooltip names the folder (distinguishes e.g. agy GUI vs CLI)."""
    t = f' title="{esc(short_path(root))}"' if root else ""
    return f'<span class="chip provbadge {esc(prov)}"{t}>{PROV_LABEL.get(prov, prov)}</span>'

def session_files(root):
    if is_codex_root(root):
        return sorted(glob.glob(os.path.join(root, "**", "rollout-*.jsonl"), recursive=True))
    if is_agy_root(root):
        return sorted(glob.glob(os.path.join(root, "*", ".system_generated", "logs", "transcript.jsonl")))
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
    p_agy = os.path.join(root, sid, ".system_generated", "logs", "transcript.jsonl")
    if os.path.exists(p_agy):
        return p_agy
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
    elif prov == "agy":
        proj = s["cwd"] or "agy"
        sid = _agy_sid(path)
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

def proj_canon(items):
    """Map each provider-specific project key to a canonical workspace path.

    Providers key projects differently — Claude by transcript-folder slug
    (``-Users-me-dev-app``), Codex/Gemini/AGY by workspace path — so the same
    workspace shows up under several keys and a ``?proj=`` filter from one provider
    misses the others. Canonical key = the project's most common session cwd
    (callers fall back to the key itself when no session recorded a cwd)."""
    cnt = {}
    for it in items:
        if it.get("cwd"):
            d = cnt.setdefault(it["proj"], {})
            d[it["cwd"]] = d.get(it["cwd"], 0) + 1
    return {p: max(d.items(), key=lambda kv: kv[1])[0] for p, d in cnt.items()}

_SLOW_SCAN_S = 2.0   # a root whose scan exceeds this stops blocking requests

def get_index(root, force=False):
    """Per-root index; re-summarizes only files whose (mtime, size) changed,
    picks up new sessions, and drops deleted ones — so a long-running server
    always shows current data at ~one stat() per file per request.

    Root isolation: when a root's last scan blew the _SLOW_SCAN_S budget (network
    filesystems like a Google Drive mount can stall for seconds), requests serve the
    cached items instead and a background thread refreshes it (force=True). One slow
    root must never hold every page hostage."""
    _load_disk_cache(root)
    if not force and _INDEX["slow"].get(root):
        with _INDEX["lock"]:
            items = [v[1] for v in _INDEX["by_root"].get(root, {}).values()]
        items.sort(key=lambda x: x["mtime"], reverse=True)
        return items
    t0 = time.monotonic()
    changed = False
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
                changed = True
        for gone in set(cache) - seen:
            del cache[gone]
            changed = True
        items = [v[1] for v in cache.values()]
    if changed:
        with _DISK["lock"]:
            _DISK["dirty"].add(root)
    _INDEX["slow"][root] = (time.monotonic() - t0) > _SLOW_SCAN_S
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

def _refresh_slow_roots():
    """Background loop: rescan roots that were demoted for being slow, off the
    request path, so their data stays reasonably fresh."""
    while True:
        time.sleep(30)
        for r in list(ROOTS):
            if _INDEX["slow"].get(r):
                try:
                    get_index(r, force=True)
                except Exception:
                    pass

def dedupe_sids(items):
    """(kept, copies) — collapse sessions that exist in several roots (e.g. a backup
    copy of ~/.claude/projects added as another folder). Keeps the freshest copy per
    session id; copies maps sid -> total count for the ⧉ badge. Items without a sid
    are never collapsed."""
    best = {}
    copies = {}
    for it in items:
        sid = it.get("sid") or ""
        if not sid:
            continue
        copies[sid] = copies.get(sid, 0) + 1
        cur = best.get(sid)
        if cur is None or it["mtime"] > cur["mtime"]:
            best[sid] = it
    kept = [it for it in items if not it.get("sid") or best.get(it["sid"]) is it]
    return kept, {sid: n for sid, n in copies.items() if n > 1}

# ---- search cache: per-file searchable turn texts, keyed on (mtime_ns, size) --
_SEARCH = {"by_path": {}, "lock": threading.Lock()}
_SEARCH_KINDS = ("text", "tool_result", "thinking", "injected", "task_notification")

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
            elif k == "task_notification":
                out.append({"gi": gi, "role": role, "text": task_notification_text(v),
                            "kind": K_SYS, "label": ""})
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
    return [r for r in out if r["text"].strip()]

_WORD_RE = re.compile(r"\w+")

def _join_blob(rows):
    """Lowercased search blob for `rows`, stamping each row's [s,e) slice offsets.
    Matching then runs as blob.find/count(term, s, e) — no per-search allocations
    (a per-row text.lower() at query time churned hundreds of MB per search, which
    macOS's allocator never returned). Lowering is per row, NOT join-then-lower:
    a few Unicode chars change length when lowered, which would skew the offsets."""
    pieces = []
    off = 0
    for r in rows:
        low = r["text"].lower()
        r["s"] = off
        r["e"] = off + len(low)
        off = r["e"] + 1
        pieces.append(low)
    return "\n".join(pieces)

def _tok_hash(w):
    # stable across processes (the packed set is persisted in the disk cache) —
    # builtin hash() is randomized per process, so it can't be used here
    return int.from_bytes(hashlib.blake2b(w.encode("utf-8"), digest_size=8).digest(), "big")

def _tok_pack(blob):
    """Whole-word set of `blob` as a sorted array of 8-byte stable hashes.
    A frozenset of the word strings held ~1.3GB on 907MB of history; this is ~80MB."""
    return array("Q", sorted({_tok_hash(m.group()) for m in _WORD_RE.finditer(blob)}))

def _tok_has(tokens, w):
    h = _tok_hash(w)
    i = bisect.bisect_left(tokens, h)
    return i < len(tokens) and tokens[i] == h

def _rows_blob(path):
    """(rows, blob, tokens) for a session — cached. blob = all lowercased text (cheap
    substring pre-filter); tokens = its whole-word set (O(1) whole-word test in scoring)."""
    try:
        st = os.stat(path)
    except OSError:
        return [], "", array("Q")
    key = (st.st_mtime_ns, st.st_size)
    with _SEARCH["lock"]:
        hit = _SEARCH["by_path"].get(path)
        if hit is not None and hit[0] == key:
            return hit[1], hit[2], hit[3]
    rows = _rows_from_turns(classify_turns(path))
    blob = _join_blob(rows)
    tokens = _tok_pack(blob)
    with _SEARCH["lock"]:
        _SEARCH["by_path"][path] = (key, rows, blob, tokens)
    r = root_for_path(path)
    if r:
        with _DISK["lock"]:
            _DISK["dirty"].add(r)
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

def _fields_ok(active, field_terms, blob):
    for f, vals in field_terms.items():
        mask = FIELD_KIND[f]
        for val in vals:
            if not any((r["kind"] & mask) and blob.find(val, r["s"], r["e"]) != -1 for r in active):
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

def match_session(active, terms, phrases, blob="", tokens=array("Q")):
    """Return the best hit for one session: row (same-turn) → cluster (nearby turns)
    → session (anywhere). None if not all terms/phrases are present. `blob`/`tokens` (the
    file's cached lowercased text and whole-word set) are used only for cheap score counts."""
    need = terms + phrases
    if not need:
        return None
    # Pasting a distinctive sentence (unquoted) is a common way to relocate a message.
    # Splitting it into AND-of-words then jumping to the earliest turn where those words
    # happen to co-occur lands on the wrong place when the words are common (by/and/the/…).
    # So when several plain words were given without quotes, treat the whole query as an
    # implicit contiguous phrase: a turn that contains the words verbatim in order is almost
    # certainly the intended target, and we prefer it over any scattered word-cluster.
    cand = " ".join(terms) if (len(terms) >= 3 and not phrases) else ""
    # which terms appear in each turn — one pass over rows' precomputed lowercase text,
    # no big per-turn string joins (that was the hot spot on large sessions). Term
    # counts for scoring are folded into the same pass (a full blob.count() per term
    # was the next hot spot — it rescanned the whole session per term).
    gi_terms = {}
    cnt = dict.fromkeys(need, 0)
    phrase_gis = []
    for r in active:
        a, b = r["s"], r["e"]
        if cand and blob.find(cand, a, b) != -1:
            phrase_gis.append(r["gi"])
        for t in need:
            c = blob.count(t, a, b)
            if c:
                gi_terms.setdefault(r["gi"], set()).add(t)
                cnt[t] += c
    ntot = len(need)
    ww = [cnt[t] for t in terms]
    all_word = bool(terms) and all(_tok_has(tokens, t) for t in terms)   # whole-word test (bisect)
    if phrase_gis:
        return {"kind": "row", "gis": sorted(set(phrase_gis)), "ww": ww,
                "all_word": all_word, "span": 0, "phrase": True}
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
    _load_disk_cache(root, rows=True)
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
        fields_ok = (not field_terms) or (all(v in blob for vs in field_terms.values() for v in vs)
                                           and _fields_ok(active, field_terms, blob))
        hit = match_session(active, terms, phrases, blob, tokens) if (fields_ok and need) else None
        field_only = fields_ok and bool(field_terms) and not need
        if not hit and not field_only and not meta_hit:
            continue
        by_gi = {}
        for r in active:
            by_gi.setdefault(r["gi"], []).append(r)
        hit_gis = hit["gis"][:5] if hit else (
            [r["gi"] for r in active if any(blob.find(v, r["s"], r["e"]) != -1 for v in fvals)][:5] if field_only else [])
        snips = []
        for gi in hit_gis:
            rs = by_gi.get(gi, [])
            row = next((r for r in rs if any(blob.find(t, r["s"], r["e"]) != -1 for t in snip_terms)), rs[0] if rs else None)
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
    seen = set()   # backup copies of a session in another root would double up
    out = []
    for m in merged:
        sid = m.get("sid") or ""
        if sid and sid in seen:
            continue
        seen.add(sid)
        out.append(m)
    return out[:max(1, min(int(limit or 30), 100))]

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

def session_api(path=None, sid=None, limit=400, full=False):
    """Full session content (meta + turns as plain text) for an agent to read.
    full=True lifts the turn-count and per-turn text caps (CLI --full)."""
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
    for gi, t in enumerate(data["turns"] if full else data["turns"][:max(1, min(int(limit or 400), 2000))]):
        parts = []
        for k, v in t["segs"]:
            if k == "channel":
                pc = parse_channel(v)
                parts.append(pc[1] if pc else v)
            elif k == "tool_use":
                parts.append(_tool_use_search_text(v))
            elif k in ("text", "thinking", "tool_result", "injected"):
                parts.append(v)
            elif k == "task_notification":
                parts.append(task_notification_text(v))
        text = " ".join(parts).strip()
        if text:
            turns.append({"turn": gi, "role": t["role"], "text": text if full else text[:4000]})
    prov = provider_of(path)
    real_sid = ({"codex": _codex_sid, "agy": _agy_sid, "gemini": _gemini_sid}.get(prov, lambda p: os.path.basename(p)[:-6]))(path)
    return {"sid": real_sid, "provider": prov, "title": m["title"], "workspace": m.get("cwd", ""),
            "counts": m["n"], "tokens": m.get("tok"), "models": m.get("models"),
            "path": path, "turns": turns}

def roots_api():
    return [{"path": r, "label": short_path(r), "provider":
             ("codex" if is_codex_root(r) else "agy" if is_agy_root(r) else "gemini" if is_gemini_root(r) else "claude")} for r in ROOTS]

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
            out.append(f'<span class=mdl title="{esc(m)} · {c} {esc(tr("responses"))}">{esc(sh)}<span class=mdlc> {c}</span></span>')
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
        elif kind == "task_notification":
            task = parse_task_notification(txt)
            if task:
                summary = task["summary"] or tr("Background task completed")
                status = f' <span class="tk-sum">· {esc(task["status"])}</span>' if task["status"] else ""
                parts.append(f'<details class="fold tasknote" open><summary>🤖 <b>{esc(summary)}</b>{status}</summary>'
                             f'<div class="seg md">{md_html(task["result"], q)}</div></details>')
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
<script>/* before first paint: ?welcome=1 → show the install modal from the very first frame */
try{if(new URLSearchParams(location.search).get('welcome')==='1'&&!(window.matchMedia&&(matchMedia('(display-mode: standalone)').matches||matchMedia('(display-mode: window-controls-overlay)').matches)))document.documentElement.classList.add('welcome');}catch(e){}</script>
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
header{position:sticky;top:0;z-index:9;background:radial-gradient(700px circle at 0% 21%,rgba(138,157,255,1),rgba(138,157,255,0)),radial-gradient(700px circle at 84% 86%,rgba(105,245,247,.88),rgba(105,245,247,0)),linear-gradient(18deg,#0084ff 0%,#1061b7 39%,#b0ff29 100%);color:#fff;padding:11px 18px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center}
/* Installed-app window chrome (no effect in a normal browser tab) */
.titlebar{display:none}
@media(display-mode:window-controls-overlay){
  .titlebar{display:flex;align-items:center;justify-content:center;position:fixed;left:0;top:0;width:100%;height:env(titlebar-area-height,33px);z-index:60;-webkit-app-region:drag;color:#fff;font-size:12px;font-weight:600;letter-spacing:.02em;text-shadow:0 1px 5px rgba(8,25,80,.45);background:radial-gradient(700px circle at 0% 21%,rgba(138,157,255,1),rgba(138,157,255,0)),radial-gradient(700px circle at 84% 86%,rgba(105,245,247,.88),rgba(105,245,247,0)),linear-gradient(18deg,#0084ff 0%,#1061b7 39%,#b0ff29 100%)}
  body{padding-top:env(titlebar-area-height,33px)}
  header{top:env(titlebar-area-height,33px)}
}
header a.home{color:#fff;text-decoration:none;font-weight:700;font-size:15px;white-space:nowrap}
header form{margin:0;display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;gap:7px;min-width:0}
header input[type=search]{min-width:50px;padding:7px 12px;border:0;border-radius:8px;font-size:14px}
header select,header button{padding:7px 11px;border:0;border-radius:8px;font-size:13px;cursor:pointer}
header select{flex:0 1 auto;min-width:74px;max-width:200px}
header button{background:#fff;color:#0d4ea6;font-weight:600}
header .advbtn{background:rgba(255,255,255,.18);color:#fff;font-weight:500;border:1px solid rgba(255,255,255,.34);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px)}
header a.home{text-shadow:0 1px 6px rgba(8,25,80,.4)}
.langsw{color:#fff;font-size:12px;white-space:nowrap;opacity:.95;text-shadow:0 1px 5px rgba(8,25,80,.4)}
.langsw a{color:#fff;text-decoration:none;padding:0 2px;opacity:.85}
.langsw a:hover{text-decoration:underline}
.langsw b{padding:0 2px}
.verbadge{color:#fff;font-size:11px;opacity:.7;text-decoration:none;white-space:nowrap;text-shadow:0 1px 5px rgba(8,25,80,.4)}
.verbadge:hover{opacity:1;text-decoration:underline}
.header-tools{display:flex;align-items:center;gap:8px;white-space:nowrap}
@media(max-width:760px){
  header{grid-template-columns:minmax(0,1fr) auto}
  header form{grid-column:1/-1;grid-row:2}
}
@media(max-width:520px){
  header{padding-inline:12px}
  header form{grid-template-columns:minmax(0,1fr) auto auto}
  header input[type=search]{grid-column:1/-1}
}
/* update notice bar (JS-inserted at very top when a newer release exists) */
.updbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:8px 16px;font-size:13px;background:linear-gradient(90deg,#eef4ff,#e7fbf3);color:#12203a;border-bottom:1px solid rgba(0,0,0,.09)}
@media(prefers-color-scheme:dark){.updbar{background:linear-gradient(90deg,#182234,#15302a);color:#e7e9ec;border-bottom-color:rgba(255,255,255,.08)}}
.updtxt{flex:1;min-width:190px}.updcur{opacity:.6}
.updbtn{background:#1061b7;color:#fff;text-decoration:none;padding:5px 12px;border-radius:7px;font-weight:600;white-space:nowrap}
.updcmd{background:rgba(0,0,0,.06);padding:4px 9px;border-radius:6px;cursor:pointer;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}
@media(prefers-color-scheme:dark){.updcmd{background:rgba(255,255,255,.1)}}
.updnotes{color:#1061b7;text-decoration:none;white-space:nowrap}
@media(prefers-color-scheme:dark){.updnotes{color:#7fb0ff}}
.updx{background:none;border:0;font-size:15px;cursor:pointer;color:inherit;opacity:.55;padding:2px 6px;line-height:1}
.updx:hover{opacity:1}
.modal-ov{display:none;position:fixed;inset:0;z-index:50;overflow:hidden;color:#fff;align-items:center;justify-content:center;padding:30px 20px;background:
radial-gradient(1600px 1100px at 6% -18%,rgba(255,96,210,.55),rgba(255,96,210,0) 64%),
radial-gradient(1700px 1200px at 110% 115%,rgba(56,224,255,.55),rgba(56,224,255,0) 64%),
radial-gradient(1400px 950px at 102% -12%,rgba(255,150,80,.48),rgba(255,150,80,0) 64%),
radial-gradient(1500px 1050px at -12% 112%,rgba(150,110,255,.6),rgba(150,110,255,0) 65%),
radial-gradient(1100px 750px at 46% -22%,rgba(124,58,237,.4),rgba(124,58,237,0) 62%),
radial-gradient(1100px 700px at 58% 122%,rgba(110,255,200,.25),rgba(110,255,200,0) 62%),
linear-gradient(158deg,#4667ec 0%,#2b4fd8 46%,#0d8ec6 100%)}
.modal-ov.open{display:flex}
/* ?welcome=1 — modal visible from the very first frame; hide the app until it's parsed
   (the modal sits at the end of the streamed HTML, so the app could paint first) */
html.welcome body{visibility:hidden}
html.welcome #installmodal{display:flex;visibility:visible}
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
.adv{grid-column:1/-1;display:none;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 2px 2px}
.adv.open{display:flex}
.adv .advlbl{color:#fff;font-size:12px;opacity:.85}
.adv select,.adv input{padding:6px 9px;border:0;border-radius:7px;font-size:13px;min-width:0;max-width:100%}
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
.addroot a.pickbtn{padding:5px 11px;border-radius:14px;background:#e9edf2;color:#444;font-size:12px;text-decoration:none;border:1px solid #dfe3e8}
@media(prefers-color-scheme:dark){.addroot a.pickbtn{background:#1b1e24;color:#cfd4db;border-color:#3a3f47}}
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
.chip-f .chipkey{background:rgba(0,0,0,.09);border-radius:4px;padding:0 4px;font-size:10px;font-family:ui-monospace,Menlo,monospace}
.chip-f.active .chipkey{background:rgba(255,255,255,.28)}
@media(prefers-color-scheme:dark){.chip-f .chipkey{background:rgba(255,255,255,.14)}}
.chip-f.active{background:#1f6feb;color:#fff;border-color:#1f6feb}
.chip-f .cnt{opacity:.6;margin-left:3px}
@media(prefers-color-scheme:dark){.chip-f{background:#1b1e24;color:#cfd4db;border-color:#3a3f47}}
.digest{background:#f7f9fc;border:1px solid #dbe3ef}
@media(prefers-color-scheme:dark){.digest{background:#171b22;border-color:#283041}}
.digest b{color:#1f6feb}
.loopchip{display:inline-block;background:#fff3cd;color:#8a6d00;border:1px solid #ffe08a;border-radius:12px;padding:1px 9px;font-size:11.5px;font-weight:600;white-space:nowrap}
@media(prefers-color-scheme:dark){.loopchip{background:#3a3115;color:#f0d68a;border-color:#5c4d1c}}
.stabwrap{overflow-x:auto;margin-top:8px}
table.stab{border-collapse:collapse;width:100%;font-size:12.5px}
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
.msg{margin:12px 0;border:1px solid #e4e7eb;border-radius:11px;overflow:hidden;scroll-margin-top:64px;contain:layout paint style}
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
.provbadge.agy{background:#e0f2fe;color:#0369a1}
@media(prefers-color-scheme:dark){.provbadge.agy{background:#0c4a6e;color:#7dd3fc}}
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
.codectx{padding:4px 12px;font-size:11.5px;color:#8a8f98;background:#fafbfc;border-bottom:1px solid #eef1f4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media(prefers-color-scheme:dark){.codectx{background:#191c22;border-color:#23262d}}
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
  <div class=header-tools>
    <button type=button id=copyurl class=advbtn title="%%COPYURLTITLE%%">🔗</button>
    <button type=button id=installbtn class=advbtn style="display:none" title="%%INSTALLTITLE%%">%%INSTALLLBL%%</button>
    %%LANGSW%%
    %%VERBADGE%%
  </div>
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
  // arrived from a session via u (data-list#sid) → pre-select that session's row in the list
  if(!inSession&&location.hash.length>1){var _fs=decodeURIComponent(location.hash.slice(1)),_a=rrows(),_k;
    for(_k=0;_k<_a.length;_k++){if(_a[_k].getAttribute('data-sid')===_fs){rcur=_k;rprev=_a[_k];
      _a[_k].classList.add('rowfocus');_a[_k].scrollIntoView({block:'center'});break;}}}
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
    if(C==='KeyM'){e.preventDefault();var mc=document.querySelector('.chip-f[data-cat="you"]');if(mc)mc.click();return;}
    if(C.indexOf('Digit')===0){var dn=+C.slice(5);                               // 0=All, 1..9 toggle a filter chip
      if(dn===0){var ca=document.querySelector('.chip-f[data-cat="*"]');if(ca){e.preventDefault();ca.click();}return;}
      var cch=document.querySelectorAll('.chip-f[data-cat]:not([data-cat="*"])');
      if(cch[dn-1]){e.preventDefault();cch[dn-1].click();}return;}
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
  function closeInstall(){if(mov)mov.classList.remove('open');document.documentElement.classList.remove('welcome');}
  // live re-check (display-mode can flip if Chrome reparents this tab into the app window)
  var dmMQ=window.matchMedia('(display-mode: standalone),(display-mode: window-controls-overlay),(display-mode: minimal-ui),(display-mode: fullscreen)');
  function liveStandalone(){return dmMQ.matches||navigator.standalone===true;}
  // after a successful install in a BROWSER tab: keep the opaque full-screen overlay up so
  // the app is never revealed here (it opens in its own PWA window); swap to a done message.
  function showInstalledMsg(){
    if(liveStandalone()){closeInstall();return;}   // we ARE the app window → show the app
    var main=document.getElementById('installmain'), done=document.getElementById('installdone');
    if(main)main.style.display='none';
    if(done)done.style.display='';
    if(mov)mov.classList.add('open');
  }
  // if Chrome "Open in app" reparents this very tab into the app window, reveal the app
  try{dmMQ.addEventListener('change',function(){if(liveStandalone())closeInstall();});}catch(_){}
  var iclose=document.getElementById('installclose');
  if(iclose)iclose.addEventListener('click',function(){window.close();});   // works: script-adjacent tab
  if(ibtn)ibtn.addEventListener('click',openInstall);
  // No visible dismiss — only "Confirm" (or ESC as an escape hatch). Feels like a finish-setup step.
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&mov&&mov.classList.contains('open'))closeInstall();});
  var inow=document.getElementById('installnow');
  if(inow)inow.addEventListener('click',function(){
    if(deferredPrompt){
      var dp=deferredPrompt;deferredPrompt=null;dp.prompt();
      // keep our full-screen overlay behind the native prompt until the user chooses.
      // accepted → keep it up as a "done, close this tab" screen (never reveal the app in
      // this browser tab); dismissed → drop it so they can use the app here in the browser.
      if(dp.userChoice&&dp.userChoice.then){
        dp.userChoice.then(function(res){
          if(res&&res.outcome==='accepted'){mark();if(ibtn)ibtn.style.display='none';showInstalledMsg();}
          else{closeInstall();}
        });
      }
    }
    else{var h=document.getElementById('installhow');if(h)h.style.display='';}
  });
  // ?welcome=1 — the macOS app launched us with no Chrome-app installed: re-greet with the modal.
  var wantWelcome=false;
  try{wantWelcome=new URLSearchParams(location.search).get('welcome')==='1';
      if(wantWelcome&&!standalone){localStorage.removeItem('aiss:installed');localStorage.removeItem('aiss:installtip');}}catch(_){}
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferredPrompt=e;
    // the browser firing this means the app is NOT installed — drop a stale "installed" flag
    try{if(!standalone)localStorage.removeItem('aiss:installed');}catch(_){}
    if(installed()){return;}                         // already installed → no button, no auto-modal
    if(ibtn)ibtn.style.display='';                    // offer manual install (button) on any page…
    // …but only auto-pop the big modal on the home page — never on a deep permalink/session link.
    try{if(location.pathname==='/'&&(wantWelcome||!localStorage.getItem('aiss:installtip'))){localStorage.setItem('aiss:installtip','1');openInstall();}}catch(_){}
  });
  window.addEventListener('appinstalled',function(){mark();if(ibtn)ibtn.style.display='none';showInstalledMsg();});
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
  // ---- update notice: async, unobtrusive; server throttles the real GitHub hit to 1/day ----
  function updDismissed(){try{return localStorage.getItem('aiss:updok');}catch(_){return null;}}
  fetch('/api/update').then(function(r){return r.json();}).then(function(d){
    if(!d||!d.newer||!d.latest||updDismissed()===d.latest)return;
    var bar=document.createElement('div');bar.className='updbar';
    var act = d.frozen
      ? '<a class=updbtn href="'+d.url+'" target=_blank rel=noopener>\u2b07\ufe0f %%UPD_DL%%</a>'
      : '<code class=updcmd title="%%UPD_COPY%%">pipx upgrade ai-session-search</code>';
    bar.innerHTML='<span class=updtxt>\u2b06\ufe0f ai-session-search <b>v'+d.latest+'</b> %%UPD_AVAIL%%'
      +' <span class=updcur>(%%UPD_ON%% v'+d.current+')</span></span>'+act
      +'<a class=updnotes href="'+d.url+'" target=_blank rel=noopener>%%UPD_WHATS%%</a>'
      +'<button type=button class=updx title="%%UPD_DISMISS%%">\u2715</button>';
    document.body.insertBefore(bar,document.body.firstChild);
    var cc=bar.querySelector('.updcmd');
    if(cc)cc.addEventListener('click',function(){if(navigator.clipboard)navigator.clipboard.writeText(cc.textContent);
      var o=cc.textContent;cc.textContent='%%UPD_COPIED%%';setTimeout(function(){cc.textContent=o;},1200);});
    bar.querySelector('.updx').addEventListener('click',function(){
      try{localStorage.setItem('aiss:updok',d.latest);}catch(_){}bar.remove();});
  }).catch(function(){});
})();
</script>
</body></html>"""

SCOPES = {"all": "All", "human": "🧑 Only me", "claude": "✦ Only Claude",
          "chat": "Conversation only (no tools/system)", "code": "🧩 Code/edits", "tool": "🔧 Commands/files"}
DAY_CHOICES = {"": "All time", "7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days"}

def _roots_label(roots):
    if len(roots) >= len(ROOTS) and len(ROOTS) > 1:
        return tr("All folders")
    return " · ".join(short_path(r) for r in roots)

def shell(title, body, q="", scope="all", root=None, days="", from_="", to="", proj=""):
    sel = active_roots(root)
    rootp = root_param(sel)
    all_on = len(sel) >= len(ROOTS)
    multi = len(ROOTS) > 1
    home = ("/?root=" + urllib.parse.quote(rootp)) if (multi and rootp) else "/"
    hidden = f'<input type=hidden name=root value="{esc(rootp)}">' if (multi and rootp) else ""
    def _rootlink(param):
        # on a search page, keep the query when switching folders (re-run search there);
        # keep a selected project too — it matches across providers (proj_canon)
        if q:
            params = {"q": q, "scope": scope}
            if param:
                params["root"] = param
            for k, v in (("days", days), ("from", from_), ("to", to), ("proj", proj)):
                if v:
                    params[k] = v
            return "/search?" + urllib.parse.urlencode(params)
        parts = ["root=" + urllib.parse.quote(param)] if param else []
        if proj:
            parts.append("proj=" + urllib.parse.quote(proj))
        return ("/?" + "&".join(parts)) if parts else "/"
    links = []
    if multi:
        links.append(f'<span class=rootitem><a class="{"on" if all_on else ""}" href="{_rootlink("")}" '
                     f'title="{esc(tr("all folders"))}">🗂 {tr("All")}</a></span>')
    for r in ROOTS:
        # toggle semantics, like the filter chips: from "All" a click drills down to
        # one folder; from a subset it adds/removes that folder (empty → back to All)
        if all_on:
            target = [r]
        elif r in sel:
            target = [x for x in sel if x != r]
        else:
            target = sel + [r]
        param = root_param([x for x in ROOTS if x in target])
        on = "on" if (r in sel and not all_on) else ""
        rm = (f'<a class=rmroot href="/delroot?path={urllib.parse.quote(r)}" title="{esc(tr("remove from list"))}">✕</a>'
              if r in SAVED_ROOTS else "")
        glyph = root_glyph(r)
        links.append(f'<span class=rootitem><a class="{on}" href="{_rootlink(param)}">'
                     f'{glyph}{esc(short_path(r))}</a>{rm}</span>')
    pick = (f'<a class=pickbtn href="/pickroot" title="{esc(tr("choose a folder with Finder"))}">📂 {tr("Browse…")}</a>'
            if sys.platform == "darwin" else "")
    addform = ('<form class=addroot action="/addroot" method=get>'
               f'<input name=path placeholder="{esc(tr("Add a folder — paste a path (…/.claude/projects)"))}">'
               f'<button>{tr("➕ Add")}</button>' + pick + '</form>')
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
        '<div id=installmain>'
        f'<h2 class=modal-h>{esc(tr("Almost done!"))}</h2>'
        f'<p class=modal-sub>{esc(tr("One last step — click Confirm to finish setting up the app."))}</p>'
        '<div class=modal-ills>'
        f'<div class=modal-ill>{ill_cmdtab}<div class=modal-cap>✓ {esc(tr("Shows up in ⌘-Tab and the Dock as its own app."))}</div></div>'
        f'<div class=modal-ill>{ill_chrome}<div class=modal-cap>✓ {esc(tr("It is still Chrome inside — ⌘-F Find and your extensions keep working."))}</div></div>'
        '</div>'
        f'<div class=modal-actions><button id=installnow class=modal-primary>{esc(tr("Confirm"))}</button></div>'
        f'<p class=modal-note id=installhow style="display:none">{tr("If it does not prompt, use the Chrome ⋮ menu → “Cast, save &amp; share” → “Install page as app”.")}</p>'
        '</div>'
        # shown after a successful install so the app is NEVER revealed in this browser
        # tab — the app opens in its own PWA window; this tab is disposable.
        '<div id=installdone style="display:none">'
        f'<h2 class=modal-h>✓ {esc(tr("Installed!"))}</h2>'
        f'<p class=modal-sub>{esc(tr("The app opened in its own window. You can close this browser tab."))}</p>'
        f'<div class=modal-actions><button id=installclose class=modal-primary>{esc(tr("Close this tab"))}</button></div>'
        '</div>'
        '</div></div>')
    kbrows = [
        ("j / k", tr("down / up — session-list rows, or prev / next session")),
        ("Enter", tr("open the focused session (or its answer thread)")),
        ("n / p", tr("next / previous message of yours")),
        ("s", tr("toggle star")),
        ("u", tr("back to the session list")),
        ("m", tr("toggle: only my messages (same as chip 1)")),
        ("0 – 9", tr("toggle a filter chip (0 = All) — combine several")),
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
        "%%VERBADGE%%": (f'<a class=verbadge href="https://github.com/{REPO_SLUG}/releases" '
                         f'target=_blank rel=noopener title="{esc(tr("current version — release notes"))}">'
                         f'v{__version__}</a>'),
        "%%INSTALLLBL%%": esc(tr("⬇ Install app")),
        "%%INSTALLTITLE%%": esc(tr("install as a standalone app (own window, shows in the app switcher)")),
        "%%COPYURLTITLE%%": esc(tr("copy this page's link (handy in the installed app — no address bar)")),
        "%%UPD_AVAIL%%": esc(tr("is available")), "%%UPD_ON%%": esc(tr("on")),
        "%%UPD_DL%%": esc(tr("Download")), "%%UPD_WHATS%%": esc(tr("What's new")),
        "%%UPD_DISMISS%%": esc(tr("dismiss")), "%%UPD_COPY%%": esc(tr("click to copy")),
        "%%UPD_COPIED%%": esc(tr("copied ✓")),
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

    def do_POST(self):
        # POST /api/shutdown — replace-on-update handshake (see main()). A newer build
        # relaunched by the user asks the stale detached server to exit. Guarded by:
        # loopback-only client + loopback-only bind, and a per-instance 256-bit token
        # readable only by the same user (runtime file, 0600). Never a GET.
        u = urllib.parse.urlparse(self.path)
        if u.path != "/api/shutdown":
            return self.send_error(404)
        if not _SHUTDOWN_TOKEN or self.client_address[0] not in ("127.0.0.1", "::1"):
            return self._send_json({"error": "forbidden"}, 403)
        sent = (self.headers.get("X-Shutdown-Token") or "").strip()
        if not hmac.compare_digest(sent, _SHUTDOWN_TOKEN):
            return self._send_json({"error": "forbidden"}, 403)
        self._send_json({"ok": True, "pid": os.getpid()})
        _cleanup_runtime_file()
        threading.Thread(target=self.server.shutdown, daemon=True).start()

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
        if u.path == "/api/update":
            # "is there a newer release?" — throttled to 1 GitHub hit/day, no data sent. See check_update().
            return self._send_json(check_update())
        if u.path == "/api/status":
            # local instance identity (no network, no cache) — lets a relaunch detect a
            # stale old-version server and replace it (see main()).
            return self._send_json({"app": "ai-session-search", "version": __version__,
                                    "pid": os.getpid()})
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
                "id": "/", "start_url": "/", "scope": "/", "display": "standalone",
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
        root = g("root")            # raw param — index/search accept multi-select ("a,b" / "" = all)
        if u.path == "/":
            return self._send(self.index(g("proj"), g("sort", "date"), g("dir", ""), root, gint("off")))
        if u.path == "/search":
            return self._send(self.search(g("q"), g("scope", "all"), root,
                                          g("days", ""), g("proj", ""), g("from", ""), g("to", "")))
        if u.path == "/session":
            return self._send(self.session(g("p"), g("q"), g("filter", "all"),
                                           gint("off"), g("lim", ""), g("thread", ""), g("view", ""),
                                           g("goto", ""), g("sq", ""), g("sqtools", "")))
        if u.path == "/subagent":
            return self._send(self.subagent(g("p"), g("parent"), g("q")))
        if u.path in ("/addroot", "/delroot", "/pickroot"):
            # CSRF guard for state-changing routes: modern browsers send
            # Sec-Fetch-Site; block explicit cross-site, allow same-origin,
            # direct navigation, and header-less clients (curl).
            sfs = (self.headers.get("Sec-Fetch-Site") or "").lower()
            if sfs in ("cross-site", "same-site"):
                return self.send_error(403, "cross-site request rejected")
            if u.path == "/pickroot":
                return self.pickroot()
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

    def pickroot(self):
        # native Finder folder picker — possible because the server runs on the same Mac
        if sys.platform != "darwin":
            return self._redirect("/")
        try:
            import subprocess
            r = subprocess.run(
                ["/usr/bin/osascript", "-e",
                 f'POSIX path of (choose folder with prompt "{tr("AI Session Search — choose a projects folder (e.g. .claude/projects, or a backup of it)")}")'],
                capture_output=True, text=True, timeout=600)
            picked = (r.stdout or "").strip()
        except Exception:
            picked = ""
        if not picked:                      # cancelled (or timed out) — just go home
            return self._redirect("/")
        return self.addroot(picked)

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
    def index(self, proj_filter="", sort="date", dir_="", root=None, off=0):
        roots = active_roots(root)
        rootp = root_param(roots)
        rootlabel = _roots_label(roots)
        all_items = [it for r in roots for it in get_index(r)]
        all_items, dup_copies = dedupe_sids(all_items)
        canon = proj_canon(all_items)
        ckey = lambda p: canon.get(p, p)
        proj_cwd = {p: short_path(c) for p, c in canon.items()}
        for c in canon.values():
            proj_cwd.setdefault(c, short_path(c))
        # one chip/row per workspace (the canonical key), merging providers in 'All'
        projs = sorted({ckey(it["proj"]) for it in all_items}, key=lambda p: proj_cwd.get(p, p).lower())
        if proj_filter:
            pf = ckey(proj_filter)
            items = [it for it in all_items if it["proj"] == proj_filter or ckey(it["proj"]) == pf]
        else:
            items = list(all_items)

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
            if rootp:
                parts.append("root=" + urllib.parse.quote(rootp))
            return "/?" + "&".join(parts) if parts else "/"

        # ---- project insight ----
        def _toktip(tk):
            return (f'{tr("Input")} {tk["in"]:,} · {tr("Output")} {tk["out"]:,} · {tr("Cache write")} {tk["cw"]:,} · '
                    f'{tr("Cache read")} {tk["cr"]:,} ({tr("cache read is reused context, cheap")})')
        if proj_filter:
            st = agg_stats(items)
            label = proj_cwd.get(proj_filter, proj_filter)
            loopline = (f' · <span class=loopchip>🔁 {tr("autonomous build-loop")} {st["loop"]}</span>') if st["loop"] else ""
            hidden_root = f'<input type=hidden name=root value="{esc(rootp)}">' if rootp else ""
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
                by.setdefault(ckey(it["proj"]), []).append(it)
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
            table = (f'<div class=stabwrap><table class=stab><thead><tr><th class=sortable>{tr("Project (folder)")}</th>'
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
                     f'<td>{tot["loop"] or ""}</td></tr></tbody></table></div>')
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
            projbar.append(f'<a class="{"on" if p==ckey(proj_filter) else ""}" '
                           f'href="{q(proj=p, sort=sort, dir=dir_)}">{esc(proj_cwd.get(p, p))}</a>')
        projbar.append("</div>")
        # server-side paging: hundreds of cards at once made the landing page heavy
        IDX_PAGE = 100
        total = len(items)
        off = max(0, min(off, max(0, total - 1)))
        page_items = items[off:off + IDX_PAGE]
        rows = []
        for it in page_items:
            link = "/session?p=" + urllib.parse.quote(it["path"])
            loopchip = f' <span class=loopchip>🔁 {tr("autonomous build-loop")}</span>' if it.get("loop") else ""
            ncopy = dup_copies.get(it.get("sid") or "", 0)
            if ncopy:
                loopchip += (' <span class=chip title="' + esc(tr("this session exists in multiple folders; showing the freshest copy"))
                             + f'">⧉ {ncopy}</span>')
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
                f'<div class=meta>{prov_badge(it.get("provider", ""), root_for_path(it["path"]))} '
                f'<a class="chip chiplink" href="{q(proj=it["proj"], sort=sort, dir=dir_)}" title="{esc(tr("show this workspace only"))}">{esc(proj_label(it))}</a> '
                f'{counts_html(it["n"])}{tokbit}{mdlbit} · '
                f'{fmt_mtime(it["mtime"])} · {fmt_size(it["size"])} · '
                f'<span class=sid>id {esc(it["sid"])}</span></div>'
                + (f'<div class=preview>{esc(it["preview"])}</div>' if it["preview"] else "") + '</div>')
        if total > IDX_PAGE:
            pl = (f'<a href="{q(proj=proj_filter, sort=sort, dir=dir_, off=max(0, off - IDX_PAGE) or None)}">'
                  f'← {tr("newer")}</a>' if off > 0 else '<span></span>')
            nl = (f'<a href="{q(proj=proj_filter, sort=sort, dir=dir_, off=off + IDX_PAGE)}">{tr("older")} →</a>'
                  if off + IDX_PAGE < total else '<span></span>')
            rows.append(f'<div class="bar sessnav">{pl}'
                        f'<span class=meta>{off + 1}–{min(off + IDX_PAGE, total)} / {total}</span>{nl}</div>')
        head = (f'<p class=meta>{len(items)} {tr("sessions")} · <b>🧑 {tr("You")}</b> {tr("marks — by a verified ruleset —")} '
                f'<b>{tr("only what you actually typed")}</b> · {esc(rootlabel)}</p>'
                f'<p class=meta>{tr("Legend")}: 🧑 {tr("You")} · ✦ Claude · ⚙ {tr("Tool result")} · ⓘ {tr("System / injected")} '
                f'<span class=hint>{tr("(hover a number for its meaning; expand ❓ below for the full legend)")}</span></p>'
                + legend_html())
        if not items and not proj_filter:
            head += (f'<div class=card><b>{tr("No sessions.")}</b>'
                     f'<p class=meta>{tr("No <code>&lt;project&gt;/&lt;uuid&gt;.jsonl</code> files found under")} {esc(rootlabel)}. '
                     + tr('Make sure this is a folder where Claude Code has run at least once, or add another folder with ➕ above.') + '</p></div>')
        favbar = (f'<div class=favbar>⭐ <b>{len(_STARS)}</b> {tr("favorites")} · '
                  f'<a href="/api/stars.json" download>⬇ {tr("export")}</a> · '
                  f'<label class=favimp>⬆ {tr("import")}<input type=file id=starimport accept="application/json,.json" hidden></label>'
                  f' <span class=hint>{tr("kept on this machine; export to move to another computer")}</span></div>')
        # fixed bottom status bar — where you are (folder, and workspace when filtered)
        if proj_filter:
            crumb_root = (f'<a class=crumb href="{("/?" + urllib.parse.urlencode({"root": rootp})) if rootp else "/"}" '
                          f'title="{esc(tr("this folder"))}">📁 {esc(rootlabel)}</a>')
            crumb = (f'<div class=crumbs>{crumb_root} <span class=crumbsep>›</span> '
                     f'<span class=crumbcur>📂 {esc(proj_cwd.get(proj_filter, proj_filter))}</span></div>')
        else:
            crumb = f'<div class=crumbs><span class=crumbcur>📁 {esc(rootlabel)}</span> <span class=hint>{len(items)} {tr("sessions")}</span></div>'
        return shell(tr("AI Session Search"), crumb + head + favbar + statsblock + "".join(sortbar) + "".join(projbar) + "".join(rows), root=rootp, proj=proj_filter)

    # ---- search ----
    def search(self, q, scope, root=None, days="", proj="", from_="", to=""):
        roots = active_roots(root)
        rootp = root_param(roots)
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
                         q, scope, rootp, days, from_, to)
        t0 = time.perf_counter()
        for r_ in roots:
            _load_disk_cache(r_, rows=True)
        index = [it for r in roots for it in get_index(r)]
        canon = proj_canon(index)
        ckey = lambda p: canon.get(p, p)
        proj_cwd = {p: short_path(c) for p, c in canon.items()}
        for c in canon.values():
            proj_cwd.setdefault(c, short_path(c))
        pf = ckey(proj) if proj else ""
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
        for path in (p_ for r_ in roots for p_ in session_files(r_)):
            mt = mtimes.get(path, 0)
            if (lo is not None and mt < lo) or (hi is not None and mt >= hi):
                continue
            it = metas.get(path, {})
            if proj and it.get("proj") != proj and ckey(it.get("proj", "")) != pf:
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
            fields_ok = (not field_terms) or (all(v in blob for vs in field_terms.values() for v in vs)
                                           and _fields_ok(active, field_terms, blob))
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
                [r["gi"] for r in active if any(blob.find(v, r["s"], r["e"]) != -1 for v in fvals)][:6] if field_only else [])
            hits = []
            for gi in hit_gis:
                rs = by_gi.get(gi, [])
                row = next((r for r in rs if any(blob.find(t, r["s"], r["e"]) != -1 for t in snip_terms)), rs[0] if rs else None)
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
                if phrases or hit.get("phrase"):   # exact-phrase (quoted or implicit) is a strong intent signal
                    score += 300
            elif field_only:
                score += 500
            score += 300 * bool(fields.get("file")) + 200 * bool(fields.get("code")) + 200 * bool(fields.get("cmd"))
            results.append({"path": path, "title": titles.get(path, tr("(untitled)")),
                            "provider": it.get("provider") or provider_of(path),
                            "proj": it.get("proj") or os.path.basename(os.path.dirname(path)),
                            "n": len(hits), "score": score, "mtime": mt,
                            "all_word": bool(hit) and hit.get("all_word"),
                            "hit_kind": hit["kind"] if hit else "", "hits": hits,
                            "meta_hit": meta_hit, "sid": sid, "forked": forked, "cwd": it.get("cwd", "")})
        results.sort(key=lambda x: (x["score"], x["mtime"]), reverse=True)
        seen_sids = set()   # collapse duplicate copies across roots (backup folders)
        results = [r_ for r_ in results
                   if not r_.get("sid") or r_["sid"] not in seen_sids and not seen_sids.add(r_["sid"])]
        truncated = len(results) - RESULT_CAP
        results = results[:RESULT_CAP]
        ms = int((time.perf_counter() - t0) * 1000)

        def searchurl(**kw):
            params = {"q": q, "scope": scope}
            for k, v in (("days", days), ("from", from_), ("to", to)):
                if v:
                    params[k] = v
            if rootp:
                params["root"] = rootp
            params.update({k: v for k, v in kw.items() if v})
            return "/search?" + urllib.parse.urlencode(params)

        projbar = ""
        matched_projs = sorted({ckey(r["proj"]) for r in results} | ({pf} if proj else set()),
                               key=lambda p: proj_cwd.get(p, p).lower())
        if matched_projs and (len(matched_projs) > 1 or proj):
            chips = [f'<a class="{"on" if not proj else ""}" href="{searchurl()}">{tr("All")}</a>']
            for p in matched_projs:
                chips.append(f'<a class="{"on" if p == pf else ""}" href="{searchurl(proj=p)}">'
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
            proj_href = "/?" + urllib.parse.urlencode({"proj": r["proj"], **({"root": rootp} if rootp else {})})
            rows.append(f'<div class=card>{prov_badge(r["provider"], root_for_path(r["path"]))} '
                        f'<a class=t href="{openurl}">{hl(r["title"], hlq)}</a> '
                        f'<span class=meta>{cnt}</span>{exact}{kchip}'
                        f'<div class=meta><a class="chip chiplink" href="{proj_href}" title="{esc(tr("show this workspace only"))}">{esc(short)}</a></div>{metaline}{snips}</div>')

        keys = " ".join(f'<span class="hlkey hl{i % HL_COLORS}">{esc(t)}</span>' for i, t in enumerate(hl_terms))
        when = (f' · {esc(from_ or "…")}~{esc(to or "…")}' if (from_ or to) else
                (" · " + tr(DAY_CHOICES[days]) if days else ""))
        more = f' · <span class=hint>(+{truncated} {tr("more, refine to narrow")})</span>' if truncated > 0 else ""
        head = (f'<p class=meta>{keys} — {len(results)} {tr("sessions matched")} ({tr("by relevance")}) · {tr(SCOPES[scope])}{when} · {ms}ms{more} · '
                f'📁 {esc(_roots_label(roots))} · <span class=hint>{tr("click a snippet to jump there")}</span></p>')
        return shell(f"{tr('Search')}: {q}", head + projbar + ("".join(rows) or f"<p class=meta>{tr('No results.')}</p>"),
                     q, scope, rootp, days, from_, to, proj=proj)

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
        pbadge = prov_badge(prov, rt) + " "
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
                if a["kind"] == "edit":
                    lbl = "✏️ " + short_path(a["label"])
                else:
                    lbl = ("🧑 " if a.get("who") == "you" else "✦ ") + "``` " + a["label"]
                ctx = a.get("ctx", "")
                ctxrow = (f'<div class=codectx title="{esc(tr("the request this came from"))}">💬 '
                          f'{esc(ctx[:110])}{"…" if len(ctx) > 110 else ""}</div>' if ctx else "")
                body.append(
                    f'<div class=codeart><div class=codehead><span><a href="{url(q=q)}#t{a["gi"]}" '
                    f'style="text-decoration:none">{esc(lbl)}</a> <span class=time>{fmt_ts_short(a["ts"])}</span></span>'
                    f'<button class=copy>{tr("Copy")}</button></div>{ctxrow}<pre class=code>{esc(a["body"])}</pre></div>')
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
                   f'<a class=backfull href="{url(goto=gi, q=q)}">← {tr("back to the conversation")}</a>'
                   f'<span class=meta>🧑 {tr("question → answer thread")} ({nxt-gi}) · <kbd>Esc</kbd> {tr("back")} · {tr("server")} {ms}ms<span id=perf></span></span></div>')
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
        showall = f'<a href="{url(q=q, lim=lim_raw)}">← {tr("Show all")}</a>' if filt == "human" else ""
        toggles = ('<div class=bar>' + showall
                   + f'<a href="{url(view="code", q=q)}">🧩 {tr("Code only")}</a>'
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
        # every filter is a (combinable) chip; "Code only" is separate because it's a reprocessed view, not a filter
        CHIP_LBL = {"you": "🧑 My messages", "agent": "✦ Agent", "error": "⚠️ Errors", "edit": "✏️ Edits",
                    "memory": "🧠 Memory", "command": "❯ Commands", "commit": "⎇ Commits", "test": "🧪 Tests", "url": "🔗 URL"}
        chips = [f'<div class=chips><button class=chip-f data-cat="*"><kbd class=chipkey>0</kbd> {tr("All")}</button>']
        knum = 0
        for c, lbl in CHIP_LBL.items():
            if cc[c]:
                knum += 1
                key = f'<kbd class=chipkey>{knum}</kbd> ' if knum <= 9 else ''
                chips.append(f'<button class=chip-f data-cat="{c}">{key}{tr(lbl)}<span class=cnt>{cc[c]}</span></button>')
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
                   f' data-list="{esc((("/?" + urllib.parse.urlencode({"proj": proj, "root": rt})) if proj else "/") + "#" + sid)}"'
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
    """Pre-parse index + search rows so the first request isn't cold. Best-effort.
    Persists the result so the NEXT start skips the parse entirely."""
    try:
        _load_disk_cache(root, rows=True)
        get_index(root)
        for p in session_files(root):
            _rows_blob(p)
        with _DISK["lock"]:
            dirty = root in _DISK["dirty"]
        if dirty:
            _save_disk_cache(root)
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
         "provider": {"type": "string", "enum": ["claude", "codex", "gemini", "agy"]},
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
                          None if p else args.get, 2000, full=args.full)
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
            for t in (res["turns"] if args.full else res["turns"][:lim]):
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

def _chrome_pwa(port):
    """Path of the installed Chrome-app (PWA) bundle pointing at our port, else None."""
    if sys.platform != "darwin":
        return None
    for app in glob.glob(os.path.expanduser("~/Applications/Chrome Apps.localized/*.app")):
        pl = os.path.join(app, "Contents", "Info.plist")
        try:
            import subprocess
            out = subprocess.run(["/usr/bin/plutil", "-extract", "CrAppModeShortcutURL", "raw", pl],
                                 capture_output=True, text=True, timeout=3).stdout
            if f"127.0.0.1:{port}" in out:
                return app
            if not out.strip():  # key missing — scan the plist itself
                with open(pl, "rb") as f:
                    if f"127.0.0.1:{port}".encode() in f.read():
                        return app
        except Exception:
            continue
    return None

def _open_ui(url, port):
    """--open target. macOS: prefer the installed Chrome app (own window, Cmd-Tab icon).
    Without one, the frozen .app opens the browser on /?welcome=1 so the install
    modal (welcome page) greets first instead of the bare app."""
    pwa = _chrome_pwa(port)
    if pwa:
        try:
            import subprocess
            subprocess.Popen(["/usr/bin/open", pwa])
            return
        except Exception:
            pass
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        url += "/?welcome=1"
    webbrowser.open(url)

def _port_file():
    """Well-known file where a running server records its port (single-instance reuse)."""
    import tempfile
    uid = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
    return os.path.join(tempfile.gettempdir(), f"ai-session-search{uid}.port")

def _runtime_file():
    """Per-user runtime record of the running server: port, pid, version, shutdown token.
    0600 — the token must be readable only by the same user."""
    return _port_file() + ".json"

# Ports we try, in order, when this machine hasn't committed to one yet. A committed
# port (below) always wins over this scan.
PORT_CANDIDATES = list(range(DEFAULT_PORT, DEFAULT_PORT + 16))   # 8777..8792

def _committed_port_file():
    """Persistent (survives reboot, unlike the /tmp port file) record of THE port this
    machine settled on. The installed Chrome PWA is keyed by origin (host:port), so once
    we've bound a port we must keep using it forever — otherwise the PWA breaks and Chrome
    mints a duplicate app. See _choose_port()."""
    return os.path.join(CONFIG_DIR, "port")

def _read_committed_port():
    try:
        with open(_committed_port_file(), encoding="utf-8") as f:
            p = int(f.read().strip())
        return p if 1 <= p <= 65535 else None
    except Exception:
        return None

def _commit_port(port):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = _committed_port_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(port))
        os.replace(tmp, _committed_port_file())
    except Exception:
        pass

def _port_free(port, host="127.0.0.1"):
    """True if `port` can be bound right now (nobody is listening)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()

_SHUTDOWN_TOKEN = None   # set at server start when bound to loopback; None disables /api/shutdown

def _write_runtime_file(port):
    global _SHUTDOWN_TOKEN
    import secrets
    _SHUTDOWN_TOKEN = secrets.token_hex(32)
    path = _runtime_file()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"port": port, "pid": os.getpid(), "version": __version__,
                       "token": _SHUTDOWN_TOKEN}, f)
    except Exception:
        pass

def _cleanup_runtime_file():
    # only remove records THIS process wrote — a replacement server may already
    # have written its own by the time the old one finishes exiting
    try:
        with open(_runtime_file(), encoding="utf-8") as f:
            if json.load(f).get("pid") != os.getpid():
                return
    except Exception:
        return
    for p in (_runtime_file(), _port_file()):
        try:
            os.remove(p)
        except OSError:
            pass

def _running_server(ports, host="127.0.0.1"):
    """(port, version|None) of the first port where one of our servers answers, else
    (None, None). Identity via the cheap /api/status (also yields the version); servers
    older than 4.0.11 lack it, so fall back to /api/roots — that one lists roots on
    disk, hence the longer timeout."""
    for port in ports:
        if not port:
            continue
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=2) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
                if d.get("app") == "ai-session-search":
                    return port, d.get("version")
        except Exception:
            pass
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/api/roots", timeout=3) as r:
                if r.status == 200 and "roots" in json.loads(r.read().decode("utf-8", "replace")):
                    return port, None
        except Exception:
            pass
    return None, None

def _replace_stale_server(port, host="127.0.0.1"):
    """Free `port` when it's held by one of OUR own (stale, different-version) servers.
    True if the port was released.

    Two stages, because the on-disk shutdown token is a single file that any of our
    servers may overwrite — when an ephemeral-port server clobbers it, the committed-port
    server's token is lost and the graceful handshake 403s. So we ALSO take the live PID
    from /api/status (always accurate) and, if graceful shutdown doesn't free the port,
    kill that PID. We only ever touch a process that /api/status confirms is ours, on
    loopback, owned by this user — killing our own orphan is exactly what the user would
    do by hand, and it's what keeps the committed port (hence the single PWA) stable."""
    import socket
    def freed():
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return False
        except OSError:
            return True
    # live identity + PID (accurate even when the on-disk token file is stale)
    pid = None
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=2) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if d.get("app") != "ai-session-search":
            return False   # NOT ours — never kill a foreign app
        pid = d.get("pid")
    except Exception:
        # no /api/status = a pre-4.0.11 server of ours (or unreachable); fall through to
        # the token path, which is all those old versions understand.
        pass
    # 1) graceful: authenticated shutdown, if our runtime file still holds this port's token
    try:
        with open(_runtime_file(), encoding="utf-8") as f:
            rt = json.load(f)
        token = rt.get("token", "") if rt.get("port") == port else ""
    except Exception:
        token = ""
    if token:
        try:
            req = urllib.request.Request(f"http://{host}:{port}/api/shutdown", data=b"",
                                         headers={"X-Shutdown-Token": token}, method="POST")
            urllib.request.urlopen(req, timeout=3).read()
        except Exception:
            pass
        for _ in range(20):   # ~2s for a graceful exit
            if freed():
                return True
            time.sleep(0.1)
    # 2) fallback: kill our own server by the PID /api/status reported
    if pid and hasattr(os, "kill"):
        import signal
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except OSError:
                break   # already gone
            for _ in range(20):
                if freed():
                    return True
                time.sleep(0.1)
    return freed()

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ai-session-search",
        description="Read-only local web viewer for Claude Code session transcripts.")
    ap.add_argument("root", nargs="?", default=None,
                    help="projects dir to browse (default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects)")
    ap.add_argument("--port", type=int, default=None, help=f"port to listen on (default {DEFAULT_PORT})")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1; changing this exposes your transcripts to the network)")
    ap.add_argument("--roots", default="", metavar="DIR[,DIR...]",
                    help="extra project roots to offer in the in-app folder switcher")
    ap.add_argument("--open", action="store_true", help="open the browser after starting")
    ap.add_argument("--demo", action="store_true",
                    help="browse a bundled synthetic dataset (Claude + Codex + Gemini) instead of "
                         "your own — great for a first look; implies --open")
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
    ap.add_argument("--full", action="store_true",
                    help="with --get: print the whole session, lifting the turn-count and per-turn text caps")
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

    # --demo: browse the bundled synthetic dataset (all three providers), never your own.
    if args.demo:
        demo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo")
        if not os.path.isdir(os.path.join(demo, "claude")):
            ap.exit(2, "demo dataset not found (expected packaged demo/ dir)\n")
        args.root = os.path.join(demo, "claude")
        args.roots = ",".join(d for d in (os.path.join(demo, ".codex", "sessions"),
                                          os.path.join(demo, ".gemini", "tmp")) if os.path.isdir(d))
        args.open = True

    # Validate the EXPLICITLY requested root before configure() — otherwise a
    # typo'd path silently falls back to the default root and serves that.
    if args.root and not os.path.isdir(os.path.expanduser(args.root)):
        ap.exit(2, f"projects dir not found: {args.root}\n")
    extra = [p for p in args.roots.split(",") if p]
    configure(args.root, extra, exclusive=bool(args.demo))
    if not os.path.isdir(ROOT):
        ap.exit(2, f"projects dir not found: {ROOT}\n")
    if args.mcp:
        # stdio MCP mode: no web server, no banner (stdout is the JSON-RPC channel)
        return run_mcp()
    if args.search is not None or args.get is not None or args.sessions:
        return _run_cli(args)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"  \u26a0\ufe0f  Binding {args.host}: your transcripts are exposed on the network. Use only on a trusted network.")

    # The app-launch path (double-clicked .app: --open, no explicit port/root) pins a
    # STABLE per-machine port. The installed Chrome PWA is keyed by origin (host:port);
    # a changing port makes Chrome mint a duplicate app and orphans the old window, so we
    # commit one port to CONFIG_DIR and reuse it forever \u2014 even after the port that forced
    # our hand (a foreign app on 8777) later frees up.
    app_launch = args.open and args.port is None and args.root is None
    committed = _read_committed_port() if app_launch else None
    if app_launch:
        try:
            saved = int(open(_port_file()).read().strip())
        except Exception:
            saved = None
        # look for one of OUR servers on the committed port first, then the /tmp hint,
        # then the deterministic candidate range \u2014 never a random port.
        probe, seen = [], set()
        for p in [committed, saved] + PORT_CANDIDATES:
            if p and p not in seen:
                seen.add(p); probe.append(p)
        running, running_ver = _running_server(probe, args.host)
        if running:
            if running_ver == __version__:
                url = f"http://{args.host}:{running}"
                print(f"\n  AI Session Search already running \u2192 {url}")
                _open_ui(url, running)
                return 0
            print(f"  \u267b\ufe0f  Replacing a running older version on port {running} \u2026")
            if _replace_stale_server(running, args.host) and committed is None:
                committed = running   # adopt the freed port as ours

    if args.port is not None:
        port = args.port
    elif app_launch:
        # committed port wins; first run picks the lowest free candidate and commits it.
        port = committed or next((p for p in PORT_CANDIDATES if _port_free(p, args.host)),
                                 DEFAULT_PORT)
    else:
        port = DEFAULT_PORT
    try:
        srv = make_server(args.host, port)
    except OSError:
        # Our committed/target port is held by a FOREIGN app (we never kill those \u2014 only
        # servers that answer /api/status as ours). Fall back to an ephemeral port for this
        # session, but do NOT commit it, so we return to the stable port once the foreign
        # app is gone. (This is the one case a PWA can still be transiently wrong.)
        print(f"  \u26a0\ufe0f  Port {port} is in use by another app \u2014 using a temporary port this time.")
        srv = make_server(args.host, 0)
    if app_launch and committed is None and srv.server_address[1] in PORT_CANDIDATES:
        _commit_port(srv.server_address[1])   # remember this machine's port for next launch
    try:
        with open(_port_file(), "w") as f:
            f.write(str(srv.server_address[1]))
    except Exception:
        pass
    if args.host in ("127.0.0.1", "localhost", "::1"):
        _write_runtime_file(srv.server_address[1])   # enables the replace-on-update handshake
    url = f"http://{args.host}:{srv.server_address[1]}"
    print(f"\n  AI Session Search v{__version__} → {url}")
    print(f"  Browsing: {ROOT}" + (f"  (+{len(ROOTS)-1} more, switchable)" if len(ROOTS) > 1 else ""))
    print("  (close this window or press Ctrl-C to stop)\n")
    if args.open:
        threading.Timer(0.8, _open_ui, [url, srv.server_address[1]]).start()
    # warm the index + search cache for every root in the background, so the FIRST
    # search is fast too (even after switching folders). Also prime the (throttled,
    # opt-out) update check so the notice, if any, is instant on first paint.
    threading.Thread(target=lambda: [_warm_cache(r) for r in ROOTS], daemon=True).start()
    threading.Thread(target=_refresh_slow_roots, daemon=True).start()
    if not update_disabled():
        threading.Thread(target=check_update, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup_runtime_file()
        _save_dirty_caches()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
