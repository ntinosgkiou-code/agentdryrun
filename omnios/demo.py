"""python -m omnios demo: the three things this repository does, on the shipped example, in one command.

It only reads files from examples/ and writes one HTML report. It sends nothing anywhere.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples")

# Public keys, the same ones as examples/KEYS.txt (nothing here is secret).
LOG_KEY = "MHY2fDusvOBeEJjZJngCGuF/NjHtLpGLcgrHgM0EhWA="
WITNESSES = {
    "auditor-witness": "Mwi9ce86bGM/9ctAKQeNu+bVxN9AlGJec/bNcsRab88=",
    "insurer-witness": "wh8uZprcOMB/IjMVDoLD1cVQxvYRZ8jzoXIAssy5jbg=",
}
PERMISSIONS = "finance:pay,finance:vendor-admin,finance:books"
# verify.py prints one line per action as well; the demo shows only the lines that decide the outcome.
SHOWN = ("log key pinned", "records checked", "witnesses ", "witness policy", "PROBLEM", "RESULT")


def _verify(bundle: str):
    cmd = [sys.executable, os.path.join(ROOT, "verify.py"), os.path.join(EX, bundle), "--log-key", LOG_KEY, "--min-witnesses", "2", "--require-all"]
    for name, key in WITNESSES.items():
        cmd += ["--witness", f"{name}={key}"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith(SHOWN)]
    return p.returncode, lines


def main(args) -> int:
    from . import shadow
    needed = [os.path.join(EX, n) for n in ("rules-finance.json", "events.csv", "bundle-valid.zip", "bundle-tampered.zip")]
    missing = [p for p in needed if not os.path.isfile(p)]
    if missing:
        print("the demo needs the examples/ folder of the repository; missing: " + ", ".join(os.path.basename(p) for p in missing), file=sys.stderr)
        return 3

    print("OmniOS demo: what this repository does, on the shipped example (a made-up company, invented data).\n")

    print("[1/3] Shadow report: where would the rules have stopped a payments agent?")
    ns = argparse.Namespace(rules=os.path.join(EX, "rules-finance.json"), events=os.path.join(EX, "events.csv"), out=args.out, json=None,
                            permissions=PERMISSIONS, agent="agent", name="Acme Demo Ltd", banner=None)
    rc1 = shadow.main(ns)

    print("\n[2/3] Verify the untouched evidence bundle (public keys pinned, 2 witnesses required)")
    rc2, lines2 = _verify("bundle-valid.zip")
    print("\n".join(lines2))

    print("\n[3/3] The same bundle after someone edited one approval (alice -> mallory) and re-zipped it")
    rc3, lines3 = _verify("bundle-tampered.zip")
    print("\n".join(lines3))

    ok = rc1 == 0 and rc2 == 0 and rc3 == 2
    print(f"\n{'As expected' if ok else 'UNEXPECTED'}: [2/3] VERIFIED, [3/3] FAILED.")
    print(f"Open {args.out} in a browser for the full shadow report.")
    return 0 if ok else 1
