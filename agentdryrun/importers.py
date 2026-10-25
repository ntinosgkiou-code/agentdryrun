"""Read tool calls out of trace exports (OpenTelemetry, Langfuse, LangSmith) so the shadow report can run on them.

Only TOOL calls become events: an agent's action is a tool call, the model's text and the retrieval steps are not.
Each event is {"tool", "params", "external_id", "occurred_at"}, the same shape `report.load_events` returns.

The three shapes below follow the vendors' field names, which were checked on 2026-10-24 against the primary sources
(OpenTelemetry GenAI conventions repo, Langfuse source, LangChain's run data format). The readers were run only on small
invented fixtures, NOT on exports from a live system: if your export is read wrongly, open an issue with a redacted sample.

    OpenTelemetry   OTLP/JSON (resourceSpans). A span is a tool call when `gen_ai.operation.name` is "execute_tool" or it
                    has `gen_ai.tool.name`. Arguments come from `gen_ai.tool.call.arguments` (opt-in in the convention:
                    if your instrumentation does not record them, the rules see no parameters).
    Langfuse        observations with type TOOL (list, {"data": [...]}, JSON Lines, or traces that carry "observations").
                    In the v2 API `input` is in the `io` field group, which is not returned by default: ask for fields=core,basic,io.
    LangSmith       runs with run_type "tool" (list, {"runs": [...]}, or JSON Lines).

What an export cannot tell us: whether the call succeeded, and who approved it. A failed call is still an attempted action.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

LANGFUSE_TYPES = {"SPAN", "GENERATION", "EVENT", "AGENT", "TOOL", "CHAIN", "RETRIEVER", "EVALUATOR", "EMBEDDING", "GUARDRAIL"}
MAX_TEXT = 500          # longer strings are not kept as parameters (they are prose, not fields a rule reads)


# ───────────────────────── reading the file ─────────────────────────
def _read_docs(path: str) -> list:
    """The file as JSON documents: one document, or one per non-empty line (JSON Lines)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        return [json.loads(text)]
    except ValueError:
        pass
    docs = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            docs.append(json.loads(line))
        except ValueError:
            raise ValueError(f"line {n}: not valid JSON")
    return docs


def _records(doc) -> Iterable[dict]:
    """Flatten a document into plain records: lists, {"data": []}, {"runs": []}, {"observations": []}, {"traces": []}."""
    if isinstance(doc, list):
        for d in doc:
            yield from _records(d)
    elif isinstance(doc, dict):
        if "resourceSpans" in doc or "resource_spans" in doc:
            yield doc
            return
        wrapped = False
        for key in ("data", "runs", "traces", "items"):
            if isinstance(doc.get(key), list):
                wrapped = True
                yield from _records(doc[key])
        if not wrapped:
            yield doc
        if isinstance(doc.get("observations"), list):        # a Langfuse trace that carries its observations
            for o in doc["observations"]:
                if isinstance(o, dict):
                    yield o


def detect(docs: list) -> Optional[str]:
    """'otlp', 'langfuse', 'langsmith', or None when the file is not a trace export."""
    recs = [r for d in docs for r in _records(d)]
    if any("resourceSpans" in r or "resource_spans" in r for r in recs):
        return "otlp"
    if any(isinstance(r.get("run_type"), str) for r in recs):
        return "langsmith"
    if any(isinstance(r.get("type"), str) and r["type"].upper() in LANGFUSE_TYPES and ("traceId" in r or "startTime" in r) for r in recs):
        return "langfuse"
    return None


# ───────────────────────── parameters ─────────────────────────
def _scalar(v) -> bool:
    return isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= MAX_TEXT)


