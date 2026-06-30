#!/usr/bin/env python3
"""Claude Code transcript viewer — stdlib only, read-only.

Correctly attributes WHO said what (audited + adversarially verified ruleset for the
Claude Code JSONL schema). Only genuine human-typed text is labelled "나" (You); tool
results, reasoning, tool calls, system/IDE injections, slash-command output,
task-notifications, autonomous build-loop prompts, and subagent threads are each their
own category, folded by default.

Features: session index (titles, project filter, sort), full-text search (all / my-only),
per-message timestamps, "my messages only" filter, answer-thread links, subagent thread
expansion, j/k keyboard nav + "/" search focus, configurable page size + render timing,
event/error chips, structure minimap, per-session extracted-fact digest, code/diff
extraction with copy.

Usage:
    python3 claude-viewer.py [PROJECTS_DIR] [--port 8777]
Defaults to ~/Downloads/.claude/projects.
"""
import os, sys, json, html, glob, re, time, urllib.parse, datetime, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- config -----------------------------------------------------------------
_pos = [a for a in sys.argv[1:] if not a.startswith("--")]
_opt = {}
for a in sys.argv[1:]:
    if a.startswith("--"):
        k, _, v = a.partition("=")
        _opt[k] = v or True
ROOT = os.path.abspath(os.path.expanduser(_pos[0])) if _pos else os.path.expanduser("~/Downloads/.claude/projects")
PORT = int(_opt.get("--port", 8777))

CONFIG_DIR = os.path.expanduser("~/.config/claude-viewer")
ROOTS_FILE = os.path.join(CONFIG_DIR, "roots.txt")
_ROOTLOCK = threading.Lock()

def _discover_roots(primary):
    """Auto-discovered roots: CLI primary, the two standard locations, and --roots."""
    cands = [primary, os.path.expanduser("~/.claude/projects"), os.path.expanduser("~/Downloads/.claude/projects")]
    extra = _opt.get("--roots")
    if isinstance(extra, str):
        cands += [p for p in extra.split(",") if p]
    seen = []
    for c in cands:
        c = os.path.abspath(os.path.expanduser(c))
        if os.path.isdir(c) and c not in seen:
            seen.append(c)
    return seen or [os.path.abspath(primary)]

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

DEFAULT_ROOTS = _discover_roots(ROOT)
SAVED_ROOTS = [p for p in _load_saved() if p not in DEFAULT_ROOTS]
ROOTS = list(DEFAULT_ROOTS)
for _p in SAVED_ROOTS:
    if _p not in ROOTS:
        ROOTS.append(_p)
ROOT = ROOT if ROOT in ROOTS else ROOTS[0]   # default active root

def root_for_path(p):
    """Which allowed root contains p (so session links work regardless of active root)."""
    ap = os.path.abspath(p or "")
    for r in ROOTS:
        try:
            if os.path.commonpath([ap, r]) == r:
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
                    segs.append(("injected", f"모델 전환 {b.get('from',{}).get('model','?')} → {b.get('to',{}).get('model','?')}"))
        elif isinstance(content, str) and content.strip():
            segs.append(("text", content))
        return ("assistant", segs) if segs else None

    if t == "user":
        you_role = "orchestrator" if sub else "you"
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
                    human.append(("text", "🖼️ [붙여넣은 이미지]"))
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
            if name == "Bash":
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
    out = []
    for o in iter_lines(path):
        r = classify_line(o, sub)
        if r:
            out.append({"role": r[0], "segs": r[1], "ts": o.get("timestamp", ""),
                        "tags": turn_tags(o, r[0], r[1])})
    return out

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
    m = re.search(r"/workflows/(wf_[^/]+)/", path)
    return {"path": path, "agentId": aid, "wf": m.group(1) if m else "",
            "n": len(turns), "brief": (brief or "(지시 없음)")[:120]}

# ---- digest + code extraction ----------------------------------------------
def _toolinput(txt):
    name, _, rest = txt.partition("\n")
    try:
        return name.strip(), json.loads(rest)
    except Exception:
        return name.strip(), {}

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
                elif name == "Bash":
                    cmds += 1
                    cmd = inp.get("command", "")
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
    ai_title = custom_title = last_prompt = first_human = ""
    n = {"you": 0, "assistant": 0, "tool-result": 0, "system": 0, "subagent": 0}
    last_ts = cwd = branch = ""
    loop = False
    for o in iter_lines(path):
        t = o.get("type")
        if t == "ai-title":
            ai_title = o.get("aiTitle", ai_title) or ai_title; continue
        if t == "custom-title":
            custom_title = o.get("customTitle", custom_title) or custom_title; continue
        if t == "last-prompt":
            last_prompt = o.get("lastPrompt", last_prompt) or last_prompt; continue
        cwd = o.get("cwd", cwd) or cwd
        branch = o.get("gitBranch", branch) or branch
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
    title = custom_title or ai_title or first_human or last_prompt or "(제목 없음)"
    return {"title": title.strip()[:120], "preview": (last_prompt or first_human).strip()[:140],
            "n": n, "last_ts": last_ts, "cwd": cwd, "branch": branch, "loop": loop}

