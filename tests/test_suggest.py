"""suggest-rules: a conservative starter rules file from recorded tool calls. No network: python -m unittest"""
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

from agentdryrun import suggest  # noqa: E402
from agentdryrun.__main__ import main  # noqa: E402
from agentdryrun.policy import IRREVERSIBLE, validate_policy  # noqa: E402
from agentdryrun.report import load_events  # noqa: E402

EX = os.path.join(ROOT, "examples")


class Classification(unittest.TestCase):
    def test_read_only_names_are_the_only_ones_left_without_a_human(self):
        for name in ("get_weather", "customers.list", "searchOrders", "db.query", "status"):
            self.assertEqual(suggest.classify(name)["risk"], "low", name)
        for name in ("search_and_update", "get_and_delete", "list_then_send", "run_query", "frobnicate", "x"):
            self.assertEqual(suggest.classify(name)["risk"], "high", name)

    def test_dangerous_words_win_over_read_words(self):
        self.assertEqual(suggest.classify("get_and_delete")["reversibility"], "one_way_terminal")
        self.assertEqual(suggest.classify("payments.send")["reversibility"], "one_way_recoverable")
        self.assertEqual(suggest.classify("refunds.issue")["reversibility"], "one_way_recoverable")       # plural matches
        self.assertEqual(suggest.classify("email.send")["reversibility"], "one_way_consequential")
        self.assertEqual(suggest.classify("contracts.sign")["reversibility"], "one_way_consequential")
        self.assertEqual(suggest.classify("sendRefundEmail")["risk"], "high")                              # camelCase is split

    def test_an_irreversible_looking_tool_is_never_low_risk(self):
        for name in ("delete_user", "email.send", "contracts.sign", "dropTable", "revoke_key", "deploy_prod"):
            c = suggest.classify(name)
            if c["reversibility"] in IRREVERSIBLE:
                self.assertEqual(c["risk"], "high", name)


class Draft(unittest.TestCase):
    def test_draft_from_the_example_events_is_valid_and_conservative(self):
        doc, notes = suggest.draft(load_events(os.path.join(EX, "events.csv")))
        self.assertEqual(validate_policy(doc), [])
        self.assertEqual(doc["default_unknown_tool"], "pending")
        self.assertEqual(set(doc["tools"]), {"payments.send", "invoices.mark_paid", "contracts.sign", "vendors.bank_details.change", "email.send"})
        for name, t in doc["tools"].items():
            self.assertEqual(t["risk"], "high", name)                                    # none of these names reads as read-only
            self.assertEqual(t["approvals"], {"required": 1}, name)
            self.assertTrue(t["description"].startswith("REVIEW ME"), name)
            self.assertNotIn("limits", t)                                                # limits are never turned on silently
            self.assertNotIn("deny", t)
            self.assertNotIn("escalate", t)
        self.assertTrue(any("amount_eur" in n and "payments.send" in n for n in notes))   # numeric fields are only listed

    def test_a_read_only_tool_passes_without_approval(self):
        events = [{"tool": "weather.get", "params": {}, "occurred_at": 1.0}, {"tool": "weather.get", "params": {}, "occurred_at": 2.0}]
        doc, _ = suggest.draft(events)
        self.assertEqual(doc["tools"]["weather.get"]["risk"], "low")
        self.assertNotIn("approvals", doc["tools"]["weather.get"])

    def test_the_draft_judges_the_example_run(self):
        from agentdryrun.shadow import run_shadow
        from agentdryrun.report import summarize
        events = load_events(os.path.join(EX, "events.csv"))
        doc, _ = suggest.draft(events)
        s = summarize(run_shadow(doc, events, agent="agent"))
        self.assertEqual((s["allow"], s["deny"], s["pending"]), (0, 0, 45))               # a draft asks a human about everything it does not know


class CommandLine(unittest.TestCase):
    def test_writes_a_valid_file_and_says_it_is_a_draft(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "rules.draft.json")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["suggest-rules", "--events", os.path.join(EX, "events.csv"), "--out", out])
            self.assertEqual(rc, 0)
            text = buf.getvalue()
            self.assertIn("THIS IS A DRAFT, NOT A POLICY", text)
            self.assertIn("5 tools seen in 45 calls", text)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(validate_policy(json.load(f)), [])

    def test_reads_a_trace_export_too(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main(["suggest-rules", "--events", os.path.join(EX, "traces", "langfuse.json"), "--out", out])
            self.assertEqual(rc, 0)

    def test_unreadable_events_exit_3(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = main(["suggest-rules", "--events", os.path.join(EX, "nope.csv")])
        self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main()
