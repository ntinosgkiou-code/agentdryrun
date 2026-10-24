"""Trace importers: OpenTelemetry, Langfuse, LangSmith. Invented fixtures only, no network: python -m unittest"""
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

from omnios import importers, shadow  # noqa: E402
from omnios.__main__ import main  # noqa: E402
from omnios.report import load_events, summarize  # noqa: E402

EX = os.path.join(ROOT, "examples")
PERMS = {"finance:pay", "finance:vendor-admin", "finance:books"}


def write(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if isinstance(text, str) else json.dumps(text))
    return p


def example_rules():
    with open(os.path.join(EX, "rules-finance.json"), encoding="utf-8") as f:
        return json.load(f)


def otlp_span(name, attrs, start="1790000000000000000", sid="00000000000000aa"):
    kv = []
    for k, v in attrs.items():
        val = {"intValue": str(v)} if isinstance(v, int) and not isinstance(v, bool) else {"stringValue": v}
        kv.append({"key": k, "value": val})
    return {"traceId": "t" * 32, "spanId": sid, "name": name, "startTimeUnixNano": start, "attributes": kv}


def otlp_doc(*spans):
    return {"resourceSpans": [{"resource": {}, "scopeSpans": [{"scope": {}, "spans": list(spans)}]}]}


class ExamplesAgreeWithCsv(unittest.TestCase):
    """The three invented trace files carry the same 45 tool calls as events.csv, so every verdict must match."""

    def judge(self, events):
        rules = example_rules()
        s = summarize(shadow.run_shadow(rules, events, agent="agent", permissions=PERMS))
        return {k: s[k] for k in ("total", "allow", "pending", "deny")}, dict(s["unmapped_tools"])

    def test_same_verdicts_in_all_formats(self):
        ref = self.judge(load_events(os.path.join(EX, "events.csv")))
        self.assertEqual(ref[0], {"total": 45, "allow": 16, "pending": 20, "deny": 9})
        for name in ("otlp.json", "langfuse.json", "langsmith.jsonl"):
            events, info = importers.try_load(os.path.join(EX, "traces", name))
            self.assertEqual(info["tool_calls"], 45, name)
            self.assertEqual(info["records"], 90, name)           # half of the records are model calls and are skipped
            self.assertEqual(self.judge(events), ref, name)


class OpenTelemetry(unittest.TestCase):
    def test_tool_spans_only_and_int64_strings(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "t.json", otlp_doc(
                otlp_span("chat m", {"gen_ai.operation.name": "chat"}),
                otlp_span("execute_tool payments.send", {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "payments.send",
                                                          "gen_ai.tool.call.id": "call-1", "gen_ai.tool.call.arguments": '{"amount_eur": 320, "vendor": "Delta"}'}),
            ))
            events, info = importers.try_load(p)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], {"tool": "payments.send", "params": {"amount_eur": 320, "vendor": "Delta"}, "external_id": "call-1", "occurred_at": 1790000000.0})
        self.assertEqual((info["records"], info["tool_calls"]), (2, 1))

    def test_name_from_span_name_and_missing_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "t.json", otlp_doc(otlp_span("execute_tool email.send", {"gen_ai.operation.name": "execute_tool"})))
            events, info = importers.try_load(p)
        self.assertEqual(events[0]["tool"], "email.send")
        self.assertEqual(events[0]["params"], {})
        self.assertEqual(events[0]["external_id"], "00000000000000aa")      # no call id: the span id
        self.assertIn("without parameters", importers.describe(info))

    def test_array_and_kvlist_arguments(self):
        span = otlp_span("execute_tool x", {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "x"})
        span["attributes"].append({"key": "gen_ai.tool.call.arguments", "value": {"kvlistValue": {"values": [
            {"key": "amount_eur", "value": {"intValue": "5"}}, {"key": "ok", "value": {"boolValue": True}}]}}})
        with tempfile.TemporaryDirectory() as d:
            events, _ = importers.try_load(write(d, "t.json", otlp_doc(span)))
        self.assertEqual(events[0]["params"], {"amount_eur": 5, "ok": True})


