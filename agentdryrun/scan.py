"""`python -m agentdryrun scan`: a dry run on your own coding agent's history.

Reads the session logs Claude Code keeps on your machine, names what the agent did (deleted, force-pushed, read a secret, ...),
judges every action against a rules pack as a dry run, and writes one HTML report card. Read-only. Nothing is sent anywhere.

    python -m agentdryrun scan                      # last 30 days of ~/.claude/projects
    python -m agentdryrun scan --days 90 --project my-app --no-previews

The rules are `agentdryrun/packs/coding-agent.json`; copy it, edit it, and pass it with --rules.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import coding
from .policy import validate_policy
from .report import _CSS, VERDICT, summarize
from .shadow import run_shadow, thresholds_exceeded

PACK = Path(__file__).with_name("packs") / "coding-agent.json"

LABEL = {
    "shell.delete_recursive": "Recursive deletes", "shell.sudo": "Commands with sudo", "shell.pipe_to_shell": "Downloaded scripts run unread (curl | sh)",
    "shell.chmod_open": "Permissions opened to everyone", "git.force_push": "Force pushes / remote branch deletes",
    "git.discard_changes": "Work thrown away (reset --hard, clean, ...)", "db.destructive_sql": "Destructive database commands",
    "infra.destructive": "Infrastructure or cloud deletes", "package.publish": "Publishes (npm, docker, ...)",
    "net.upload": "Files or output sent to a remote host", "net.remote_access": "Connections to other machines (ssh, scp, nc)",
    "secrets.read": "Secret files read", "secrets.dump_env": "Environment variables dumped",
    "file.write": "Writes to settings, CI, startup files, system folders",
    "mcp.call": "MCP tools that do not look read-only", "shell.command": "Ordinary shell commands", "file.read": "File reads and searches",
    "net.fetch": "Downloads", "web.fetch": "Web fetches and searches", "agent.spawn": "Sub-agents", "agent.other": "Other tool calls",
}
_QUIET = {"shell.command", "file.read", "net.fetch", "web.fetch", "agent.spawn", "agent.other"}


def _day(t) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t)) if t else "-"


def waste(calls: list) -> dict:
    """Output size and failures per tool call. Sizes are characters of tool output; tokens are a rough characters / 4."""
    total = sum(c["chars"] for c in calls)
    errs = [c for c in calls if c["error"]]
    by_tool = defaultdict(lambda: [0, 0, 0])
    for c in calls:
        row = by_tool[c["tool"]]
        row[0] += 1
        row[1] += 1 if c["error"] else 0
        row[2] += c["chars"]
    loops = Counter((c["session"], c["tool"], c["preview"]) for c in errs)
    return {
        "calls": len(calls), "errors": len(errs), "output_chars": total, "output_tokens_estimate": total // 4,
        "biggest": sorted(calls, key=lambda c: -c["chars"])[:8],
        "by_tool": sorted(([k, *v] for k, v in by_tool.items()), key=lambda r: -r[3])[:6],
        "loops": [{"tool": k[1], "preview": k[2], "times": n, "project": next((c["project"] for c in errs if c["session"] == k[0] and c["preview"] == k[2]), "")}
                  for k, n in loops.most_common(5) if n >= 3],
    }


def card_numbers(s: dict, obs: list, meta: dict) -> dict:
    """Counts per kind of action, with the verdicts, for the table at the top of the card."""
    kinds = defaultdict(lambda: {"total": 0, "allow": 0, "pending": 0, "deny": 0})
    for o in obs:
        k = kinds[o["tool"]]
        k["total"] += 1
        k[o["decision"]] += 1
    return dict(sorted(kinds.items(), key=lambda kv: (-(kv[1]["deny"] * 1000 + kv[1]["pending"]), -kv[1]["total"])))


def attention_rows(obs: list, meta: dict, n: int = 30) -> list:
    order = {"deny": 0, "pending": 1}
    rows = [o for o in obs if o["decision"] in order]
    rows.sort(key=lambda o: (order.get(o["decision"], 2), -(o.get("occurred_at") or 0)))
    return rows[:n]


_EXTRA_CSS = """.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;word-break:break-all}.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:12px;font-weight:600}
.p-deny{background:var(--ers);color:var(--er)}.p-pending{background:var(--wns);color:var(--wn)}.p-allow{background:var(--oks);color:var(--ok)}h1 small{font-size:15px;color:var(--mu);font-weight:400}"""


def render_card(*, s: dict, kinds: dict, rows: list, meta: dict, stats: dict, info: dict, days, previews: bool, rules_name: str, banner: str = "") -> str:
    e = html.escape
    pct = round(100 * s["needs_review_share"], 1)
    k_rows = "".join(
        f"<tr><td>{e(LABEL.get(t, t))}</td><td class='mu'><code>{e(t)}</code></td><td>{v['total']}</td><td>{v['allow']}</td><td>{v['pending']}</td><td>{v['deny']}</td></tr>"
        for t, v in kinds.items() if t not in _QUIET or v["pending"] or v["deny"]) or "<tr><td colspan=6>-</td></tr>"
    a_rows = ""
    for o in rows:
        m = meta.get(o.get("external_id") or "", {})
        cmd = f"<td class='mono'>{e(m.get('preview', ''))}</td>" if previews else ""
        why = "; ".join(o["reasons"][:2]) or "tool is classified high risk"
        a_rows += (f"<tr><td>{e(_day(o.get('occurred_at')))}</td><td>{e(m.get('project', ''))}</td><td>{e(LABEL.get(o['tool'], o['tool']))}</td>"
                   f"<td><span class='pill p-{o['decision']}'>{e('refused' if o['decision'] == 'deny' else 'approval')}</span></td><td>{e(why)}</td>{cmd}</tr>")
    a_rows = a_rows or f"<tr><td colspan={7 if previews else 6}>Nothing in this period would have been stopped.</td></tr>"
    big = "".join(f"<tr><td>{e(c['tool'])}</td><td>{e(c['project'])}</td><td>{c['chars'] // 4:,}</td>"
                  + (f"<td class='mono'>{e(c['preview'])}</td>" if previews else "") + "</tr>" for c in stats["biggest"]) or "<tr><td colspan=4>-</td></tr>"
    loops = "".join(f"<li><b>{x['times']}&times;</b> the same failing call in one session: <code>{e(x['tool'])}</code>"
                    + (f" <span class='mono'>{e(x['preview'])}</span>" if previews else "") + f" <span class='mu'>({e(x['project'])})</span></li>" for x in stats["loops"]) \
        or "<li>No call failed three or more times with the same command in one session.</li>"
    fail_pct = round(100 * stats["errors"] / stats["calls"], 1) if stats["calls"] else 0
    cmdh = "<th>Command (secrets hidden, best effort)</th>" if previews else ""
    cmdh2 = "<th>Output ~tokens</th>" + ("<th>Command</th>" if previews else "")
    share = ("<div class='box warn'><b>Before you share this page:</b> it contains excerpts of your commands and project names. Secrets are hidden "
             "only on a best-effort basis. Re-run with <code>--no-previews</code> for a version without command text.</div>") if previews else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent report card</title><style>{_CSS}{_EXTRA_CSS}</style></head><body><main>
<p class="mu">agentdryrun scan &middot; dry run on your coding agent's history &middot; read-only, nothing left this machine</p>
<h1>Agent report card <small>{e(info['label'])}</small></h1>
<p class="mu">{info['sessions']:,} session{'' if info['sessions'] == 1 else 's'} &middot; {info['projects']:,} project{'' if info['projects'] == 1 else 's'} &middot; {info['calls']:,} tool calls &middot; {s['total']:,} actions judged &middot; period {e(_day(s['first_at']))} to {e(_day(s['last_at']))} &middot; rules: <code>{e(rules_name)}</code></p>
{('<div class="box warn"><b>' + e(banner) + '</b></div>') if banner else ''}{share}
<div class="k"><div><b>{s['total']:,}</b><span class="mu">actions judged</span></div>
<div class="ok"><b>{s['allow']:,}</b><span class="mu">would have passed</span></div>
<div class="wn"><b>{s['pending']:,}</b><span class="mu">would have needed your approval</span></div>
<div class="er"><b>{s['deny']:,}</b><span class="mu">would have been refused</span></div></div>
<p><b>{pct}%</b> of what the agent did would not have gone through on its own under these rules. Refused = the rules say never; approval = a human should decide.</p>
<h2>What kind of actions</h2><div class="tw"><table><thead><tr><th>Kind</th><th>Name in the rules</th><th>Total</th><th>Pass</th><th>Approval</th><th>Refused</th></tr></thead><tbody>{k_rows}</tbody></table></div>
<h2>Look at these first</h2><div class="tw"><table><thead><tr><th>When (UTC)</th><th>Project</th><th>What</th><th>Verdict</th><th>Why</th>{cmdh}</tr></thead><tbody>{a_rows}</tbody></table></div>
<h2>Where the output piled up</h2>
<p>The model had to read about <b>{stats['output_tokens_estimate']:,} tokens</b> of tool output in this period (characters / 4, a rough estimate), and <b>{stats['errors']:,}</b> calls ({fail_pct}%) ended in an error.</p>
<div class="tw"><table><thead><tr><th>Tool</th><th>Project</th>{cmdh2}</tr></thead><tbody>{big}</tbody></table></div>
<ul>{loops}</ul>
<div class="box warn"><b>What this report is, and is not.</b> It reads the transcripts Claude Code keeps on this machine and names what the agent <i>attempted</i>
with pattern matching on its commands, so it misses things (a script that deletes files, <code>python -c</code>, a path built at run time) and flags a few harmless ones.
It cannot know whether a command worked or what you approved. The verdicts are a simulation under a starter rules pack: edit the rules to match how you work.
Nothing was blocked or executed. It is not a security audit, a certification or legal advice. The transcript format is not a documented interface and may change.</div>
</main></body></html>"""