# ---- index cache (per root) -------------------------------------------------
_INDEX = {"by_root": {}, "lock": threading.Lock()}
def session_files(root):
    return sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))

def build_index(root):
    items = []
    for path in session_files(root):
        try:
            st = os.stat(path)
        except OSError:
            continue
        s = summarize_file(path)
        items.append({"path": path, "proj": os.path.basename(os.path.dirname(path)),
                      "sid": os.path.basename(path)[:-6], "title": s["title"], "preview": s["preview"],
                      "n": s["n"], "mtime": st.st_mtime, "size": st.st_size, "cwd": s["cwd"],
                      "branch": s["branch"], "loop": s["loop"]})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

def get_index(root):
    with _INDEX["lock"]:
        if root not in _INDEX["by_root"]:
            _INDEX["by_root"][root] = build_index(root)
        return _INDEX["by_root"][root]

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

def agg_stats(items):
    s = {"sessions": 0, "my_sessions": 0, "my_msgs": 0, "size": 0, "my_size": 0,
         "loop": 0, "asst": 0, "tool": 0}
    for it in items:
        s["sessions"] += 1
        s["size"] += it["size"]
        s["asst"] += it["n"]["assistant"]
        s["tool"] += it["n"]["tool-result"]
        s["my_msgs"] += it["n"]["you"]
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
    return "~" + p[len(_HOME):] if p.startswith(_HOME) else p

def proj_label(item):
    return short_path(item.get("cwd") or "") or item.get("proj", "")

def counts_html(n, system=False):
    parts = [f'<span title="내가 직접 보낸 메시지 수">🧑 {n["you"]}</span>',
             f'<span title="Claude(어시스턴트) 응답 수">✦ {n["assistant"]}</span>',
             f'<span title="도구 실행 결과 수 (Bash/Edit/Read 등)">⚙ {n["tool-result"]}</span>']
    if system:
        parts.append(f'<span title="시스템·주입 컨텍스트 수 (system-reminder/IDE/명령출력 등)">ⓘ {n["system"]}</span>')
    return " · ".join(parts)

def hl(text, q):
    if not q:
        return esc(text)
    out, low, ql, i = [], text.lower(), q.lower(), 0
    while True:
        j = low.find(ql, i)
        if j < 0:
            out.append(esc(text[i:])); break
        out.append(esc(text[i:j])); out.append("<mark>" + esc(text[j:j+len(q)]) + "</mark>")
        i = j + len(q)
    return "".join(out)

ROLE_LABEL = {"you": "🧑 나", "assistant": "✦ Claude", "tool-result": "⚙ 도구 결과",
              "system": "ⓘ 시스템·주입", "subagent": "🤖 서브에이전트",
              "orchestrator": "📋 지시 → 서브에이전트"}
ROLE_DESC = {
    "you": "내가 직접 타이핑하거나 붙여넣은 메시지 — 검증된 규칙으로 이것만 '나'로 표시",
    "assistant": "Claude(어시스턴트)의 답변",
    "tool-result": "Claude가 실행한 도구(Bash 명령·Edit/Write·Read 등)의 출력 결과. 사람이 쓴 게 아님",
    "system": "시스템이 자동으로 끼워 넣은 컨텍스트 — system-reminder·IDE 알림·슬래시명령 출력·task-notification 등. 사람이 쓴 게 아님",
    "subagent": "Claude가 띄운 하위(서브)에이전트의 대화",
    "orchestrator": "서브에이전트에게 준 작업 지시문 (사람이 아니라 Claude가 생성)"}

def legend_html(open_=False):
    rows = [("🧑 나", ROLE_DESC["you"]),
            ("✦ Claude", ROLE_DESC["assistant"]),
            ("💭 추론", "Claude의 사고 과정 — 보통 비공개로 접혀 있음"),
            ("🔧 도구 호출", "Claude가 도구(Bash 실행·파일 Edit/Write·Read 등)를 부른 호출"),
            ("⚙ 도구 결과", ROLE_DESC["tool-result"]),
            ("ⓘ 시스템·주입", ROLE_DESC["system"]),
            ("📋 지시", ROLE_DESC["orchestrator"]),
            ("🤖 서브에이전트", ROLE_DESC["subagent"])]
    body = "".join(f'<div style="margin:3px 0"><b>{esc(e)}</b> — <span class=meta>{esc(d)}</span></div>'
                   for e, d in rows)
    return (f'<details class="card"{" open" if open_ else ""}>'
            f'<summary style="cursor:pointer;font-weight:650;color:#1f6feb">❓ 메시지 종류 설명 (범례)</summary>'
            f'<div style="margin-top:8px">{body}</div></details>')
