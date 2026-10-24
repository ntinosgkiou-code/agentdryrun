"""
shadow.py: judge what an agent already did against a rules file, as a dry run. Nothing is blocked, nothing is executed.

    python -m omnios shadow --rules examples/rules-finance.json --events examples/events.csv --out report.html

Every reported event is judged by the same decision order the OmniOS gateway uses (permission, risk, deny rules, escalate rules,
limits, approvals). Limits count the events you reported inside their own time window (`occurred_at`), because whatever is
reported actually happened. Everything runs locally; nothing is sent anywhere.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Optional

from .canonical import canon, digest
from .policy import PERIOD_SECONDS, eval_cond, get_path, num, policy_hash, validate_policy


def judge(policy: dict, permissions: set, agent: str, tool_name: str, params: dict, at: float, history: list) -> dict:
    """One verdict: {"decision": allow|pending|deny, "risk", "approvals_required", "reasons"}."""
    tool = (policy.get("tools") or {}).get(tool_name)
    if tool is None:
        if policy.get("default_unknown_tool", "deny") == "pending":
            return {"decision": "pending", "risk": "high", "approvals_required": 1,
                    "reasons": [f"tool '{tool_name}' is not in the policy: a human decides"]}
        return {"decision": "deny", "risk": "high", "approvals_required": 0, "reasons": [f"tool '{tool_name}' is not in the policy"]}
    reasons: list = []
    need = tool.get("permission")
    if need and need not in permissions:
        return {"decision": "deny", "risk": "high", "approvals_required": 0, "reasons": [f"agent lacks permission '{need}'"]}
    risk = tool.get("risk", "high")
    if risk == "high":
        reasons.append("tool is classified high risk")
    for i, r in enumerate(tool.get("deny", [])):
        res = eval_cond(r["when"], params)
        if res is True:
            return {"decision": "deny", "risk": "high", "approvals_required": 0, "reasons": [r.get("reason", f"deny rule {i} matched")]}
        if res is None:
            risk = "high"
            reasons.append(f"deny rule {i} could not be evaluated (missing or non-numeric field): escalated to a human")
    for i, r in enumerate(tool.get("escalate", [])):
        res = eval_cond(r["when"], params)
        if res is True or res is None:
            risk = "high"
            why = r.get("reason", f"escalation rule {i}")
            reasons.append(why if res else f"{why} (could not be evaluated: escalated)")
    for lim in tool.get("limits", []):
        found, v = get_path(params, lim["field"])
        n = num(v) if found else None
        if n is None:
            risk = "high"
            reasons.append(f"limit on '{lim['field']}' could not be checked (missing or non-numeric): escalated to a human")
            continue
        used = _used(history, tool_name, lim["field"], PERIOD_SECONDS[lim["per"]], lim.get("scope", "tool"), agent, at)
        if used + n > num(lim["max"]):
            msg = f"limit exceeded: {lim['field']} {used + n} would pass {lim['max']} per {lim['per']}"
            if lim.get("on_exceed", "deny") == "deny":
                return {"decision": "deny", "risk": "high", "approvals_required": 0, "reasons": [msg]}
            risk = "high"
            reasons.append(msg + " (escalated)")
    required = 0
    if risk == "high":
        ap = tool.get("approvals", {})
        required = int(ap.get("required", 1))
        for x in ap.get("extra", []):
            res = eval_cond(x["when"], params)
            if res is True or res is None:
                required = max(required, int(x["required"]))
                reasons.append(f"{x['required']} distinct approvers required" + ("" if res else " (condition could not be evaluated)"))
    return {"decision": "pending" if risk == "high" else "allow", "risk": risk, "reasons": reasons, "approvals_required": required}


def _used(history: list, tool_name: str, field: str, window: int, scope: str, agent: str, now: float):
    from decimal import Decimal
    total = Decimal(0)
    for o in history:
        if o["tool"] != tool_name or (scope == "agent" and o["agent"] != agent):
            continue
        at = o["at"]
        if at < now - window or at > now:
            continue
        found, v = get_path(o["params"], field)
        n = num(v) if found else None
        if n is not None:
            total += n
    return total


def run_shadow(policy: dict, events: list, agent: str = "agent", permissions: Optional[set] = None) -> list:
    """Judge events (already sorted by time) and return observation records ready for report.summarize()."""
    ph = policy_hash(policy)
    if permissions is None:
        permissions = {t.get("permission") for t in (policy.get("tools") or {}).values() if t.get("permission")}
    history: list = []
    seen: set = set()
    out: list = []
    for ev in events:
        ext = ev.get("external_id")
        if ext:
            if ext in seen:
                continue
            seen.add(ext)
        tool, params = ev["tool"], ev.get("params") or {}
        if not isinstance(tool, str) or not 1 <= len(tool) <= 80:
            raise ValueError(f"invalid tool name: {tool!r}")
        if not isinstance(params, dict):
            raise ValueError(f"params of '{tool}' must be an object")
        occurred = ev.get("occurred_at")
        at = float(occurred) if occurred is not None else time.time()
        v = judge(policy, permissions, agent, tool, params, at, history)
        history.append({"tool": tool, "agent": agent, "params": params, "at": at})
        out.append({"id": f"obs-{len(out) + 1:05d}", "tool": tool, "agent": agent, "params": params, "params_digest": digest(params),
                    "decision": v["decision"], "risk": v["risk"], "approvals_required": v["approvals_required"], "reasons": v["reasons"],
                    "policy_hash": ph, "created_at": at, "occurred_at": float(occurred) if occurred is not None else None, "external_id": ext})
    return out


def main(args) -> int:
    from .report import load_events, render_html, summarize
    try:
        with open(args.rules, encoding="utf-8-sig") as f:
            policy = json.load(f)
    except (OSError, ValueError) as e:
        print(f"cannot read the rules file: {e}", file=sys.stderr)
        return 3
    errs = validate_policy(policy)
    if errs:
        print("the rules file is not valid:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 3
    try:
        from . import importers
        traced = importers.try_load(args.events)          # an OpenTelemetry / Langfuse / LangSmith export, read as it is
        if traced:
            events = traced[0]
            print("read a " + importers.describe(traced[1]))
        else:
            events = load_events(args.events)
    except (OSError, ValueError) as e:
        print(f"cannot read the events: {e}", file=sys.stderr)
        return 3
    perms = {p.strip() for p in args.permissions.split(",") if p.strip()} if args.permissions else None
    names_permissions = any(isinstance(t, dict) and t.get("permission") for t in (policy.get("tools") or {}).values())
    if perms is None and names_permissions:
        print("note: no --permissions given, so the agent is assumed to hold every permission named in the rules. "
              "Pass --permissions to test the real set.", file=sys.stderr)
    obs = run_shadow(policy, events, agent=args.agent, permissions=perms)
    s = summarize(obs)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_html(s, args.name, banner=args.banner))
    print(f"{s['total']} events judged: {s['allow']} would pass, {s['pending']} would need approval, {s['deny']} would be refused.")
    if s["unmapped_tools"]:
        print("tools the agent used that no rule covers: " + ", ".join(f"{t} ({n})" for t, n in s["unmapped_tools"].items()))
    print(f"report: {args.out}   (nothing was blocked or executed)")
    return 0
