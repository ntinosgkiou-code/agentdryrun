"""`scan --wrapped`: one shareable card about what your coding agent did. Numbers only (no commands, paths or project names)."""
from __future__ import annotations

import html
import time
from collections import Counter

REPO_URL = "github.com/ntinosgkiou-code/agentdryrun"

# (upper bound of the share of actions that would have needed a human, title, one line)
PERSONAS = [
    (0.005, "The Calm Operator", "Almost everything went through on its own."),
    (0.02, "The Careful Shipper", "A few moments where a human should have looked."),
    (0.05, "The Fast Mover", "Quick hands. Some of it deserved a second pair of eyes."),
    (0.10, "The Brave One", "A lot of this would have asked for permission."),
    (1.01, "Living Dangerously", "Your agent had very few brakes."),
]


def persona(share: float) -> tuple:
    """(title, line) for the share of judged actions that would have needed approval or been refused."""
    for bound, title, line in PERSONAS:
        if share < bound:
            return title, line
    return PERSONAS[-1][1], PERSONAS[-1][2]


_ACTION_GROUPS = {
    "reads": ("file.read", "secrets.read"),
    "writes": ("file.write",),
    "commands": ("shell.command", "shell.delete_recursive", "shell.sudo", "shell.pipe_to_shell", "shell.chmod_open", "git.force_push",
                 "git.discard_changes", "db.destructive_sql", "infra.destructive", "package.publish", "net.upload", "net.remote_access",
                 "net.fetch", "secrets.dump_env"),
}
_QUIET = {"shell.command", "file.read", "net.fetch", "web.fetch", "agent.spawn", "agent.other"}


def card_stats(*, s: dict, kinds: dict, stats: dict, info: dict, calls_info: list, label: dict) -> dict:
    """Everything the card shows, as plain numbers and fixed labels."""
    days, hours, per_session = Counter(), Counter(), Counter()
    for c in calls_info:
        per_session[c.get("session")] += 1
        t = c.get("at")
        if t:
            lt = time.localtime(t)
            days[time.strftime("%Y-%m-%d", lt)] += 1
            hours[lt.tm_hour] += 1
    busiest = days.most_common(1)[0] if days else None
    peak = hours.most_common(1)[0][0] if hours else None

    def total(group):
        return sum(kinds.get(k, {}).get("total", 0) for k in _ACTION_GROUPS[group])

    close = []
    for t, v in kinds.items():
        if t in _QUIET or not (v["pending"] or v["deny"]):
            continue
        close.append((v["deny"] * 3 + v["pending"], label.get(t, t), v["total"], v["deny"]))
    close.sort(reverse=True)
    title, line = persona(s.get("needs_review_share", 0))
    return {
        "period": info.get("label", ""), "calls": info.get("calls", 0), "sessions": info.get("sessions", 0),
        "active_days": len(days), "busiest_day": busiest[0] if busiest else "", "busiest_day_calls": busiest[1] if busiest else 0,
        "peak_hour": peak, "longest_session": max(per_session.values()) if per_session else 0,
        "reads": total("reads"), "writes": total("writes"), "commands": total("commands"),
        "judged": s.get("total", 0), "review_pct": round(100 * s.get("needs_review_share", 0), 1),
        "pending": s.get("pending", 0), "deny": s.get("deny", 0),
        "failed_pct": round(100 * stats["errors"] / stats["calls"], 1) if stats.get("calls") else 0.0,
        "tokens": stats.get("output_tokens_estimate", 0),
        "close_calls": [{"label": lab, "total": tot, "refused": den} for _, lab, tot, den in close[:3]],
        "persona": title, "persona_line": line,
    }


def share_text(w: dict) -> str:
    return (f"My Claude Code Wrapped ({w['period']}): {w['calls']:,} tool calls, {w['sessions']:,} sessions. "
            f"Under the starter rules {w['review_pct']}% of what my agent did would have needed a human. I am: {w['persona']}. "
            f"Check yours (local, read-only): {REPO_URL}")


def _rows(w: dict) -> str:
    e = html.escape
    close = w["close_calls"] or []
    out = ""
    for i in range(3):
        y = 1010 + i * 62
        if i < len(close):
            c = close[i]
            tail = f"{c['total']:,}" + (f"  ({c['refused']} refused)" if c["refused"] else "")
            out += (f'<text x="90" y="{y}" font-size="34" fill="#e8ecff">{e(c["label"])[:44]}</text>'
                    f'<text x="990" y="{y}" font-size="34" fill="#ffd166" text-anchor="end">{e(tail)}</text>')
        elif i == 0:
            out += f'<text x="90" y="{y}" font-size="34" fill="#9ad1a0">Nothing here would have needed a human.</text>'
    return out