TAG_BADGE = {"error": "⚠️", "edit": "✏️", "command": "❯", "commit": "⎇", "test": "🧪", "url": "🔗", "web": "🌐"}

def render_turn(gi, t, q="", thread_link=None):
    role, segs, ts, tags = t["role"], t["segs"], t["ts"], t["tags"]
    parts = []
    for kind, txt in segs:
        if kind == "text":
            parts.append(f'<div class=seg>{hl(txt, q)}</div>')
        elif kind == "thinking":
            if (txt or "").strip():
                parts.append(f'<details class=fold><summary>💭 추론 과정</summary><div class="seg mono">{esc(txt)}</div></details>')
            else:
                parts.append('<div class="seg muted">💭 (추론 비공개)</div>')
        elif kind == "tool_use":
            parts.append(f'<details class=fold><summary>🔧 도구 호출</summary><div class="seg mono">{esc(txt[:6000])}</div></details>')
        elif kind == "tool_result":
            tt = txt if len(txt) < 6000 else txt[:6000] + "\n… (생략)"
            parts.append(f'<details class=fold><summary>⚙ 도구 결과 ({len(txt)}자)</summary><div class="seg mono">{esc(tt)}</div></details>')
        elif kind == "injected":
            tt = txt if len(txt) < 4000 else txt[:4000] + "\n… (생략)"
            parts.append(f'<details class=fold><summary>주입된 컨텍스트 보기</summary><div class="seg mono">{esc(tt)}</div></details>')
    badges = "".join(f'<span class=badge title="{c}">{TAG_BADGE[c]}</span>' for c in
                     ("error", "edit", "command", "commit", "test", "url", "web") if c in tags)
    link = f'<a class=threadlink href="{thread_link}">↳ 답변 스레드</a>' if thread_link else ""
    tstr = f'<span class=time>{fmt_ts_short(ts)}</span>' if ts else ""
    data = f' data-thread="{esc(thread_link)}"' if thread_link else ""
    cats = " ".join((["you"] if role == "you" else []) + sorted(tags))
    who = (f'<div class=who><span title="{esc(ROLE_DESC.get(role, ""))}">{ROLE_LABEL.get(role, role)} {badges}</span>'
           f'<span class=whoR>{tstr}{link}</span></div>')
    return f'<div class="msg {role}" id="t{gi}" data-cats="{cats}"{data}>{who}{"".join(parts)}</div>'