class Langfuse(unittest.TestCase):
    OBS = [{"id": "o1", "traceId": "t1", "type": "TOOL", "name": "payments.send", "startTime": "2026-10-06T21:00:00.000Z", "input": {"amount_eur": 320}},
           {"id": "o2", "traceId": "t1", "type": "GENERATION", "name": "plan", "startTime": "2026-10-06T20:59:00.000Z", "input": "prompt"}]

    def load(self, text, name="o.json"):
        with tempfile.TemporaryDirectory() as d:
            return importers.try_load(write(d, name, text))

    def test_list_wrapper_and_jsonl(self):
        for text, name in ((self.OBS, "a.json"), ({"data": self.OBS, "meta": {}}, "b.json"), ("\n".join(json.dumps(o) for o in self.OBS), "c.jsonl")):
            events, info = self.load(text, name)
            self.assertEqual([e["tool"] for e in events], ["payments.send"], name)
            self.assertEqual(events[0]["occurred_at"], 1791320400.0, name)

    def test_trace_with_nested_observations_is_not_double_counted(self):
        trace = {"id": "t1", "observations": self.OBS}
        events, _ = self.load({"data": [trace, self.OBS[0]]})
        self.assertEqual(len(events), 1)

    def test_python_sdk_args_kwargs_wrapper_and_json_text(self):
        obs = [{"id": "o1", "traceId": "t", "type": "TOOL", "name": "a", "startTime": "2026-10-06T21:00:00Z", "input": {"args": ["x"], "kwargs": {"amount_eur": 7}}},
               {"id": "o2", "traceId": "t", "type": "TOOL", "name": "b", "startTime": "2026-10-06T22:00:00Z", "input": '{"amount_eur": 9}'}]
        events, _ = self.load(obs)
        self.assertEqual([e["params"] for e in events], [{"amount_eur": 7}, {"amount_eur": 9}])


class LangSmith(unittest.TestCase):
    def test_runs_wrapper_and_naive_time_is_utc(self):
        runs = {"runs": [{"id": "r1", "name": "refunds.issue", "run_type": "tool", "start_time": "2026-10-06T21:00:00", "inputs": {"amount_eur": 50}},
                         {"id": "r2", "name": "llm", "run_type": "llm", "start_time": "2026-10-06T20:00:00", "inputs": {"prompt": "x"}}]}
        with tempfile.TemporaryDirectory() as d:
            events, info = importers.try_load(write(d, "r.json", runs))
        self.assertEqual(events, [{"tool": "refunds.issue", "params": {"amount_eur": 50}, "external_id": "r1", "occurred_at": 1791320400.0}])
        self.assertEqual(info["records"], 2)


class Boundaries(unittest.TestCase):
    def test_not_a_trace_export_is_left_to_the_events_loader(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(importers.try_load(os.path.join(EX, "events.csv")))
            self.assertIsNone(importers.try_load(write(d, "e.jsonl", '{"tool": "payments.send", "params": {"amount_eur": 1}}\n')))
            self.assertIsNone(importers.try_load(write(d, "junk.json", "not json at all")))

    def test_export_without_tool_calls_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "r.json", [{"id": "r", "name": "llm", "run_type": "llm", "start_time": "2026-10-06T21:00:00"}])
            with self.assertRaises(ValueError) as cm:
                importers.try_load(p)
        self.assertIn("none is a tool call", str(cm.exception))

    def test_long_text_and_nested_objects(self):
        got = importers.params_from({"note": "x" * 600, "payment": {"amount_eur": 3, "deep": {"a": 1}}, "n": 1, "tags": [1, 2]})
        self.assertEqual(got, {"payment.amount_eur": 3, "n": 1})

    def test_fields_in_rules_and_keep_filter(self):
        fields = importers.fields_in_rules(example_rules())
        self.assertIn("amount_eur", fields)
        events, info = importers.try_load(os.path.join(EX, "traces", "langfuse.json"), keep_fields={"amount_eur"})
        self.assertTrue(all(set(e["params"]) <= {"amount_eur"} for e in events))
        self.assertTrue(any(e["params"] for e in events))
        self.assertEqual(info["with_parameters"], 45)                       # the export held parameters; filtering is not "missing"
        self.assertNotIn("without parameters", importers.describe(info))


class Cli(unittest.TestCase):
    def test_import_writes_an_events_file_the_shadow_command_reads(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "events.jsonl")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["import", os.path.join(EX, "traces", "otlp.json"), "--out", out, "--rules", os.path.join(EX, "rules-finance.json")])
            self.assertEqual(rc, 0, buf.getvalue())
            self.assertIn("45 tool calls", buf.getvalue())
            self.assertEqual(len(load_events(out)), 45)

    def test_shadow_reads_a_trace_export_directly(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["shadow", "--rules", os.path.join(EX, "rules-finance.json"), "--events", os.path.join(EX, "traces", "langsmith.jsonl"),
                           "--permissions", ",".join(sorted(PERMS)), "--out", os.path.join(d, "r.html")])
            self.assertEqual(rc, 0)
            self.assertIn("read a LangSmith export", buf.getvalue())
            self.assertIn("45 events judged: 16 would pass, 20 would need approval, 9 would be refused.", buf.getvalue())

    def test_import_refuses_a_file_it_does_not_recognise(self):
        with tempfile.TemporaryDirectory() as d:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = main(["import", os.path.join(EX, "events.csv"), "--out", os.path.join(d, "x.jsonl")])
            self.assertEqual(rc, 3)
            self.assertIn("not a recognised trace export", err.getvalue())


if __name__ == "__main__":
    unittest.main()
