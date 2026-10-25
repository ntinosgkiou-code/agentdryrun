"""`python -m agentdryrun suggest-rules`: draft a starter rules file from the tool calls you recorded.

It reads the same events files as `shadow` (the Recorder's file, a CSV, or a Langfuse / LangSmith / OpenTelemetry export),
lists every tool the agent called and writes a rules file that you then REVIEW. It is a starting point, not a policy:

  * a tool whose name clearly reads as read-only (get, list, search...) is allowed without a human;
  * everything else, including every tool whose name it does not recognise, needs a human (`risk: high`);
  * a tool that looks irreversible (send, pay, delete, deploy...) is marked so and can never be `risk: low`;
  * limits are NEVER turned on: numeric parameters it saw are only listed, so you decide.

The guess comes from the tool NAME only. It cannot know what a tool really does, so read every line before you rely on it.
"""
from __future__ import annotations

import json
import re
import sys
from statistics import median

READ_WORDS = {"get", "list", "read", "search", "find", "query", "fetch", "view", "show", "describe", "check", "lookup", "count",
              "select", "retrieve", "summarize", "summarise", "inspect", "preview", "status", "history", "info"}
MONEY_WORDS = {"pay", "payment", "refund", "transfer", "charge", "wire", "withdraw", "purchase", "buy", "invoice", "payout", "bill"}
TERMINAL_WORDS = {"delete", "remove", "drop", "destroy", "purge", "wipe", "revoke", "terminate", "erase", "truncate"}
SEND_WORDS = {"send", "email", "sms", "message", "post", "publish", "share", "invite", "notify", "tweet", "broadcast", "sign", "submit", "deploy", "release"}
WRITE_WORDS = {"create", "add", "update", "set", "write", "edit", "save", "modify", "change", "book", "schedule", "reschedule", "cancel",
               "insert", "upsert", "put", "patch", "assign", "approve", "reject", "close", "open", "run", "exec", "execute", "apply",
               "commit", "push", "install", "grant", "enable", "disable", "reset", "restart", "start", "stop", "kill", "note", "tag", "label", "mark"}


def words(tool: str) -> list:
    """Split a tool name into lower-case words: `payments.sendRefund` -> payments, send, refund."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tool)
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]


def _forms(tool: str) -> set:
    """Every word, and the word without a plural `s`, so that `payments` matches `payment` and `status` still matches `status`."""
    out = set()
    for w in words(tool):
        out.add(w)
        if len(w) > 3 and w.endswith("s"):
            out.add(w[:-1])
    return out


def classify(tool: str) -> dict:
    """Conservative guess of reversibility and risk from the tool name. Anything not clearly read-only needs a human."""
    ws = _forms(tool)
    if ws & TERMINAL_WORDS:
        return {"reversibility": "one_way_terminal", "risk": "high", "why": "name suggests deleting or revoking"}
    if ws & MONEY_WORDS:
        return {"reversibility": "one_way_recoverable", "risk": "high", "why": "name suggests moving money"}
    if ws & SEND_WORDS:
        return {"reversibility": "one_way_consequential", "risk": "high", "why": "name suggests sending something out or publishing"}
    if ws & WRITE_WORDS:
        return {"reversibility": "one_way_recoverable", "risk": "high", "why": "name suggests it changes something"}
    if ws & READ_WORDS:
        return {"reversibility": "two_way", "risk": "low", "why": "name reads as read-only (check it really is)"}
    return {"reversibility": "one_way_recoverable", "risk": "high", "why": "name not recognised: left to a human"}


def _numeric(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).strip())
        return str(v).strip() not in ("", "nan", "NaN", "inf", "-inf")
    except ValueError:
        return False


def observe(events: list) -> dict:
    """Per tool: how many calls and which numeric parameters were seen (with a range)."""
    seen: dict = {}
    for e in events:
        t = seen.setdefault(e["tool"], {"calls": 0, "numeric": {}})
        t["calls"] += 1
        for k, v in (e.get("params") or {}).items():
            if _numeric(v):
                t["numeric"].setdefault(k, []).append(float(v))
    return seen


def draft(events: list) -> tuple:
    """(rules document, notes). The document always passes `rules check`."""
    seen = observe(events)
    tools = {}
    notes = []
    for tool, info in sorted(seen.items(), key=lambda kv: -kv[1]["calls"]):
        c = classify(tool)
        entry = {"description": f"REVIEW ME. Seen {info['calls']} time(s). Guess: {c['why']}.",
                 "reversibility": c["reversibility"], "risk": c["risk"]}
        if c["risk"] == "high":
            entry["approvals"] = {"required": 1}
        tools[tool] = entry
        for field, vals in info["numeric"].items():
            notes.append(f"{tool}: numeric field `{field}` seen {len(vals)} time(s), from {min(vals):g} to {max(vals):g} "
                         f"(median {median(vals):g}). Consider a deny/escalate rule or a limit.")
    doc = {"version": 1, "default_unknown_tool": "pending", "tools": tools}
    return doc, notes


def main(args) -> int:
    from .policy import validate_policy
    from .report import load_events
    from . import importers
    try:
        traced = importers.try_load(args.events)
        events = traced[0] if traced else load_events(args.events)
    except (OSError, ValueError) as e:
        print(f"cannot read the events: {e}", file=sys.stderr)
        return 3
    doc, notes = draft(events)
    errs = validate_policy(doc)
    if errs:                                    # should never happen; refuse rather than write something invalid
        print("internal error: the draft is not valid:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 2
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    allowed = sum(1 for t in doc["tools"].values() if t["risk"] == "low")
    print(f"{len(doc['tools'])} tools seen in {len(events)} calls. Draft written to {args.out}: "
          f"{allowed} look read-only (no approval), {len(doc['tools']) - allowed} need a human.")
    print("THIS IS A DRAFT, NOT A POLICY. It is guessed from tool names only: read every tool before you rely on it.")
    for n in notes[:12]:
        print("  note: " + n)
    print(f"next: python -m agentdryrun shadow --rules {args.out} --events {args.events} --out report.html")
    return 0