def _svg(w: dict) -> str:
    e = html.escape
    peak = f"{w['peak_hour']:02d}:00" if w["peak_hour"] is not None else "-"
    stat = lambda x, y, n, lab: (f'<text x="{x}" y="{y}" font-size="40" font-weight="700" fill="#ffffff">{n}</text>'  # noqa: E731
                                 f'<text x="{x}" y="{y + 42}" font-size="26" fill="#a9b4ff">{lab}</text>')
    return f"""<svg id="card" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="540" height="675" font-family="system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1020"/><stop offset="1" stop-color="#241552"/></linearGradient></defs>
<rect width="1080" height="1350" fill="url(#g)"/>
<text x="90" y="130" font-size="30" letter-spacing="6" fill="#a9b4ff">CLAUDE CODE WRAPPED</text>
<text x="90" y="180" font-size="30" fill="#7e89c9">{e(w['period'])}</text>
<text x="90" y="400" font-size="190" font-weight="800" fill="#ffffff">{w['calls']:,}</text>
<text x="90" y="460" font-size="40" fill="#c9d1ff">tool calls by your agent</text>
{stat(90, 590, f"{w['sessions']:,}", "sessions")}{stat(400, 590, f"{w['active_days']:,}", "active days")}{stat(710, 590, peak, "busiest hour")}
{stat(90, 720, f"{w['commands']:,}", "commands")}{stat(400, 720, f"{w['reads']:,}", "files read")}{stat(710, 720, f"{w['writes']:,}", "files written")}
<rect x="60" y="810" width="960" height="130" rx="28" fill="#ffffff" fill-opacity="0.08"/>
<text x="90" y="866" font-size="30" fill="#a9b4ff">YOU ARE</text>
<text x="90" y="918" font-size="52" font-weight="800" fill="#ffd166">{e(w['persona'])}</text>
<text x="90" y="985" font-size="28" fill="#c9d1ff">{w['review_pct']}% of actions would have needed a human &#183; {w['pending']:,} approvals, {w['deny']:,} refused</text>
{_rows(w)}
<text x="90" y="1250" font-size="26" fill="#7e89c9">judged with the starter rules &#183; a simulation, not a security audit</text>
<text x="90" y="1300" font-size="30" fill="#ffffff">{REPO_URL}</text>
</svg>"""


_PAGE_CSS = ("body{margin:0;background:#0b1020;color:#e8ecff;font:16px system-ui,sans-serif;display:flex;flex-direction:column;align-items:center;padding:24px 16px;gap:16px}"
             "svg{max-width:100%;height:auto;border-radius:20px;box-shadow:0 10px 40px #0008}"
             "button{background:#ffd166;color:#241552;border:0;border-radius:12px;padding:12px 20px;font-weight:700;font-size:16px;cursor:pointer}"
             ".row{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}p{max-width:540px;color:#a9b4ff;text-align:center;margin:0}"
             "textarea{width:100%;max-width:540px;height:110px;background:#151a33;color:#e8ecff;border:1px solid #3a4075;border-radius:12px;padding:10px;font:14px system-ui}")
_PAGE_JS = """function savePng(){var s=document.getElementById('card'),x=new XMLSerializer().serializeToString(s),i=new Image();
i.onload=function(){var c=document.createElement('canvas');c.width=1080;c.height=1350;c.getContext('2d').drawImage(i,0,0,1080,1350);
c.toBlob(function(b){var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='claude-code-wrapped.png';a.click();});};
i.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(x);}
function copyText(){var t=document.getElementById('t');t.select();try{document.execCommand('copy');}catch(e){}}"""


def render_wrapped(w: dict) -> str:
    """The page: the card, a Download PNG button (made in the browser) and the text to post with it."""
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Claude Code Wrapped</title><style>{_PAGE_CSS}</style></head><body>{_svg(w)}'
            '<div class="row"><button onclick="savePng()">Download PNG</button><button onclick="copyText()">Copy post text</button></div>'
            f'<textarea id="t" readonly>{html.escape(share_text(w))}</textarea>'
            '<p>This card contains numbers only: no commands, no file names, no project names. Nothing was uploaded; the PNG is made in your browser.</p>'
            f'<script>{_PAGE_JS}</script></body></html>')
