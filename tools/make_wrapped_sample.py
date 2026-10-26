"""Regenerate docs/assets/wrapped-sample.svg: the Wrapped card for the invented sample transcripts in examples/ (no real data).

    python tools/make_wrapped_sample.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "examples", "claude-code-sample", "projects")
OUT = os.path.join(ROOT, "docs", "assets", "wrapped-sample.svg")


def main() -> int:
    env = dict(os.environ, TZ="UTC0")                          # "busiest hour" in UTC so the file does not change with the machine
    with tempfile.TemporaryDirectory() as d:
        page = os.path.join(d, "w.html")
        r = subprocess.run([sys.executable, "-m", "agentdryrun", "scan", "--root", SAMPLE, "--days", "0", "--no-previews",
                            "--out", os.path.join(d, "c.html"), "--wrapped", page], capture_output=True, text=True, cwd=ROOT, env=env)
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr)
            return r.returncode
        with open(page, encoding="utf-8") as f:
            html = f.read()
    m = re.search(r"<svg id=\"card\".*?</svg>", html, re.S)
    if not m:
        print("no card found", file=sys.stderr)
        return 1
    svg = m.group(0).replace('<svg id="card"', '<svg', 1)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n")
    print("written", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
