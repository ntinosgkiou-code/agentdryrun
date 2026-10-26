"""profile.py: turn what you ACTUALLY do into a rules file that fits you (`scan --write-rules my-rules.json`).

The starter pack treats every risky kind of action the same for everyone. Your own history says more: if in the last N days
the agent never force-pushed, never read a secret file, never destroyed cloud resources, then a rule that **refuses** those
costs you nothing, and anything that suddenly tries one of them is worth a look.

What it does, and nothing more:
  * a risky kind of action that does NOT appear in your history gets a first deny rule ("locked");
  * a kind that does appear keeps the starter rules (you do it, so a human decision per case is the right default);
  * it needs enough history to mean something (MIN_ACTIONS); otherwise nothing is locked and it says so.

It is a PROPOSAL written to a file. Nothing here blocks anything by itself: the file is read by `shadow` and `scan --rules`.
"""
from __future__ import annotations

import copy
from collections import Counter

MIN_ACTIONS = 200       # fewer judged actions than this is too little to say what you "never" do

# A parameter that every event of that kind carries, so that {"field": F, "op": "exists"} is true for each of them.
ALWAYS_PRESENT = {
    "shell.delete_recursive": "scope", "shell.sudo": "program", "shell.pipe_to_shell": "fetcher", "shell.chmod_open": "program",
    "git.force_push": "kind", "git.discard_changes": "kind", "db.destructive_sql": "program", "infra.destructive": "tool",
    "package.publish": "program", "net.upload": "program", "net.remote_access": "program", "secrets.read": "via",
    "secrets.dump_env": "program",
}


def personal_rules(policy: dict, events: list, label: str) -> tuple:
    """(new_policy, report) where report = {"locked": [...], "kept": {tool: count}, "actions": n, "enough": bool}."""
    counts = Counter(e["tool"] for e in events)
    total = sum(counts.values())
    out = copy.deepcopy(policy)
    report = {"locked": [], "kept": {}, "actions": total, "enough": total >= MIN_ACTIONS, "label": label}
    for name, rules in (out.get("tools") or {}).items():
        field = ALWAYS_PRESENT.get(name)
        if field is None:
            continue
        n = counts.get(name, 0)
        if n:
            report["kept"][name] = n
            rules["description"] = f"{rules.get('description', '').rstrip('.')}. In your history ({label}) this happened {n} time(s): the starter rules apply."
            continue
        if not report["enough"]:
            continue
        rules.setdefault("deny", []).insert(0, {"when": {"field": field, "op": "exists"},
                                                "reason": f"locked: this kind of action does not appear in your history ({label}); a human should look at the first one"})
        rules["description"] = f"{rules.get('description', '').rstrip('.')}. LOCKED: never seen in your history ({label})."
        report["locked"].append(name)
    return out, report
