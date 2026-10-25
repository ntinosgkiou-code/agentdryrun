"""CI use: limits that change the exit code, and the Markdown summary for a job summary. No network: python -m unittest"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agentdryrun.__main__ import main  # noqa: E402
from agentdryrun.shadow import summary_markdown, thresholds_exceeded  # noqa: E402

EX = os.path.join(ROOT, "examples")
PERMS = "finance:pay,finance:vendor-admin,finance:books"
SUMMARY = {"total": 45, "allow": 16, "pending": 20, "deny": 9, "unmapped_tools": {"contracts.sign": 3, "email.send": 1},
           "by_tool": {"payments.send": {"total": 23, "allow": 0, "pending": 18, "deny": 5}}}


class Thresholds(unittest.TestCase):
    def test_pure_function(self):
        self.assertEqual(thresholds_exceeded(SUMMARY), [])                                   # no limits given: nothing is checked
        self.assertEqual(thresholds_exceeded(SUMMARY, max_refused=9, max_pending=20, max_unmapped=4), [])   # at the limit is fine
        over = thresholds_exceeded(SUMMARY, max_refused=8, max_pending=19, max_unmapped=3)
        self.assertEqual(len(over), 3)
        self.assertIn("9 actions would be refused, the limit is 8", over[0])
        self.assertIn("4 actions use a tool no rule covers", over[2])

    def run_main(self, *extra):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["shadow", "--rules", os.path.join(EX, "rules-finance.json"), "--events", os.path.join(EX, "events.csv"),
                       "--permissions", PERMS, "--out", os.path.join(d, "r.html"), "--summary-md", os.path.join(d, "s.md"), *extra])
        with open(os.path.join(d, "s.md"), encoding="utf-8") as f:
            md = f.read()
        return rc, out.getvalue(), err.getvalue(), md

    def test_exit_code_4_when_a_limit_is_exceeded(self):
        rc, out, err, md = self.run_main("--max-refused", "0")
        self.assertEqual(rc, 4)
        self.assertIn("LIMIT EXCEEDED: 9 actions would be refused, the limit is 0", err)
        self.assertIn("**Limits exceeded:**", md)

    def test_exit_code_0_when_within_limits(self):
        rc, out, err, md = self.run_main("--max-refused", "9", "--max-pending", "20", "--max-unmapped", "4")
        self.assertEqual(rc, 0, err)
        self.assertIn("No limit exceeded.", md)
        self.assertIn("**45 actions judged:** 16 would pass, 20 would need approval, 9 would be refused.", md)
        self.assertIn("`payments.send`", md)

    def test_no_limits_never_fails(self):
        self.assertEqual(self.run_main()[0], 0)

    def test_markdown_lists_tools_no_rule_covers(self):
        md = summary_markdown(SUMMARY, "demo", [])
        self.assertIn("`contracts.sign` (3)", md)
        self.assertTrue(md.rstrip().endswith("nothing was blocked or executed._"))


class ActionFile(unittest.TestCase):
    def test_action_yml_declares_what_the_readme_promises(self):
        with open(os.path.join(ROOT, "action.yml"), encoding="utf-8") as f:
            text = f.read()
        for needle in ('using: "composite"', "rules:", "events:", "max-refused:", "max-pending:", "max-unmapped:",
                       "python -m agentdryrun", "GITHUB_STEP_SUMMARY", "upload-artifact", "branding:"):
            self.assertIn(needle, text)
        self.assertNotIn("\t", text)                                                      # YAML must not contain tabs


if __name__ == "__main__":
    unittest.main()
