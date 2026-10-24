"""Recorder: two lines of integration that write the events file the shadow report reads. No network: python -m unittest"""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from omnios.__main__ import main  # noqa: E402
from omnios.record import Recorder  # noqa: E402
from omnios.report import load_events  # noqa: E402

RULES = os.path.join(ROOT, "examples", "rules-front-office.json")


def read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class Basics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "events.jsonl")

    def test_decorator_records_before_the_call_and_returns_normally(self):
        rec = Recorder(self.path, fields={"amount_eur"})
        seen = []

        @rec.tool("payments.send")
        def send(amount_eur, vendor):
            seen.append(len(read(self.path)))               # the line is already there when the function body runs
            return "sent"

        self.assertEqual(send(320, vendor="Delta"), "sent")
        self.assertEqual(seen, [1])
        (ev,) = read(self.path)
        self.assertEqual(ev["tool"], "payments.send")
        self.assertEqual(ev["params"], {"amount_eur": 320})            # `vendor` is not in `fields`: minimised away
        self.assertTrue(ev["external_id"] and ev["occurred_at"] > 1e9)

    def test_bare_decorator_wrap_defaults_and_kwargs(self):
        rec = Recorder(self.path)                                       # no rules, no fields: all short scalars are kept

        @rec.tool
        def refund(amount_eur, note="x", **extra):
            return amount_eur

        refund(50, region="gr", payload={"nested": {"a": 1}}, items=[1, 2])
        wrapped = rec.wrap(lambda a, b: a + b, "math.add")
        self.assertEqual(wrapped(1, b=2), 3)
        evs = read(self.path)
        self.assertEqual(evs[0]["tool"], "refund")
        self.assertEqual(evs[0]["params"], {"amount_eur": 50, "region": "gr"})     # nested objects and lists are dropped, the unused default too
        self.assertEqual((evs[1]["tool"], evs[1]["params"]), ("math.add", {"a": 1, "b": 2}))

    def test_long_text_is_never_kept(self):
        rec = Recorder(self.path)
        rec.record("messages.send", {"recipients": 3, "body": "x" * 600})
        self.assertEqual(read(self.path)[0]["params"], {"recipients": 3})

    def test_rules_decide_which_fields_survive(self):
        rec = Recorder(self.path, rules=RULES)
        rec.record("invoices.create", {"customer": "Jane Doe", "amount_eur": 450, "address": "somewhere"})
        self.assertEqual(read(self.path)[0]["params"], {"amount_eur": 450})
        rec2 = Recorder(self.path, rules=RULES, fields={"customer"})    # an explicit extra field is added to the rules' fields
        rec2.record("invoices.create", {"customer": "C-1", "amount_eur": 1})
        self.assertEqual(read(self.path)[1]["params"], {"customer": "C-1", "amount_eur": 1})

    def test_async_functions_are_recorded_and_awaited(self):
        rec = Recorder(self.path)

        @rec.tool("jobs.run")
        async def run(job_id):
            await asyncio.sleep(0)
            return job_id * 2

        self.assertEqual(asyncio.run(run(21)), 42)
        self.assertEqual(read(self.path)[0]["params"], {"job_id": 21})

    def test_an_exception_in_the_tool_is_not_swallowed_and_the_attempt_is_recorded(self):
        rec = Recorder(self.path)

        @rec.tool("payments.send")
        def boom(amount_eur):
            raise RuntimeError("bank down")

        with self.assertRaises(RuntimeError):
            boom(10)
        self.assertEqual(len(read(self.path)), 1)

    def test_never_breaks_the_agent_when_the_file_cannot_be_written(self):
        bad = os.path.join(self.tmp.name, "no-such-dir", "events.jsonl")
        rec = Recorder(bad)

        @rec.tool("payments.send")
        def send(amount_eur):
            return "sent"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(send(1), "sent")
            self.assertEqual(send(2), "sent")
        self.assertEqual(len([w for w in caught if issubclass(w.category, RuntimeWarning)]), 1)   # one warning, not one per call

    def test_threads_do_not_interleave_lines(self):
        rec = Recorder(self.path)

        def work(k):
            for i in range(50):
                rec.record("t.call", {"worker": k, "i": i})

        threads = [threading.Thread(target=work, args=(k,)) for k in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(read(self.path)), 400)

    def test_the_file_is_what_the_shadow_loader_reads(self):
        rec = Recorder(self.path, rules=RULES, clock=iter([1790000000.0, 1790000100.0]).__next__)
        rec.record("refunds.issue", {"amount_eur": 80})
        rec.record("appointments.book", {"customer": "C-1"})
        events = load_events(self.path)
        self.assertEqual([e["tool"] for e in events], ["refunds.issue", "appointments.book"])
        self.assertEqual(events[0]["params"], {"amount_eur": 80})
        self.assertEqual(events[1]["occurred_at"], 1790000100.0)


class TheDemo(unittest.TestCase):
    def test_the_example_agent_and_its_rules_give_the_documented_verdicts(self):
        spec = importlib.util.spec_from_file_location("agent_demo", os.path.join(ROOT, "examples", "agent_demo.py"))
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        with tempfile.TemporaryDirectory() as d:
            events_path = os.path.join(d, "agent-events.jsonl")
            with contextlib.redirect_stdout(io.StringIO()):
                n = demo.main(events_path)
            self.assertEqual(n, 50)
            with open(events_path, encoding="utf-8") as f:
                raw = f.read()
            self.assertNotIn("Customer 0", raw)                         # names never reach the file
            self.assertNotIn("never recorded", raw)                     # nor do message bodies
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["shadow", "--rules", demo.RULES, "--events", events_path, "--out", os.path.join(d, "r.html")])
            self.assertEqual(rc, 0)
            self.assertIn("50 events judged: 37 would pass, 11 would need approval, 2 would be refused.", out.getvalue())
            self.assertIn("calendar.share (2)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