# ---- HTML shell (token-replace, NOT str.format — so CSS/JS braces stay literal) ----
SHELL = r"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
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
@media(prefers-color-scheme:dark){
 .you .who{background:#16304f;color:#9ec5ff} .you{border-color:#244668}
 .assistant .who{background:#15331f;color:#7ddfa1}
 .orchestrator .who{background:#241a3a;color:#c2a8f0} .orchestrator{border-color:#3a2c5c}
 .tool-result .who,.system .who,.subagent .who{background:#23262d;color:#9aa0a8}}
.subcard{background:#faf7ff;border:1px solid #e3d7f7}
@media(prefers-color-scheme:dark){.subcard{background:#1c1830;border-color:#352a52}}
.whoR{display:flex;gap:10px;align-items:center}
.time{font-weight:400;color:#9aa0a8;font-size:11px;font-variant-numeric:tabular-nums}
.sid{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;color:#9aa0a8;user-select:all}
code.sid{background:#eef1f4;padding:1px 5px;border-radius:4px;color:#555}
@media(prefers-color-scheme:dark){code.sid{background:#2a2e35;color:#aeb4bd}}
.badge{font-weight:400;font-size:11px;margin-left:2px}
.threadlink{font-weight:600;color:#1f6feb;text-decoration:none;font-size:11px;white-space:nowrap}
.seg{padding:9px 15px;white-space:pre-wrap;word-break:break-word}
.seg.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#555;max-height:340px;overflow:auto;background:#fafbfc}
@media(prefers-color-scheme:dark){.seg.mono{color:#9aa0a8;background:#15171c}}
.muted{color:#9aa0a8;font-style:italic}
details.fold{border-top:1px dashed #e0e3e7}
details.fold>summary{cursor:pointer;padding:5px 15px;font-size:12px;color:#8a8f98;user-select:none}
@media(prefers-color-scheme:dark){details.fold{border-color:#2a2e35}}
mark{background:#ffe27a;color:#000;padding:0 1px;border-radius:2px}
.msg.kfocus{outline:3px solid #1f6feb;outline-offset:2px}
.msg:target{outline:3px solid #f59e0b;outline-offset:2px}
.pg{display:flex;gap:10px;justify-content:center;margin:18px 0}
.pg a{padding:7px 16px;border-radius:9px;background:#1f6feb;color:#fff;text-decoration:none;font-size:13px}
.snip{color:#666;font-size:12.5px;margin:4px 0 0;padding-left:10px;border-left:2px solid #d9dde2}
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
  <a class=home href="%%HOMEHREF%%">&#9776; 대화 뷰어</a>
  <form action="/search" role=search>
    <input type=search name=q id=qbox placeholder="모든 대화 검색  ( / 키로 포커스 )" value="%%Q%%">
    <select name=scope><option value=all%%SA%%>전체</option><option value=human%%SH%%>내 말만</option></select>
    %%ROOTHIDDEN%%
    <button>검색</button>
  </form>
</header>
%%ROOTBAR%%
<div class=wrap>%%BODY%%</div>
<div id=minimap></div>
<script>
(function(){
  var cur=-1;
  function ys(){return Array.prototype.slice.call(document.querySelectorAll('.msg.you'));}
  function focusYou(i){var a=ys();if(!a.length)return;cur=((i%a.length)+a.length)%a.length;
    a.forEach(function(e){e.classList.remove('kfocus');});var el=a[cur];
    el.classList.add('kfocus');el.scrollIntoView({block:'center',behavior:'smooth'});}
  document.addEventListener('keydown',function(e){
    var tag=(e.target.tagName||'').toLowerCase();
    var typing=(tag==='input'||tag==='select'||tag==='textarea');
    if(e.key==='/'&&!typing){e.preventDefault();var s=document.getElementById('qbox');if(s){s.focus();s.select();}return;}
    if(e.key==='Escape'&&typing){e.target.blur();return;}
    if(typing)return;
    if(e.key==='j'||e.key==='n'){if(ys().length){e.preventDefault();focusYou(cur+1);}}
    else if(e.key==='k'||e.key==='p'){if(ys().length){e.preventDefault();focusYou(cur-1);}}
    else if(e.key==='Enter'&&cur>=0){var a=ys();var l=a[cur]&&a[cur].getAttribute('data-thread');if(l)location.href=l;}
  });
  // copy buttons (code view)
  document.addEventListener('click',function(e){
    if(e.target.classList.contains('copy')){
      var pre=e.target.closest('.codeart').querySelector('pre.code');
      var txt=pre?pre.textContent:'';
      if(navigator.clipboard){navigator.clipboard.writeText(txt);}
      var o=e.target.textContent;e.target.textContent='복사됨 ✓';setTimeout(function(){e.target.textContent=o;},1200);
    }
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
    if(p&&window.performance){p.textContent=' · 브라우저 렌더 '+Math.round(performance.now())+'ms';}
    buildMinimap();
  });
})();
</script>
</body></html>"""

def shell(title, body, q="", scope="all", root=None):
    root = root if root in ROOTS else ROOT
    multi = len(ROOTS) > 1
    home = ("/?root=" + urllib.parse.quote(root)) if multi else "/"
    hidden = f'<input type=hidden name=root value="{esc(root)}">' if multi else ""
    links = []
    for r in ROOTS:
        on = "on" if r == root else ""
        rm = (f'<a class=rmroot href="/delroot?path={urllib.parse.quote(r)}" title="목록에서 제거">✕</a>'
              if r in SAVED_ROOTS else "")
        links.append(f'<span class=rootitem><a class="{on}" href="/?root={urllib.parse.quote(r)}">'
                     f'{esc(short_path(r))}</a>{rm}</span>')
    addform = ('<form class=addroot action="/addroot" method=get>'
               '<input name=path placeholder="새 폴더 추가 — 경로 붙여넣기 (…/.claude/projects)">'
               '<button>➕ 추가</button></form>')
    rootbar = f'<div class=rootbar><span class=lbl>📁 폴더:</span>{"".join(links)}{addform}</div>'
    return (SHELL.replace("%%TITLE%%", esc(title)).replace("%%BODY%%", body)
            .replace("%%Q%%", esc(q))
            .replace("%%SA%%", " selected" if scope == "all" else "")
            .replace("%%SH%%", " selected" if scope == "human" else "")
            .replace("%%HOMEHREF%%", home).replace("%%ROOTHIDDEN%%", hidden)
            .replace("%%ROOTBAR%%", rootbar))

# ---- handlers ---------------------------------------------------------------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body):
        b = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _redirect(self, loc):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        g = lambda k, d="": qs.get(k, [d])[0]
        root = active_root(g("root"))
        if u.path == "/":
            return self._send(self.index(g("proj"), g("sort", "date"), g("dir", ""), root))
        if u.path == "/search":
            return self._send(self.search(g("q"), g("scope", "all"), root))
        if u.path == "/session":
            return self._send(self.session(g("p"), g("q"), g("filter", "all"),
                                           int(g("off", "0") or 0), g("lim", ""), g("thread", ""), g("view", "")))
        if u.path == "/subagent":
            return self._send(self.subagent(g("p"), g("parent"), g("q")))
        if u.path == "/addroot":
            return self.addroot(g("path"))
        if u.path == "/delroot":
            return self.delroot(g("path"))
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
        body = (f'<div class=card><b>폴더를 추가할 수 없습니다.</b>'
                f'<p class=meta>입력: <code class=sid>{esc(path)}</code></p>'
                f'<p>그 경로가 존재하고, 안에 <code>*/*.jsonl</code> 세션이 있는 <b>projects</b> 폴더여야 해요. '
                f'(<code>.claude</code> 폴더나 그 부모를 줘도 자동으로 <code>projects</code>를 찾습니다.)<br>'
                f'예: <code>/Volumes/backup/.claude/projects</code></p>'
                f'<p><a href="/">← 돌아가기</a></p></div>')
        return self._send(shell("폴더 추가 실패", body))

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
        SORTF = {"date": "날짜", "mine": "내 메시지", "title": "제목", "size": "용량"}
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
        if proj_filter:
            st = agg_stats(items)
            label = proj_cwd.get(proj_filter, proj_filter)
            loopline = (f' · <span class=loopchip>🔁 자율 빌드루프 {st["loop"]}개</span>') if st["loop"] else ""
            statsblock = (
                f'<div class="card digest"><b>📁 {esc(label)}</b>{loopline}'
                f'<div style="margin-top:6px">총 <b>{st["sessions"]}</b>개 세션 · '
                f'🧑 내가 참여한 세션 <b>{st["my_sessions"]}</b>개 · 내가 쓴 메시지 <b>{st["my_msgs"]}</b>개</div>'
                f'<div>총 용량 <b>{fmt_size(st["size"])}</b> · 🧑 내가 참여한 세션 용량 합 <b>{fmt_size(st["my_size"])}</b></div>'
                f'<div class=meta>✦ Claude {st["asst"]} · ⚙ 도구결과 {st["tool"]}</div></div>')
        else:
            by = {}
            for it in all_items:
                by.setdefault(it["proj"], []).append(it)
            ov = []
            for p, its in sorted(by.items(), key=lambda kv: -agg_stats(kv[1])["size"]):
                s = agg_stats(its)
                lc = f'🔁 {s["loop"]}' if s["loop"] else ""
                ov.append(f'<tr><td><a href="{q(proj=p, sort=sort, dir=dir_)}">{esc(proj_cwd.get(p, p))}</a></td>'
                          f'<td>{s["sessions"]}</td><td>{s["my_sessions"]}</td><td>{s["my_msgs"]}</td>'
                          f'<td>{fmt_size(s["size"])}</td><td>{fmt_size(s["my_size"])}</td><td>{lc}</td></tr>')
            tot = agg_stats(all_items)
            table = ('<table class=stab><thead><tr><th>프로젝트(폴더)</th><th title="세션 수">세션</th>'
                     '<th title="내가(사람이) 참여한 세션 수">내 참여</th><th title="내가 쓴 총 메시지 수">내 메시지</th>'
                     '<th title="모든 세션 용량 합">총 용량</th><th title="내가 참여한 세션들의 용량 합">내 세션 용량</th>'
                     '<th title="자율 빌드루프 세션 수">🔁</th></tr></thead><tbody>' + "".join(ov)
                     + f'<tr class=tot><td>합계 {len(by)}개 폴더</td><td>{tot["sessions"]}</td><td>{tot["my_sessions"]}</td>'
                     f'<td>{tot["my_msgs"]}</td><td>{fmt_size(tot["size"])}</td><td>{fmt_size(tot["my_size"])}</td>'
                     f'<td>{tot["loop"] or ""}</td></tr></tbody></table>')
            statsblock = (f'<details class="card" open><summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                          f'📊 프로젝트별 통계 ({len(by)}개 폴더)</summary>{table}</details>')

        arrow = "▼" if dir_ == "desc" else "▲"
        sortbar = ['<div class=bar><span class=meta>정렬:</span>']
        for k, lbl in SORTF.items():
            if k == sort:
                nd = "asc" if dir_ == "desc" else "desc"
                sortbar.append(f'<a class=on href="{q(proj=proj_filter, sort=k, dir=nd)}" '
                               f'title="클릭하면 방향 전환">{lbl} {arrow}</a>')
            else:
                sortbar.append(f'<a href="{q(proj=proj_filter, sort=k, dir=DEFDIR[k])}">{lbl}</a>')
        sortbar.append("</div>")

        projbar = ['<div class=bar><span class=meta>프로젝트:</span>',
                   f'<a class="{"" if proj_filter else "on"}" href="{q(sort=sort, dir=dir_)}">전체</a>']
        for p in projs:
            projbar.append(f'<a class="{"on" if p==proj_filter else ""}" '
                           f'href="{q(proj=p, sort=sort, dir=dir_)}">{esc(proj_cwd.get(p, p))}</a>')
        projbar.append("</div>")
        rows = []
        for it in items:
            link = "/session?p=" + urllib.parse.quote(it["path"])
            loopchip = ' <span class=loopchip>🔁 자율 빌드루프</span>' if it.get("loop") else ""
            rows.append(
                f'<div class=card><a class=t href="{link}">{esc(it["title"])}</a>{loopchip}'
                f'<div class=meta><span class=chip>{esc(proj_label(it))}</span>'
                f'{counts_html(it["n"])} · '
                f'{fmt_mtime(it["mtime"])} · {fmt_size(it["size"])} · '
                f'<span class=sid>id {esc(it["sid"])}</span></div>'
                + (f'<div class=preview>{esc(it["preview"])}</div>' if it["preview"] else "") + '</div>')
        head = (f'<p class=meta>{len(items)}개 세션 · <b>🧑 나</b>는 검증된 규칙으로 '
                f'<b>실제 네가 타이핑한 메시지만</b> 표시 · {esc(root)}</p>'
                f'<p class=meta>범례: 🧑 나(내 메시지) · ✦ Claude 응답 · ⚙ 도구 결과 · ⓘ 시스템·주입 '
                f'<span class=hint>(숫자에 마우스 올리면 설명, 아래 ❓ 펼치면 전체 설명)</span></p>'
                + legend_html())
        return shell("대화 뷰어", head + statsblock + "".join(sortbar) + "".join(projbar) + "".join(rows), root=root)

    # ---- search ----
    def search(self, q, scope, root=None):
        root = root if root in ROOTS else ROOT
        if not q.strip():
            return shell("검색", "<p class=meta>검색어를 입력하세요. (<kbd>/</kbd> 로 검색창 포커스)</p>", q, scope, root)
        human_only = scope == "human"
        results = []
        for path in session_files(root):
            hits, title = [], ""
            for t in classify_turns(path):
                role, segs = t["role"], t["segs"]
                if role == "you" and not title:
                    title = " ".join(x[1] for x in segs if x[0] == "text").strip()[:100]
                if human_only and role != "you":
                    continue
                txt = " ".join(x[1] for x in segs if x[0] in ("text", "tool_result", "thinking", "injected"))
                if q.lower() in txt.lower():
                    idx = txt.lower().find(q.lower())
                    hits.append((role, txt[max(0, idx-55):idx+len(q)+90].replace("\n", " ")))
            if hits:
                results.append({"path": path, "title": title or "(제목 없음)",
                                "proj": os.path.basename(os.path.dirname(path)), "n": len(hits), "hits": hits[:6]})
        results.sort(key=lambda x: x["n"], reverse=True)
        rows = []
        for r in results:
            link = ("/session?p=" + urllib.parse.quote(r["path"]) + "&q=" + urllib.parse.quote(q)
                    + ("&filter=human" if human_only else ""))
            snips = "".join(f'<div class=snip><span class=chip>{ROLE_LABEL.get(role, role)}</span>{hl(s, q)}</div>'
                            for role, s in r["hits"])
            short = r["proj"].replace("-Users-kimdongryeong-", "~/").replace("-", "/")
            rows.append(f'<div class=card><a class=t href="{link}">{esc(r["title"])}</a> '
                        f'<span class=meta>({r["n"]}건)</span>'
                        f'<div class=meta><span class=chip>{esc(short)}</span></div>{snips}</div>')
        head = f'<p class=meta>"{esc(q)}" — {len(results)}개 세션에서 매치{" · <b>내 말만</b> 범위" if human_only else ""} · 📁 {esc(short_path(root))}</p>'
        return shell(f"검색: {q}", head + ("".join(rows) or "<p class=meta>결과 없음.</p>"), q, scope, root)

    # ---- session ----
    def session(self, path, q="", filt="all", off=0, lim_raw="", thread="", view=""):
        rt = root_for_path(path)
        if not path or not os.path.exists(path) or rt is None:
            return shell("?", "<p>세션을 찾을 수 없습니다.</p>")
        t0 = time.perf_counter()
        turns = classify_turns(path)
        meta = summarize_file(path)
        sid = os.path.basename(path)[:-6]
        you_idx = [i for i, t in enumerate(turns) if t["role"] == "you"]

        def url(**kw):
            params = {"p": path}
            params.update({k: v for k, v in kw.items() if v not in (None, "")})
            return "/session?" + urllib.parse.urlencode(params)

        head = (f'<p class=meta>{esc(meta["cwd"] or os.path.basename(os.path.dirname(path)))} · '
                f'{esc(meta["branch"])} · {fmt_ts(meta["last_ts"])}</p>'
                f'<h3 style="margin:4px 0">{esc(meta["title"])}'
                + (' <span class=loopchip>🔁 자율 빌드루프</span>' if meta.get("loop") else "") + '</h3>'
                f'<p class=meta>session-id <code class=sid>{esc(sid)}</code> · '
                f'복귀: <code class=sid>claude --resume {esc(sid)}</code> · 📁 {esc(short_path(rt))}</p>'
                + legend_html())

        # subagent banner
        subs = [subagent_brief(s) for s in subagent_files(path)]
        if subs:
            sub_items = "".join(
                f'<div class=card style="margin:6px 0"><a class=t '
                f'href="/subagent?p={urllib.parse.quote(sb["path"])}&parent={urllib.parse.quote(path)}'
                f'{("&q="+urllib.parse.quote(q)) if q else ""}">🤖 {esc(sb["brief"])}</a>'
                f'<div class=meta>{("워크플로 "+esc(sb["wf"])+" · ") if sb["wf"] else ""}'
                f'{sb["n"]}개 메시지 · agent {esc(sb["agentId"][:10])}</div></div>'
                for sb in subs)
            head += (f'<details class=fold style="margin:10px 0;border:1px solid #d9c8f5;border-radius:11px" open>'
                     f'<summary style="padding:9px 14px;color:#6b3fb5;font-weight:600">'
                     f'🤖 이 세션이 띄운 서브에이전트 {len(subs)}개 — 펼쳐보기</summary>'
                     f'<div style="padding:0 12px 8px">{sub_items}</div></details>')

        # extracted-fact digest
        d = session_digest(turns)
        dl = []
        dl.append(f'✏️ 편집 {d["edits"]}회 ({len(d["files"])}개 파일) · ❯ 명령 {d["cmds"]} · '
                  f'🧪 테스트 {d["tests"]} · ⚠️ 에러 {d["errors"]} · ⎇ 커밋 {len(d["commits"])} · 🌐 웹 {d["webs"]}')
        if d["files"]:
            dl.append('<div style="margin-top:7px"><b>건드린 파일</b> ' +
                      "".join(f'<span class=dfile>{esc(short_path(f))}</span>' for f in d["files"][:25]) +
                      (f'<span class=meta>… 외 {len(d["files"])-25}개</span>' if len(d["files"]) > 25 else "") + '</div>')
        if d["commits"]:
            dl.append('<div style="margin-top:7px"><b>커밋</b> ' +
                      "".join(f'<span class=dfile>⎇ {esc(c)}</span>' for c in d["commits"][:12]) + '</div>')
        if d["prs"]:
            dl.append('<div style="margin-top:7px"><b>PR/이슈</b> ' +
                      "".join(f'<a class=dfile href="{esc(u)}" target=_blank>{esc(u)}</a>' for u in d["prs"][:10]) + '</div>')
        digest = (f'<details class="card digest" open><summary style="cursor:pointer;font-weight:650;color:#1f6feb">'
                  f'📊 이 세션 요약 (추출된 사실)</summary><div style="margin-top:8px">{"".join(dl)}</div></details>')
        head += digest

        # ---- CODE view ----
        if view == "code":
            arts = extract_code(turns)
            bar = (f'<div class=bar><a href="{url(q=q)}">← 대화로</a>'
                   f'<a class=on href="{url(view="code", q=q)}">🧩 코드만</a>'
                   f'<span class=meta>{len(arts)}개 코드/편집 · 서버 {int((time.perf_counter()-t0)*1000)}ms<span id=perf></span></span></div>')
            body = []
            for a in arts:
                lbl = ("✏️ " + short_path(a["label"])) if a["kind"] == "edit" else ("``` " + a["label"])
                body.append(
                    f'<div class=codeart><div class=codehead><span><a href="{url(q=q)}#t{a["gi"]}" '
                    f'style="text-decoration:none">{esc(lbl)}</a> <span class=time>{fmt_ts_short(a["ts"])}</span></span>'
                    f'<button class=copy>복사</button></div><pre class=code>{esc(a["body"])}</pre></div>')
            return shell(meta["title"][:50], head + bar + ("".join(body) or "<p class=meta>코드/편집이 없습니다.</p>"), q, root=rt)

        # ---- thread mode ----
        if thread != "":
            try:
                gi = int(thread)
            except ValueError:
                gi = -1
            if gi < 0 or gi >= len(turns) or turns[gi]["role"] != "you":
                return shell("?", head + "<p class=meta>스레드를 찾을 수 없습니다.</p>", q, root=rt)
            nxt = next((i for i in you_idx if i > gi), len(turns))
            body = [render_turn(i, turns[i], q, url(thread=i, q=q) if turns[i]["role"] == "you" else None)
                    for i in range(gi, nxt)]
            ms = int((time.perf_counter() - t0) * 1000)
            bar = ('<div class=bar>'
                   f'<a href="{url(filter="human", q=q)}">← 내 말만 목록</a>'
                   f'<a href="{url(q=q)}#t{gi}">전체에서 보기</a>'
                   f'<span class=meta>🧑 질문 → 답변 스레드 ({nxt-gi}개) · 서버 {ms}ms<span id=perf></span></span></div>')
            return shell(meta["title"][:50], head + bar + "".join(body), q, root=rt)

        # ---- normal / human-filtered + pagination ----
        lim = parse_lim(lim_raw) if lim_raw != "" else DEFAULT_LIM
        idxs = you_idx if filt == "human" else range(len(turns))
        view_turns = [(i, turns[i]) for i in idxs]
        total = len(view_turns)
        page = view_turns if lim is None else view_turns[off:off + lim]
        body = []
        for gi, t in page:
            tl = url(thread=gi, q=q) if t["role"] == "you" else None
            body.append(render_turn(gi, t, q, tl))
        ms = int((time.perf_counter() - t0) * 1000)

        n = meta["n"]
        toggles = ('<div class=bar>'
                   f'<a class="{"on" if filt=="all" else ""}" href="{url(q=q, lim=lim_raw)}">전체 보기</a>'
                   f'<a class="{"on" if filt=="human" else ""}" href="{url(filter="human", q=q, lim=lim_raw)}">🧑 내 말만</a>'
                   f'<a href="{url(view="code", q=q)}">🧩 코드만</a>'
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
        CHIP_LBL = {"you": "🧑 내 메시지", "error": "⚠️ 에러", "edit": "✏️ 편집", "command": "❯ 명령",
                    "commit": "⎇ 커밋", "test": "🧪 테스트", "url": "🔗 URL"}
        chips = ['<div class=chips><button class=chip-f data-cat="*">전체</button>']
        for c, lbl in CHIP_LBL.items():
            if cc[c]:
                chips.append(f'<button class=chip-f data-cat="{c}">{lbl}<span class=cnt>{cc[c]}</span></button>')
        chips.append('</div>')

        opts = []
        for v in LIM_OPTIONS:
            opts.append(f'<option value="{v}"{" selected" if (lim is not None and lim == v) else ""}>{v}개</option>')
        opts.append(f'<option value="all"{" selected" if lim is None else ""}>전체({total})</option>')
        sizeform = ('<form class=psize method=get action=/session>'
                    f'<input type=hidden name=p value="{esc(path)}">'
                    + (f'<input type=hidden name=q value="{esc(q)}">' if q else "")
                    + (f'<input type=hidden name=filter value="{esc(filt)}">' if filt == "human" else "")
                    + '페이지당 <select name=lim onchange="this.form.submit()">' + "".join(opts) + '</select>'
                    + f'<span class=hint>· 서버 {ms}ms<span id=perf></span> · 표시 {len(page)}/{total} · '
                      f'<kbd>j</kbd>/<kbd>k</kbd> 내 메시지, <kbd>Enter</kbd> 답변 스레드 · 칩/미니맵은 현재 페이지 기준</span>'
                    + '</form>')
        pg = []
        if lim is not None:
            if off > 0:
                pg.append(f'<a href="{url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=max(0, off-lim))}">← 이전</a>')
            if off + lim < total:
                pg.append(f'<a href="{url(filter=(filt if filt=="human" else ""), q=q, lim=lim_raw, off=off+lim)}">다음 {min(lim, total-off-lim)}개 →</a>')
        pgbar = f'<div class=pg>{"".join(pg)}</div>' if pg else ""
        return shell(meta["title"][:50], head + toggles + "".join(chips) + sizeform + pgbar + "".join(body) + pgbar, q, root=rt)

    # ---- subagent thread ----
    def subagent(self, path, parent="", q=""):
        rt = root_for_path(path)
        if not path or not os.path.exists(path) or rt is None:
            return shell("?", "<p>서브에이전트 기록을 찾을 수 없습니다.</p>")
        t0 = time.perf_counter()
        turns = classify_turns(path, sub=True)
        sb = subagent_brief(path)
        body = [render_turn(i, t, q, None) for i, t in enumerate(turns)]
        ms = int((time.perf_counter() - t0) * 1000)
        back = ""
        if parent and os.path.exists(parent):
            back = f'<a href="/session?p={urllib.parse.quote(parent)}{("&q="+urllib.parse.quote(q)) if q else ""}">← 부모 세션으로</a>'
        bar = ('<div class=bar>' + back
               + f'<span class=meta>🤖 서브에이전트 · {("워크플로 "+esc(sb["wf"])+" · ") if sb["wf"] else ""}'
               f'agent {esc(sb["agentId"][:12])} · {len(turns)}개 메시지 · 서버 {ms}ms<span id=perf></span></span></div>')
        head = (f'<p class=meta>📋 지시: {esc(sb["brief"])}</p><h3 style="margin:4px 0">🤖 서브에이전트 대화</h3>')
        return shell("서브에이전트", head + bar + "".join(body), q, root=rt)

# ---- main -------------------------------------------------------------------
if __name__ == "__main__":
    if not os.path.isdir(ROOT):
        sys.exit(f"projects dir not found: {ROOT}")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"\n  Claude 대화 뷰어 → http://127.0.0.1:{PORT}")
    print(f"  보는 폴더: {ROOT}")
    print(f"  (이 창을 닫거나 Ctrl-C 로 종료)\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
