"""The JavaScript recorder writes the same file the Python side judges. Skipped when Node is not installed: python -m unittest"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agentdryrun.report import load_events, summarize  # noqa: E402
from agentdryrun.shadow import run_shadow  # noqa: E402

RULES = os.path.join(ROOT, "examples", "rules-front-office.json")


@unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
class JsRecorderFeedsThePythonJudge(unittest.TestCase):
    def test_events_written_by_javascript_are_judged_by_python(self):
        with tempfile.TemporaryDirectory() as d:
            events = os.path.join(d, "events.jsonl")
            script = os.path.join(d, "make.js")
            with open(script, "w", encoding="utf-8") as f:
                f.write(f"""
const {{ Recorder }} = require({json.dumps(os.path.join(ROOT, "js", "index.js"))});
let t = 1790000000;
const rec = new Recorder({json.dumps(events)}, {{ rules: {json.dumps(RULES)}, clock: () => (t += 3600) }});
const refund = rec.tool('refunds.issue', async ({{ customer, amount_eur }}) => 'ok');
const invoice = rec.tool('invoices.create', ({{ customer, amount_eur }}) => 'ok');
refund({{ customer: 'x', amount_eur: 250 }});
invoice({{ customer: 'y', amount_eur: 5200 }});
rec.record('calendar.share', {{ with_whom: 'z' }});
""")
            r = subprocess.run(["node", script], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            evs = load_events(events)
            self.assertEqual([e["tool"] for e in evs], ["refunds.issue", "invoices.create", "calendar.share"])
            self.assertEqual(evs[0]["params"], {"amount_eur": 250})                       # `customer` is not something the rules look at
            with open(RULES, encoding="utf-8") as f:
                policy = json.load(f)
            s = summarize(run_shadow(policy, evs, agent="agent"))
            self.assertEqual((s["allow"], s["pending"], s["deny"]), (0, 2, 1))             # refund needs approvals, 5200 invoice refused, unknown tool to a human
            self.assertEqual(s["unmapped_tools"], {"calendar.share": 1})


if __name__ == "__main__":
    unittest.main()