def params_from(value) -> dict:
    """A tool's input as a flat dict of short scalar values. JSON text is decoded; nested objects become `a.b`;
    the Langfuse/Python `{"args": [...], "kwargs": {...}}` wrapper is unwrapped (positional args have no names, so they are dropped)."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if isinstance(value, dict) and set(value) <= {"args", "kwargs"} and isinstance(value.get("kwargs", {}), dict):
        value = value.get("kwargs", {})
    if not isinstance(value, dict):
        return {}
    out: dict = {}
    for k, v in value.items():
        if _scalar(v):
            out[str(k)] = v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if _scalar(v2):
                    out[f"{k}.{k2}"] = v2
    return out


def fields_in_rules(policy: dict) -> set:
    """Every field name a rules document looks at (the value of any "field" key, anywhere)."""
    found: set = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "field" and isinstance(v, str):
                    found.add(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(policy)
    return found


# ───────────────────────── OpenTelemetry (OTLP/JSON) ─────────────────────────
def _any(v):
    """An OTLP AnyValue as a Python value."""
    if not isinstance(v, dict):
        return v
    for k in ("stringValue", "boolValue", "doubleValue"):
        if k in v:
            return v[k]
    if "intValue" in v:                                       # int64 travels as a string in JSON
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return v["intValue"]
    if "arrayValue" in v:
        return [_any(x) for x in (v["arrayValue"] or {}).get("values", [])]
    if "kvlistValue" in v:
        return {kv.get("key"): _any(kv.get("value")) for kv in (v["kvlistValue"] or {}).get("values", [])}
    return None


def _attrs(span: dict) -> dict:
    out = {}
    for kv in span.get("attributes") or []:
        if isinstance(kv, dict) and "key" in kv:
            out[kv["key"]] = _any(kv.get("value"))
    return out


def _otlp(docs: list):
    events, spans, skipped = [], 0, 0
    for doc in docs:
        for rec in _records(doc):
            for rs in rec.get("resourceSpans") or rec.get("resource_spans") or []:
                for ss in rs.get("scopeSpans") or rs.get("scope_spans") or rs.get("instrumentationLibrarySpans") or []:
                    for sp in ss.get("spans") or []:
                        spans += 1
                        a = _attrs(sp)
                        if a.get("gen_ai.operation.name") != "execute_tool" and "gen_ai.tool.name" not in a:
                            continue
                        name = a.get("gen_ai.tool.name")
                        if not isinstance(name, str) or not name.strip():
                            n = sp.get("name") or ""
                            name = n[len("execute_tool"):].strip() if n.startswith("execute_tool") else ""
                        if not name:
                            skipped += 1
                            continue
                        ev = {"tool": name.strip(), "params": params_from(a.get("gen_ai.tool.call.arguments"))}
                        ext = a.get("gen_ai.tool.call.id") or sp.get("spanId")
                        if ext:
                            ev["external_id"] = str(ext)
                        t = sp.get("startTimeUnixNano")
                        if t not in (None, ""):
                            ev["occurred_at"] = int(t) / 1e9
                        events.append(ev)
    return events, {"format": "OpenTelemetry (OTLP/JSON)", "records": spans, "unit": "spans", "skipped_unnamed": skipped}


# ───────────────────────── Langfuse ─────────────────────────
def _event(tool, params, ext, started):
    from .report import _parse_time
    ev = {"tool": tool.strip(), "params": params}
    if ext not in (None, ""):
        ev["external_id"] = str(ext)
    t = _parse_time(started)
    if t is not None:
        ev["occurred_at"] = t
    return ev


def _langfuse(docs: list):
    events, n, skipped = [], 0, 0
    seen = set()
    for doc in docs:
        for r in _records(doc):
            if not isinstance(r.get("type"), str):
                continue
            n += 1
            if r["type"].upper() != "TOOL":
                continue
            if r.get("id") in seen:                           # a trace and a flat list can both carry the same observation
                continue
            seen.add(r.get("id"))
            name = r.get("name")
            if not isinstance(name, str) or not name.strip():
                skipped += 1
                continue
            events.append(_event(name, params_from(r.get("input")), r.get("id"), r.get("startTime")))
    return events, {"format": "Langfuse", "records": n, "unit": "observations", "skipped_unnamed": skipped}


# ───────────────────────── LangSmith ─────────────────────────
def _langsmith(docs: list):
    events, n, skipped = [], 0, 0
    for doc in docs:
        for r in _records(doc):
            if not isinstance(r.get("run_type"), str):
                continue
            n += 1
            if r["run_type"].lower() != "tool":
                continue
            name = r.get("name")
            if not isinstance(name, str) or not name.strip():
                skipped += 1
                continue
            events.append(_event(name, params_from(r.get("inputs")), r.get("id"), r.get("start_time")))
    return events, {"format": "LangSmith", "records": n, "unit": "runs", "skipped_unnamed": skipped}


# ───────────────────────── entry points ─────────────────────────
def try_load(path: str, keep_fields: Optional[set] = None):
    """(events, info) when `path` is a trace export, None when it is not (so the caller can read it as a plain events file).
    Raises ValueError when it is a trace export that contains no tool calls."""
    if Path(path).suffix.lower() == ".csv":
        return None
    try:
        docs = _read_docs(path)
    except (ValueError, UnicodeDecodeError):
        return None
    kind = detect(docs)
    if kind is None:
        return None
    events, info = {"otlp": _otlp, "langfuse": _langfuse, "langsmith": _langsmith}[kind](docs)
    if not events:
        raise ValueError(f"this is a {info['format']} export with {info['records']} {info['unit']}, but none is a tool call "
                         f"(Langfuse: type TOOL; LangSmith: run_type tool; OpenTelemetry: gen_ai.operation.name = execute_tool)")
    info["tool_calls"] = len(events)
    info["with_parameters"] = sum(1 for e in events if e["params"])      # counted before any filtering: it says what the export held
    if keep_fields is not None:
        for ev in events:
            ev["params"] = {k: v for k, v in ev["params"].items() if k in keep_fields}
    events.sort(key=lambda e: e.get("occurred_at") if e.get("occurred_at") is not None else float("inf"))
    return events, info


def main(args) -> int:
    """python -m agentdryrun import traces.json --out events.jsonl [--rules rules.json]"""
    import sys
    keep = None
    if args.rules:
        try:
            with open(args.rules, encoding="utf-8-sig") as f:
                keep = fields_in_rules(json.load(f))
        except (OSError, ValueError) as e:
            print(f"cannot read the rules file: {e}", file=sys.stderr)
            return 3
    try:
        traced = try_load(args.traces, keep)
    except (OSError, ValueError) as e:
        print(f"cannot read the traces: {e}", file=sys.stderr)
        return 3
    if traced is None:
        print("not a recognised trace export. Supported: OpenTelemetry OTLP/JSON, Langfuse observations, LangSmith runs "
              "(JSON, or JSON Lines). For a plain list of actions use a .csv or .jsonl events file (see README).", file=sys.stderr)
        return 3
    events, info = traced
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"read a {describe(info)}")
    print(f"wrote {args.out}" + ("" if keep is not None else "   (all short parameters kept; add --rules to keep only the fields your rules look at)"))
    return 0


def describe(info: dict) -> str:
    s = f"{info['format']} export: {info['records']} {info['unit']}, {info['tool_calls']} tool calls"
    if info["with_parameters"] < info["tool_calls"]:
        s += f" ({info['tool_calls'] - info['with_parameters']} without parameters: rules that need a field will send those to a human)"
    return s
