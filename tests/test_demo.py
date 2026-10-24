"""`python -m omnios demo` runs the shadow report and the verifier on the shipped example. No network: python -m unittest"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from omnios.__main__ import main  # noqa: E402


class DemoTest(unittest.TestCase):
    def test_demo_runs_all_three_steps(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "report.html")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["demo", "--out", out])
            text = buf.getvalue()
            self.assertEqual(rc, 0, text)
            self.assertIn("45 events judged: 16 would pass, 20 would need approval, 9 would be refused.", text)
            self.assertIn("RESULT: VERIFIED", text)
            self.assertIn("RESULT: FAILED", text)
            self.assertIn("As expected", text)
            self.assertTrue(os.path.getsize(out) > 1000)


if __name__ == "__main__":
    unittest.main()
