"""The shadow judge: verdicts, limits, loaders, report, command line. No platform, no network: python -m unittest"""
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

from agentdryrun import shadow  # noqa: E402
from agentdryrun.policy import validate_policy  # noqa: E402
from agentdryrun.report import load_events, render_html, summarize  # noqa: E402

DAY = 86400
T0 = 1_790_000_000.0
RULES = {
    "version": 1, "default_unknown_tool": "deny",
    "tools": {
        "payments.send": {
            "permission": "finance:pay", "reversibility": "one_way_recoverable", "risk": "high",
            "deny": [{"when": {"field": "amount_eur", "op": ">", "value": 10000}, "reason": "ceiling"}],
            "limits": [{"field": "amount_eur", "per": "day", "max": 15000, "on_exceed": "deny"}],
            "approvals": {"required": 1, "extra": [{"when": {"field": "amount_eur", "op": ">", "value": 1000}, "required": 2}]}},
        "notes.add": {"permission": "notes:write", "reversibility": "two_way", "risk": "low"},
        "refunds.issue": {"permission": "refund:issue", "reversibility": "two_way", "risk": "low",
                          "escalate": [{"when": {"field": "amount_eur", "op": ">", "value": 100}, "reason": "needs a human"}]},
    },
}
PERMS = {"finance:pay", "notes:write", "refund:issue"}


def run(events, rules=RULES, perms=PERMS):
    return shadow.run_shadow(rules, events, agent="bot", permissions=perms)


def ev(tool, params=None, at=None, ext=None):
    e = {"tool": tool, "params": params or {}}
    if at is not None:
        e["occurred_at"] = at
    if ext:
        e["external_id"] = ext
    return e


class Verdicts(unittest.TestCase):
    def test_the_rules_file_is_valid(self):
        self.assertEqual(validate_policy(RULES), [])

    def test_allow_pending_deny(self):
        o = run([ev("notes.add", at=T0), ev("payments.send", {"amount_eur": 4000, "vendor": "V"}, at=T0 + 1),
                 ev("payments.send", {"amount_eur": 20000}, at=T0 + 2)])
        self.assertEqual([x["decision"] for x in o], ["allow", "pending", "deny"])
        self.assertEqual(o[1]["approvals_required"], 2)
        self.assertEqual(o[2]["reasons"], ["ceiling"])

    def test_small_payment_needs_one_approver(self):
        o = run([ev("payments.send", {"amount_eur": 500}, at=T0)])
        self.assertEqual((o[0]["decision"], o[0]["approvals_required"]), ("pending", 1))

    def test_missing_permission_and_unknown_tool(self):
        o = run([ev("payments.send", {"amount_eur": 5}, at=T0), ev("calendar.invite", at=T0 + 1)], perms={"notes:write"})
        self.assertEqual([x["decision"] for x in o], ["deny", "deny"])
        self.assertIn("lacks permission", o[0]["reasons"][0])
        self.assertIn("is not in the policy", o[1]["reasons"][0])

    def test_unknown_tool_can_go_to_a_human_instead(self):
        rules = dict(RULES, default_unknown_tool="pending")
        o = run([ev("calendar.invite", at=T0)], rules=rules)
        self.assertEqual((o[0]["decision"], o[0]["approvals_required"]), ("pending", 1))

    def test_a_value_that_cannot_be_read_goes_to_a_human(self):
        o = run([ev("payments.send", {"amount_eur": "1_000"}, at=T0), ev("payments.send", {"vendor": "V"}, at=T0 + 1),
                 ev("payments.send", {"amount_eur": "1200.50"}, at=T0 + 2)])
        self.assertEqual([x["decision"] for x in o], ["pending", "pending", "pending"])
        self.assertTrue(any("could not be" in r for r in o[0]["reasons"]))
        self.assertEqual(o[2]["approvals_required"], 2)                    # a plain decimal string IS read as a number

    def test_escalation_rule_on_a_low_risk_tool(self):
        o = run([ev("refunds.issue", {"amount_eur": 50}, at=T0), ev("refunds.issue", {"amount_eur": 250}, at=T0 + 1)])
        self.assertEqual([x["decision"] for x in o], ["allow", "pending"])

    def test_limit_counts_what_was_reported_inside_its_own_window(self):
        o = run([ev("payments.send", {"amount_eur": 6000}, at=T0), ev("payments.send", {"amount_eur": 6000}, at=T0 + 600),
                 ev("payments.send", {"amount_eur": 6000}, at=T0 + 1200),
                 ev("payments.send", {"amount_eur": 6000}, at=T0 + 2 * DAY)])
        self.assertEqual([x["decision"] for x in o], ["pending", "pending", "deny", "pending"])
        self.assertIn("limit exceeded", o[2]["reasons"][0])

    def test_the_same_external_id_counts_once(self):
        o = run([ev("notes.add", at=T0, ext="a-1"), ev("notes.add", at=T0 + 1, ext="a-1"), ev("notes.add", at=T0 + 2, ext="a-2")])
        self.assertEqual(len(o), 2)


