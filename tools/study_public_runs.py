"""Judge a random sample of public coding-agent runs with the starter rules (read-only: nothing is executed).

Dataset: nebius/SWE-rebench-openhands-trajectories, CC-BY-4.0 (https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories).
Rows are read through the public datasets-server API, one small page at a time; nothing is downloaded as a whole file and
only counts and a few flagged commands are kept.

    python tools/study_public_runs.py --pages 200 --per 10 --seed 20261026 --out study.json

Needs network access. Takes about 12 minutes for 2,000 runs. See docs/VALIDATION-PUBLIC-RUNS.md for what the numbers mean.
"""
import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agentdryrun import coding  # noqa: E402
from agentdryrun.shadow import run_shadow  # noqa: E402

DATASET = "nebius/SWE-rebench-openhands-trajectories"
TOTAL_ROWS = 67074                                   # rows in the single "train" split when this was written


def fetch(offset: int, per: int) -> dict:
    q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "train", "offset": offset, "length": per})
    req = urllib.request.Request("https://datasets-server.huggingface.co/rows?" + q, headers={"User-Agent": "agentdryrun-study/1"})
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


def events_of(row: dict):
    """Turn one run into agentdryrun events. The project folder is the first /workspace/<repo> named in the task text."""
    traj = row["trajectory"]
    text = " ".join(str(x.get("content") or "") for x in traj[:4])[:40000] if traj else ""
    m = re.search(r"/workspace/[A-Za-z0-9_.\-]+", text)
    ctx = coding.Ctx(m.group(0) if m else "/workspace", home="/root")
    evs, preview, n = [], {}, 0
    for msg in traj:
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            name, raw = fn.get("name") or "", fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except ValueError:
                args = {}
            if name == "execute_bash":
                cname, cin = "Bash", {"command": args.get("command", "")}
            elif name == "str_replace_editor":
                cname = "Read" if args.get("command") == "view" else "Edit"
                cin = {"file_path": args.get("path", "")}
            elif name in ("think", "finish"):
                continue
            else:
                cname, cin = name, args
            for tool, params, shown in coding.events_for_call(cname, cin, ctx):
                n += 1
                ext = f"{row['trajectory_id']}:{n}"
                evs.append({"tool": tool, "params": params, "external_id": ext, "occurred_at": float(n)})
                preview[ext] = shown
    return evs, preview, ctx.cwd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages", type=int, default=200)
    ap.add_argument("--per", type=int, default=10, help="rows per page")
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--rules", default=str(ROOT / "agentdryrun" / "packs" / "coding-agent.json"))
    ap.add_argument("--out", default="study.json")
    a = ap.parse_args()
    policy = json.loads(Path(a.rules).read_text(encoding="utf-8-sig"))
    offsets = sorted(random.Random(a.seed).sample(range(0, TOTAL_ROWS - a.per, a.per), a.pages))
    decisions, kinds, runs_with = Counter(), defaultdict(Counter), Counter()
    examples = defaultdict(list)
    n_runs = n_actions = 0
    for i, off in enumerate(offsets, 1):
        try:
            data = fetch(off, a.per)
        except Exception as e:  # noqa: BLE001
            print(f"page {i}/{a.pages} offset {off}: failed ({type(e).__name__})", flush=True)
            continue
        for r in data.get("rows", []):
            if r.get("truncated_cells"):
                continue
            evs, shown, cwd = events_of(r["row"])
            n_runs += 1
            if not evs:
                continue
            flagged = False
            for o in run_shadow(policy, evs, agent="openhands"):
                n_actions += 1
                decisions[o["decision"]] += 1
                kinds[o["tool"]][o["decision"]] += 1
                if o["decision"] != "allow":
                    flagged = True
                    key = f"{o['tool']} / {o['decision']}"
                    if len(examples[key]) < 40:
                        examples[key].append({"command": shown.get(o["external_id"], "")[:400], "params": o["params"], "cwd": cwd})
            runs_with["flagged"] += flagged
        print(f"page {i}/{a.pages}: runs {n_runs}, actions {n_actions}", flush=True)
        time.sleep(1)
    out = {"dataset": DATASET, "license": "cc-by-4.0", "seed": a.seed, "offsets": offsets, "rows_per_page": a.per, "runs": n_runs,
           "actions_judged": n_actions, "decisions": dict(decisions), "runs_with_a_flag": runs_with["flagged"],
           "by_kind": {k: dict(v) for k, v in sorted(kinds.items(), key=lambda kv: -(kv[1]["deny"] * 1000 + kv[1]["pending"]))},
           "examples": dict(examples)}
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"done: {n_runs} runs, {n_actions} actions, {dict(decisions)}; written {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
