"""
python -m omnios demo                                                                 the whole thing on the shipped example, one command
python -m omnios shadow --rules rules.json --events events.csv --out report.html    judge what your agent did (dry run, local)
                                                                                      (--events also takes an OpenTelemetry / Langfuse / LangSmith export)
python -m omnios import traces.json --out events.jsonl                               turn a trace export into an events file
python -m omnios rules check rules.json                                              validate a rules file
python -m omnios witness init|run|serve|report                                       the independent witness
python verify.py bundle.zip --log-key ...                                            the offline verifier (single file)
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="omnios", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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

    p = sub.add_parser("demo", help="run the shadow report and the verifier on the shipped example (one command)")
    p.add_argument("--out", default="omnios-demo-report.html", help="where to write the demo's shadow report")

    p = sub.add_parser("import", help="turn a trace export (OpenTelemetry, Langfuse, LangSmith) into an events file")
    p.add_argument("traces", help="the export: JSON or JSON Lines")
    p.add_argument("--out", default="events.jsonl")
    p.add_argument("--rules", help="keep only the parameters these rules look at (recommended before sharing the file)")

    r = sub.add_parser("rules", help="work with a rules file").add_subparsers(dest="sub", required=True)
    p = r.add_parser("check", help="validate a rules file")
    p.add_argument("file")

    wp = sub.add_parser("witness", help="run an independent witness for one or many logs").add_subparsers(dest="sub", required=True)
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