class Loaders(unittest.TestCase):
    def write(self, name, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return p

    def test_csv_blank_cells_are_left_out_and_events_are_sorted_by_time(self):
        p = self.write("e.csv", "tool,external_id,occurred_at,amount_eur,vendor\n"
                               "payments.send,b,2026-10-02T09:00:00,100,V\n"
                               "notes.add,a,2026-10-01T09:00:00,,\n")
        ev_ = load_events(p)
        self.assertEqual([e["tool"] for e in ev_], ["notes.add", "payments.send"])
        self.assertEqual(ev_[0]["params"], {})
        self.assertEqual(ev_[1]["params"], {"amount_eur": "100", "vendor": "V"})

    def test_jsonl(self):
        p = self.write("e.jsonl", '{"tool": "notes.add", "params": {"x": 1}, "occurred_at": 1790000000}\n\n{"tool": "refunds.issue", "amount_eur": 5}\n')
        ev_ = load_events(p)
        self.assertEqual(ev_[0]["params"], {"x": 1})
        self.assertEqual(ev_[1]["params"], {"amount_eur": 5})

    def test_errors_name_the_row(self):
        with self.assertRaises(ValueError) as cm:
            load_events(self.write("bad.csv", "tool,occurred_at\nnotes.add,yesterday-ish\n"))
        self.assertIn("row 2", str(cm.exception))
        with self.assertRaises(ValueError):
            load_events(self.write("empty.jsonl", "\n"))


class ReportAndCommand(unittest.TestCase):
    def test_report_counts_unmapped_tools_and_escapes_html(self):
        o = run([ev("notes.add", at=T0), ev("payments.send", {"amount_eur": 4000}, at=T0 + 1), ev("evil<script>", at=T0 + 2)])
        s = summarize(o)
        self.assertEqual((s["total"], s["allow"], s["pending"], s["deny"]), (3, 1, 1, 1))
        self.assertEqual(list(s["unmapped_tools"]), ["evil<script>"])
        page = render_html(s, "Acme <b>Ltd</b>", banner="demo <i>data</i>")
        self.assertNotIn("<script>", page)
        self.assertNotIn("<b>Ltd</b>", page)
        self.assertIn("nothing was stopped", page)

    def run_cli(self, rules, events):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "r.html")
        a = argparse.Namespace(rules=rules, events=events, out=out, json=None, permissions=None, agent="bot", name="T", banner=None)
        so, se = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            code = shadow.main(a)
        return code, so.getvalue(), se.getvalue(), out

    def test_the_example_files_give_the_published_numbers(self):
        code, out, err, path = self.run_cli(os.path.join(ROOT, "examples", "rules-finance.json"), os.path.join(ROOT, "examples", "events.csv"))
        self.assertEqual(code, 0)
        self.assertIn("45 events judged: 16 would pass, 20 would need approval, 9 would be refused", out)
        self.assertIn("contracts.sign (3)", out)
        self.assertTrue(os.path.exists(path))

    def test_a_bad_rules_file_is_refused_whole(self):
        d = tempfile.mkdtemp()
        bad = os.path.join(d, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "tools": {"x": {"risk": "low"}}}, f)           # reversibility is required
        code, out, err, _ = self.run_cli(bad, os.path.join(ROOT, "examples", "events.csv"))
        self.assertEqual(code, 3)
        self.assertIn("reversibility", err)


if __name__ == "__main__":
    unittest.main()
