"""`scan --write-rules`: a rules file that fits what you actually do. Invented data only."""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agentdryrun import coding, profile, scan  # noqa: E402
from agentdryrun.policy import validate_policy  # noqa: E402
from agentdryrun.shadow import judge  # noqa: E402

SAMPLE = os.path.join(ROOT, "examples", "claude-code-sample", "projects")


def pack():
    with open(scan.PACK, encoding="utf-8") as f:
        return json.load(f)


def history(extra_commands, plain=300):
    """A transcript with `plain` ordinary commands and then the given extra ones."""
    cmds = [f"npm run build-{i % 7}" for i in range(plain)] + list(extra_commands)
    lines = []
    for n, c in enumerate(cmds, start=1):
        ts = "2026-10-05T10:%02d:00.000Z" % (n % 60)
        a = {"type": "assistant", "timestamp": ts, "sessionId": "s", "cwd": "/home/dev/proj",
             "message": {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{n}", "name": "Bash", "input": {"command": c}}]}}
        u = {"type": "user", "timestamp": ts, "sessionId": "s", "cwd": "/home/dev/proj",
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{n}", "content": "ok", "is_error": False}]}}
        lines += [json.dumps(a), json.dumps(u)]
    return lines


def events_of(commands, plain=300):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "p"))
        with open(os.path.join(d, "p", "s.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(history(commands, plain)) + "\n")
        return coding.scan_transcripts(d)["events"]


def verdict(policy, tool, params):
    return judge(policy, set(), "agent", tool, params, 1.0, [])


class PersonalRules(unittest.TestCase):
    def test_kinds_you_never_do_are_locked_and_kinds_you_do_are_kept(self):
        ev = events_of(["git push --force origin feature/x"])
        mine, rep = profile.personal_rules(pack(), ev, "last 90 days")
        self.assertTrue(rep["enough"])
        self.assertIn("infra.destructive", rep["locked"])
        self.assertIn("shell.sudo", rep["locked"])
        self.assertIn("git.force_push", rep["kept"])
        self.assertNotIn("git.force_push", rep["locked"])
        self.assertEqual(validate_policy(mine), [])

    def test_a_locked_kind_is_refused_with_the_reason(self):
        mine, _ = profile.personal_rules(pack(), events_of([]), "last 90 days")
        v = verdict(mine, "infra.destructive", {"tool": "terraform", "action": "destroy", "production_hint": False})
        self.assertEqual(v["decision"], "deny")
        self.assertIn("locked", v["reasons"][0])
        v = verdict(mine, "shell.sudo", {"program": "apt"})
        self.assertEqual(v["decision"], "deny")

    def test_a_kept_kind_still_follows_the_starter_rules(self):
        ev = events_of(["git push --force origin feature/x"])
        mine, _ = profile.personal_rules(pack(), ev, "last 90 days")
        v = verdict(mine, "git.force_push", {"protected_branch": False, "branch": "feature/x", "kind": "force"})
        self.assertEqual(v["decision"], "pending")                                   # a human decides, as in the starter pack
        v = verdict(mine, "git.force_push", {"protected_branch": True, "branch": "main", "kind": "force"})
        self.assertEqual(v["decision"], "deny")

    def test_ordinary_tools_are_never_locked(self):
        mine, rep = profile.personal_rules(pack(), events_of([]), "last 90 days")
        for t in ("shell.command", "file.read", "file.write", "net.fetch", "web.fetch", "agent.spawn", "mcp.call"):
            self.assertNotIn(t, rep["locked"])
        self.assertEqual(verdict(mine, "shell.command", {"program": "ls"})["decision"], "allow")

    def test_too_little_history_locks_nothing(self):
        mine, rep = profile.personal_rules(pack(), events_of([], plain=20), "last 7 days")
        self.assertFalse(rep["enough"])
        self.assertEqual(rep["locked"], [])
        self.assertEqual(mine["tools"]["infra.destructive"].get("deny", []), pack()["tools"]["infra.destructive"].get("deny", []))

    def test_the_original_pack_is_not_changed(self):
        original = pack()
        profile.personal_rules(original, events_of([]), "x")
        self.assertEqual(original, pack())


class ThroughTheCommand(unittest.TestCase):
    def run_scan(self, root, out_rules, **kw):
        ns = argparse.Namespace(root=root, days=0, since=None, project=None, rules=None, out=os.path.join(os.path.dirname(out_rules), "c.html"),
                                no_previews=True, json=None, events_out=None, max_refused=None, max_pending=None, banner=None, write_rules=out_rules)
        for k, v in kw.items():
            setattr(ns, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = scan.main(ns)
        return code, buf.getvalue()

    def test_writes_a_valid_file_and_says_what_it_locked(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "p"))
            with open(os.path.join(d, "p", "s.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(history(["git push --force origin feature/x"])) + "\n")
            out = os.path.join(d, "mine.json")
            code, text = self.run_scan(d, out)
            self.assertEqual(code, 0)
            self.assertIn("LOCKED because you never do them", text)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(validate_policy(json.load(f)), [])

    def test_the_sample_is_too_small_and_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "mine.json")
            code, text = self.run_scan(SAMPLE, out)
            self.assertEqual(code, 0)
            self.assertIn("too little history", text)

    def test_the_personal_file_is_usable_with_rules(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "p"))
            with open(os.path.join(d, "p", "s.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(history(["terraform destroy -auto-approve"])) + "\n")
            out = os.path.join(d, "mine.json")
            self.run_scan(d, out)
            code, text = self.run_scan(d, os.path.join(d, "again.json"), rules=out)
            self.assertEqual(code, 0)                                                # reads its own output as --rules


if __name__ == "__main__":
    unittest.main()
