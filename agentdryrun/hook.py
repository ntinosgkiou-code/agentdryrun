"""`python -m agentdryrun hook`: the same rules as `scan`, applied LIVE as a Claude Code PreToolUse hook. EXPERIMENTAL.

`scan` looks back. This looks at each tool call just before Claude Code runs it and answers with the rules' verdict:

    would be refused        ->  permissionDecision "deny"   (the call is blocked; the reason is shown)
    would need approval     ->  permissionDecision "ask"    (you are asked, even if the tool was on an allow list)
    would pass              ->  no output, exit 0           (Claude Code's normal permission flow decides, exactly as without the hook)

It never answers "allow": the hook can only make things stricter, never override your own permission settings.
The protocol (stdin fields `tool_name`, `tool_input`, `cwd`; stdout `hookSpecificOutput.permissionDecision`; exit 0 with no output
means "no decision") was read from Claude Code's hooks documentation on 2026-10-26. It was exercised here with simulated calls,
NOT yet inside a live Claude Code session.

    python -m agentdryrun hook --print-settings         # the JSON to add to .claude/settings.json (or ~/.claude/settings.json)
    python -m agentdryrun hook --mode observe --log hook-log.jsonl      # judge and log only; never blocks (start here)

Limits: pattern matching on commands (it misses scripts and paths built at run time), Claude Code only, and a hook that crashes or
times out lets the call through unless you set `"onFailure": "block"` (needs a recent Claude Code). Not a sandbox.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from . import coding
from .policy import validate_policy
from .scan import LABEL, PACK
from .shadow import judge

MATCHER = "Bash|PowerShell|Read|Write|Edit|MultiEdit|NotebookEdit"
_RANK = {"allow": 0, "pending": 1, "deny": 2}


def decide(data: dict, policy: dict) -> dict:
    """The worst verdict over everything one tool call does: {"decision", "tool", "reasons", "preview"} (decision allow|pending|deny)."""
    ctx = coding.Ctx(str(data.get("cwd") or ""))
    best = {"decision": "allow", "tool": "", "reasons": [], "preview": ""}
    for tool, params, preview in coding.events_for_call(str(data.get("tool_name") or ""), data.get("tool_input") or {}, ctx):
        v = judge(policy, set(), "claude-code", tool, params, time.time(), [])
        if _RANK[v["decision"]] > _RANK[best["decision"]]:
            best = {"decision": v["decision"], "tool": tool, "reasons": v["reasons"], "preview": preview}
    return best


def hook_output(best: dict, rules_name: str) -> Optional[dict]:
    """The JSON Claude Code expects, or None for 'no decision'."""
    if best["decision"] == "allow":
        return None
    kind = LABEL.get(best["tool"], best["tool"])
    why = "; ".join(best["reasons"][:2]) or "the tool is classified high risk"
    verb = "would be refused" if best["decision"] == "deny" else "needs your approval"
    reason = f"agentdryrun ({rules_name}): {kind} {verb}: {why}. Excerpt: {best['preview'][:100]}"
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny" if best["decision"] == "deny" else "ask",
                                   "permissionDecisionReason": reason}}


def settings_snippet(mode: str = "enforce", log: Optional[str] = None, rules: Optional[str] = None) -> dict:
    """The settings.json block. Exec form (no shell), so it works the same on Windows, macOS and Linux."""
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    argv = ["hook", "--mode", mode] + (["--log", log] if log else []) + (["--rules", rules] if rules else [])
    boot = f"import sys; sys.path.insert(0, {pkg_parent!r}); from agentdryrun.__main__ import main; raise SystemExit(main({argv!r}))"
    return {"hooks": {"PreToolUse": [{"matcher": MATCHER, "hooks": [{"type": "command", "command": sys.executable, "args": ["-c", boot], "timeout": 10}]}]}}


def main(args, stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if getattr(args, "print_settings", False):
        json.dump(settings_snippet(getattr(args, "mode", "enforce"), getattr(args, "log", None), getattr(args, "rules", None)),
                  stdout, indent=2)          # ASCII-escaped on purpose: a console code page (cp1253) must not corrupt a non-ASCII path
        stdout.write("\n")
        print("# Add this to .claude/settings.json (this project) or ~/.claude/settings.json (everywhere). It is EXPERIMENTAL: print it with "
              "`--mode observe --log hook-log.jsonl` first, to see what it would do before it blocks anything.", file=sys.stderr)
        return 0
    try:
        rules_path = Path(args.rules) if args.rules else PACK
        policy = json.loads(rules_path.read_text(encoding="utf-8-sig"))
        if validate_policy(policy):
            raise ValueError("the rules file is not valid")
        data = json.loads(stdin.read())
        if not isinstance(data, dict):
            raise ValueError("the hook input is not a JSON object")
        best = decide(data, policy)
        mode = getattr(args, "mode", "enforce")
        if getattr(args, "log", None):
            with open(args.log, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"at": time.time(), "tool_name": data.get("tool_name"), "kind": best["tool"], "decision": best["decision"],
                                    "reasons": best["reasons"][:2], "preview": best["preview"][:100], "mode": mode}, ensure_ascii=False) + "\n")
        out = hook_output(best, rules_path.name)
        if out is not None and mode == "enforce":
            stdout.write(json.dumps(out))
            stdout.flush()
        return 0
    except Exception as e:                                                   # a non-blocking error for Claude Code (exit 1): the call proceeds
        print(f"agentdryrun hook: {e}", file=sys.stderr)
        return 1
