"""mcp-record: a transparent stdio proxy that records tools/call. Uses a fake MCP server; no network: python -m unittest"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agentdryrun.mcprec import calls_in  # noqa: E402
from agentdryrun.report import load_events  # noqa: E402

EX = os.path.join(ROOT, "examples")

FAKE_SERVER = r'''
import json, os, sys
log = open(os.environ["RECEIVED"], "wb")
for raw in sys.stdin.buffer:
    log.write(raw); log.flush()
    try:
        m = json.loads(raw)
    except ValueError:
        continue
    if isinstance(m, dict) and "id" in m:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": {"echo": m.get("method")}}) + "\n")
        sys.stdout.flush()
sys.stderr.write("fake server done\n")
sys.exit(7)
'''


def msg(method, id=None, params=None):
    d = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        d["id"] = id
    if params is not None:
        d["params"] = params
    return json.dumps(d)


class CallsIn(unittest.TestCase):
    def test_finds_tools_call_only(self):
        line = msg("tools/call", 3, {"name": "payments.send", "arguments": {"amount_eur": 5}}).encode()
        self.assertEqual(list(calls_in(line)), [("payments.send", {"amount_eur": 5}, 3)])
        self.assertEqual(list(calls_in(msg("tools/list", 2).encode())), [])
        self.assertEqual(list(calls_in(msg("notifications/initialized").encode())), [])
        self.assertEqual(list(calls_in(b"not json at all\n")), [])
        self.assertEqual(list(calls_in(b"\xff\xfe\n")), [])

    def test_missing_arguments_and_batches(self):
        self.assertEqual(list(calls_in(msg("tools/call", 1, {"name": "x.y"}).encode())), [("x.y", {}, 1)])
        batch = "[" + msg("tools/call", 1, {"name": "a", "arguments": {"n": 1}}) + "," + msg("tools/list", 2) + "," + msg("tools/call", 3, {"name": "b"}) + "]"
        self.assertEqual([c[0] for c in calls_in(batch.encode())], ["a", "b"])
        self.assertEqual(list(calls_in(msg("tools/call", 1, {"arguments": {}}).encode())), [])        # no tool name


class Proxy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server = os.path.join(self.tmp.name, "fake_server.py")
        with open(self.server, "w", encoding="utf-8") as f:
            f.write(FAKE_SERVER)
        self.events = os.path.join(self.tmp.name, "events.jsonl")
        self.received = os.path.join(self.tmp.name, "received.txt")
        self.input = ("\n".join([
            msg("initialize", 1, {"protocolVersion": "2025-06-18"}),
            msg("notifications/initialized"),
            msg("tools/list", 2),
            msg("tools/call", 3, {"name": "payments.send", "arguments": {"amount_eur": 320, "vendor": "Delta", "note": "x" * 600, "items": [1, 2]}}),
            msg("tools/call", 4, {"name": "files.read", "arguments": {"path": "a.txt"}}),
            "not json at all",
        ]) + "\n").encode("utf-8")

    def run_proxy(self, *extra):
        env = dict(os.environ, PYTHONPATH=ROOT, RECEIVED=self.received, PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, "-m", "agentdryrun", "mcp-record", "--out", self.events, *extra, "--", sys.executable, self.server],
                              input=self.input, capture_output=True, env=env, cwd=self.tmp.name, timeout=60)

    def test_passes_bytes_through_unchanged_and_records_only_tool_calls(self):
        r = self.run_proxy()
        self.assertEqual(r.returncode, 7, r.stderr)                                       # the server's exit code is passed on
        with open(self.received, "rb") as f:
            self.assertEqual(f.read(), self.input)                                         # the server saw exactly what the client sent
        replies = [json.loads(l) for l in r.stdout.decode("utf-8").splitlines()]
        self.assertEqual([x["id"] for x in replies], [1, 2, 3, 4])                         # and the client got exactly the server's replies
        self.assertIn(b"fake server done", r.stderr)                                       # server stderr is passed through
        self.assertIn(b"recording tools/call", r.stderr)                                   # our own notes go to stderr, never stdout
        self.assertNotIn(b"agentdryrun", r.stdout)
        events = load_events(self.events)
        self.assertEqual([e["tool"] for e in events], ["payments.send", "files.read"])
        self.assertEqual(events[0]["params"], {"amount_eur": 320, "vendor": "Delta"})      # long text and lists are never kept
        self.assertEqual(events[1]["params"], {"path": "a.txt"})

    def test_rules_limit_which_fields_reach_the_file(self):
        self.run_proxy("--rules", os.path.join(EX, "rules-finance.json"))
        events = load_events(self.events)
        self.assertEqual(events[0]["params"], {"amount_eur": 320, "vendor": "Delta"})
        self.assertEqual(events[1]["params"], {})                                          # `path` is not something the rules look at

    def test_fields_option(self):
        self.run_proxy("--fields", "path")
        events = load_events(self.events)
        self.assertEqual(events[0]["params"], {})
        self.assertEqual(events[1]["params"], {"path": "a.txt"})

    def test_the_file_is_what_the_shadow_report_reads(self):
        self.run_proxy("--rules", os.path.join(EX, "rules-finance.json"))
        env = dict(os.environ, PYTHONPATH=ROOT, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "-m", "agentdryrun", "shadow", "--rules", os.path.join(EX, "rules-finance.json"), "--events", self.events,
                            "--permissions", "finance:pay,finance:books,finance:vendor-admin", "--out", os.path.join(self.tmp.name, "r.html")],
                           capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"2 events judged", r.stdout)
        self.assertIn(b"files.read (1)", r.stdout)                                         # a tool no rule covers is reported as such

    def test_the_server_exiting_while_the_client_keeps_stdin_open_ends_cleanly(self):
        """A real client does not close our stdin. The proxy must still exit with the server's code and no interpreter crash."""
        quick = os.path.join(self.tmp.name, "quick_server.py")
        with open(quick, "w", encoding="utf-8") as f:
            f.write("import sys\nsys.stdin.readline()\nsys.stderr.write('bye\\n')\nsys.exit(5)\n")
        env = dict(os.environ, PYTHONPATH=ROOT)
        p = subprocess.Popen([sys.executable, "-m", "agentdryrun", "mcp-record", "--out", self.events, "--", sys.executable, quick],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=self.tmp.name)
        try:
            p.stdin.write((msg("tools/call", 1, {"name": "a.b", "arguments": {"n": 1}}) + "\n").encode())
            p.stdin.flush()                                                               # ...and deliberately do NOT close p.stdin
            code = p.wait(timeout=30)
            err = p.stderr.read()
        finally:
            if p.poll() is None:
                p.kill()
            for s in (p.stdin, p.stdout, p.stderr):
                try:
                    s.close()
                except OSError:
                    pass
        self.assertEqual(code, 5, err)
        self.assertNotIn(b"Fatal Python error", err)
        self.assertEqual([e["tool"] for e in load_events(self.events)], ["a.b"])           # the call was recorded before the server left

    def test_a_missing_command_fails_cleanly(self):
        env = dict(os.environ, PYTHONPATH=ROOT)
        r = subprocess.run([sys.executable, "-m", "agentdryrun", "mcp-record", "--out", self.events, "--"], input=b"", capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"put the server command after --", r.stderr)
        r = subprocess.run([sys.executable, "-m", "agentdryrun", "mcp-record", "--out", self.events, "--", "definitely-not-a-command-xyz"],
                           input=b"", capture_output=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 127)
        self.assertIn(b"cannot start the server", r.stderr)


if __name__ == "__main__":
    unittest.main()