def main(args) -> int:
    since = None
    if args.since:
        try:
            since = _dt.datetime.fromisoformat(args.since).replace(tzinfo=_dt.timezone.utc).timestamp()
        except ValueError:
            print(f"--since must look like 2026-10-01, got {args.since!r}", file=sys.stderr)
            return 3
    elif args.days:
        since = time.time() - args.days * 86400
    rules_path = Path(args.rules) if args.rules else PACK
    try:
        policy = json.loads(rules_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"cannot read the rules: {e}", file=sys.stderr)
        return 3
    errs = validate_policy(policy)
    if errs:
        print("the rules are not valid:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 3
    try:
        got = coding.scan_transcripts(args.root, since, args.project)
    except (OSError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 3
    if not got["events"]:
        print(f"read {got['files']} transcript files: no tool calls in this period" + (f" for project '{args.project}'" if args.project else "") + ".", file=sys.stderr)
        return 3
    obs = run_shadow(policy, got["events"], agent="claude-code")
    s = summarize(obs)
    stats = waste(got["calls_info"])
    kinds = card_numbers(s, obs, got["meta"])
    label = f"last {args.days} days" if (args.days and not args.since) else (f"since {args.since}" if args.since else "all time")
    page = render_card(s=s, kinds=kinds, rows=attention_rows(obs, got["meta"]), meta=got["meta"], stats=stats,
                       info={"sessions": got["sessions"], "projects": got["projects"], "calls": got["calls"], "label": label},
                       days=args.days, previews=not args.no_previews, rules_name=rules_path.name, banner=args.banner or "")
    Path(args.out).write_text(page, encoding="utf-8", newline="\n")
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": s, "kinds": kinds, "waste": {k: v for k, v in stats.items() if k not in ("biggest", "loops")}},
                                              indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    if args.events_out:
        with open(args.events_out, "w", encoding="utf-8", newline="\n") as f:
            for ev in got["events"]:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"{got['sessions']} sessions, {got['calls']} tool calls ({label}): {s['total']} actions judged.")
    print(f"  would pass {s['allow']}   would need approval {s['pending']}   would be refused {s['deny']}")
    risky = [(t, v) for t, v in kinds.items() if t not in _QUIET and (v["pending"] or v["deny"])]
    for t, v in risky[:8]:
        print(f"  {LABEL.get(t, t):52} {v['total']:>5}  ({v['deny']} refused, {v['pending']} approval)")
    print(f"  tool output the model read: about {stats['output_tokens_estimate']:,} tokens;  {stats['errors']} of {stats['calls']} calls failed")
    print(f"report card: {args.out}   (read-only: nothing was blocked, changed or sent)")
    if not args.no_previews:
        print("note: the report contains excerpts of your commands. Use --no-previews before you share it.")
    exceeded = thresholds_exceeded(s, args.max_refused, args.max_pending, None)
    if exceeded:
        print("LIMIT EXCEEDED: " + "; ".join(exceeded), file=sys.stderr)
        return 4
    return 0
