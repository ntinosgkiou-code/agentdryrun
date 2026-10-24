"""Writes examples/traces/{otlp.json, langfuse.json, langsmith.jsonl} from examples/events.csv.

They are INVENTED, shaped after the vendors' documented field names, and contain the same 45 tool calls as events.csv
(plus a few non-tool records, so you can see them being skipped). They are not exports from a live system.

    python tools/make_trace_examples.py
"""
import csv
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "examples", "traces")


def num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in v else f
    except ValueError:
        return v


def load():
    rows = []
    with open(os.path.join(ROOT, "examples", "events.csv"), newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            when = dt.datetime.fromisoformat(r["occurred_at"]).replace(tzinfo=dt.timezone.utc)
            params = {k: num(v) for k, v in r.items() if k not in ("tool", "external_id", "occurred_at") and v}
            rows.append((r["tool"], r["external_id"], when, params))
    return rows


def otlp(rows):
    def kv(k, v):
        return {"key": k, "value": {"stringValue": v}}
    spans = []
    for i, (tool, ext, when, params) in enumerate(rows):
        ns = int(when.timestamp()) * 1_000_000_000
        spans.append({"traceId": f"{i:032x}", "spanId": f"{i + 1:016x}", "name": "chat demo-model", "kind": 3,
                      "startTimeUnixNano": str(ns - 2_000_000_000), "endTimeUnixNano": str(ns - 1_000_000_000),
                      "attributes": [kv("gen_ai.operation.name", "chat"), kv("gen_ai.request.model", "demo-model")]})
        spans.append({"traceId": f"{i:032x}", "spanId": f"{i + 1000:016x}", "name": f"execute_tool {tool}", "kind": 1,
                      "startTimeUnixNano": str(ns), "endTimeUnixNano": str(ns + 500_000_000),
                      "attributes": [kv("gen_ai.operation.name", "execute_tool"), kv("gen_ai.tool.name", tool),
                                     kv("gen_ai.tool.call.id", ext), kv("gen_ai.tool.call.arguments", json.dumps(params))]})
    return {"resourceSpans": [{"resource": {"attributes": [kv("service.name", "acme-demo-agent")]},
                               "scopeSpans": [{"scope": {"name": "demo"}, "spans": spans}]}]}


def langfuse(rows):
    data = []
    for i, (tool, ext, when, params) in enumerate(rows):
        t = when.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        data.append({"id": f"gen-{i:03d}", "traceId": f"trace-{i:03d}", "type": "GENERATION", "name": "plan-next-step",
                     "startTime": t, "input": "(model prompt)", "output": "(model answer)"})
        data.append({"id": ext, "traceId": f"trace-{i:03d}", "type": "TOOL", "name": tool, "startTime": t, "input": params, "output": {"ok": True}})
    return {"data": data, "meta": {"page": 1, "limit": len(data), "totalItems": len(data)}}


def langsmith(rows):
    out = []
    for i, (tool, ext, when, params) in enumerate(rows):
        t = when.strftime("%Y-%m-%dT%H:%M:%S")
        out.append({"id": f"llm-{i:03d}", "trace_id": f"trace-{i:03d}", "name": "demo-model", "run_type": "llm", "start_time": t,
                    "inputs": {"prompt": "(model prompt)"}, "outputs": {"text": "(model answer)"}})
        out.append({"id": ext, "trace_id": f"trace-{i:03d}", "name": tool, "run_type": "tool", "start_time": t,
                    "inputs": params, "outputs": {"ok": True}, "error": None})
    return out


def main():
    rows = load()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "otlp.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(otlp(rows), f, indent=1)
    with open(os.path.join(OUT, "langfuse.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(langfuse(rows), f, indent=1)
    with open(os.path.join(OUT, "langsmith.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for r in langsmith(rows):
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} tool calls x 3 formats to {OUT}")


if __name__ == "__main__":
    main()
