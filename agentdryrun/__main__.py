"""
python -m agentdryrun demo                                                                 the whole thing on the shipped example, one command
python -m agentdryrun scan                                                                 dry run on your own Claude Code history: one report card
python -m agentdryrun shadow --rules rules.json --events events.csv --out report.html    judge what your agent did (dry run, local)
                                                                                      (--events also takes an OpenTelemetry / Langfuse / LangSmith export)
python -m agentdryrun import traces.json --out events.jsonl                               turn a trace export into an events file
python -m agentdryrun rules check rules.json                                              validate a rules file
python -m agentdryrun witness init|run|serve|report                                       the witness service
python verify.py bundle.zip --log-key ...                                            the offline verifier (single file)
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="agentdryrun", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("shadow", help="judge what an agent already did against a rules file (dry run)")
    p.add_argument("--rules", required=True, help="the rules file (JSON); see docs/RULES.md")
    p.add_argument("--events", required=True, help="what the agent did: a .csv or .jsonl file; see README")
    p.add_argument("--out", default="shadow-report.html")
    p.add_argument("--json", help="also write the numbers as JSON")
    p.add_argument("--permissions", help="comma-separated permissions the agent really holds (default: all named in the rules)")
    p.add_argument("--agent", default="agent")
    p.add_argument("--name", default="Your company", help="name shown on the report")
    p.add_argument("--banner", help="a notice shown at the top of the report")
    p.add_argument("--max-refused", type=int, metavar="N", help="exit with code 4 if more than N actions would be refused (for CI)")
    p.add_argument("--max-pending", type=int, metavar="N", help="exit with code 4 if more than N actions would need approval (for CI)")
    p.add_argument("--max-unmapped", type=int, metavar="N", help="exit with code 4 if more than N actions use a tool no rule covers (for CI)")
    p.add_argument("--summary-md", metavar="FILE", help="also write a short Markdown summary (for a CI job summary)")

    p = sub.add_parser("scan", help="dry run on your coding agent's own history (Claude Code transcripts): one report card, read-only")
    p.add_argument("--root", help="where the transcripts are (default: ~/.claude/projects, or $CLAUDE_CONFIG_DIR/projects)")
    p.add_argument("--days", type=int, default=30, help="how many days back (default 30; 0 = everything)")
    p.add_argument("--since", help="start date instead of --days, e.g. 2026-10-01")
    p.add_argument("--project", help="only sessions whose folder contains this text")
    p.add_argument("--rules", help="your own rules file (default: the built-in coding-agent pack)")
    p.add_argument("--out", default="agent-report-card.html")
    p.add_argument("--no-previews", action="store_true", help="leave command text out of the report (use before sharing it)")
    p.add_argument("--banner", help="a notice shown at the top of the report")
    p.add_argument("--write-rules", metavar="FILE", help="also write a rules file that fits YOUR history: kinds of action you never do are locked (a proposal, not enforcement)")
    p.add_argument("--json", help="also write the numbers as JSON")
    p.add_argument("--events-out", help="also write the derived events (JSON Lines) so you can run `shadow` with your own rules")
    p.add_argument("--max-refused", type=int, metavar="N", help="exit with code 4 if more than N actions would be refused")
    p.add_argument("--max-pending", type=int, metavar="N", help="exit with code 4 if more than N actions would need approval")

    p = sub.add_parser("hook", help="EXPERIMENTAL: the same rules as `scan`, applied live as a Claude Code PreToolUse hook (reads the call on stdin)")
    p.add_argument("--rules", help="your own rules file (default: the built-in coding-agent pack)")
    p.add_argument("--mode", choices=["enforce", "observe"], default="enforce", help="observe: judge and log only, never block (start here)")
    p.add_argument("--log", metavar="FILE", help="append every decision to this JSON Lines file")
    p.add_argument("--print-settings", action="store_true", help="print the settings.json block that registers this hook, and exit")

    p = sub.add_parser("suggest-rules", help="draft a starter rules file from the tool calls you recorded (a draft to review, not a policy)")
    p.add_argument("--events", required=True, help="the events file or trace export, as for `shadow`")
    p.add_argument("--out", default="rules.draft.json")

    p = sub.add_parser("mcp-record", help="record the tool calls of an MCP server (stdio) without changing any code: mcp-record --out F -- <server command>")
    p.add_argument("--out", default="mcp-events.jsonl", help="where the events go (JSON Lines, appended)")
    p.add_argument("--rules", help="keep only the parameters these rules look at")
    p.add_argument("--fields", help="comma-separated parameter names to keep (added to the rules' fields)")
    p.add_argument("command", nargs=argparse.REMAINDER, help="the command that starts the MCP server, after --")

    p = sub.add_parser("demo", help="run the shadow report and the verifier on the shipped example (one command)")
    p.add_argument("--out", default="agentdryrun-demo-report.html", help="where to write the demo's shadow report")

    p = sub.add_parser("import", help="turn a trace export (OpenTelemetry, Langfuse, LangSmith) into an events file")
    p.add_argument("traces", help="the export: JSON or JSON Lines")
    p.add_argument("--out", default="events.jsonl")
    p.add_argument("--rules", help="keep only the parameters these rules look at (recommended before sharing the file)")

    r = sub.add_parser("rules", help="work with a rules file").add_subparsers(dest="sub", required=True)
    p = r.add_parser("check", help="validate a rules file")
    p.add_argument("file")

    wp = sub.add_parser("witness", help="run a witness for one or many logs").add_subparsers(dest="sub", required=True)
    p = wp.add_parser("init", help="create a witness key and a config skeleton")
    p.add_argument("--out", required=True)
    p.add_argument("--name", default="witness-1")
    p = wp.add_parser("run", help="check every configured log (pull mode)")
    p.add_argument("--config", required=True)
    p.add_argument("--once", action="store_true")
    p = wp.add_parser("report", help="the monthly report")
    p.add_argument("--config", required=True)
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--out", default="reports")
    p = wp.add_parser("serve", help="the witness's own HTTP service (push mode)")
    p.add_argument("--config", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8100)
    a = ap.parse_args(argv)

    if a.cmd == "shadow":
        from . import shadow
        return shadow.main(a)
    if a.cmd == "hook":
        from . import hook
        return hook.main(a)
    if a.cmd == "scan":
        from . import scan
        return scan.main(a)
    if a.cmd == "mcp-record":
        from . import mcprec
        return mcprec.main(a)
    if a.cmd == "suggest-rules":
        from . import suggest
        return suggest.main(a)
    if a.cmd == "import":
        from . import importers
        return importers.main(a)
    if a.cmd == "demo":
        from . import demo
        return demo.main(a)
    if a.cmd == "rules":
        from .policy import validate_policy
        try:
            with open(a.file, encoding="utf-8-sig") as f:
                doc = json.load(f)
        except (OSError, ValueError) as e:
            print(f"cannot read {a.file}: {e}", file=sys.stderr)
            return 3
        errs = validate_policy(doc)
        if errs:
            print("NOT VALID:\n  " + "\n  ".join(errs))
            return 2
        print(f"valid: {len(doc.get('tools', {}))} tools")
        return 0

    from . import witnessd
    if a.sub == "init":
        res = witnessd.init_witness(a.out, a.name)
        print(f"witness '{res['name']}'  public key: {res['public_key']}\nconfig: {res['config_path']}")
        return 0
    d = witnessd.WitnessDaemon(a.config)
    if a.sub == "serve":
        return d.serve(a.host, a.port)
    if a.sub == "run":
        return d.run(once=a.once)
    rep = d.monthly_report(a.month)
    print(json.dumps(witnessd.write_report(rep, a.out), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
