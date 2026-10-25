"""Record what your agent does, in two lines, and judge it later with `python -m agentdryrun shadow`.

    from agentdryrun.record import Recorder
    rec = Recorder("agent-events.jsonl", rules="my-rules.json")

    @rec.tool("payments.send")
    def send_payment(amount_eur, vendor): ...

Every call to `send_payment` appends one line (tool, parameters, time, id) to the file BEFORE the function runs, then runs it
unchanged. Nothing is blocked, nothing is sent anywhere, the file is yours.

What it is, honestly:
  * It records the ATTEMPT. It does not know whether the call succeeded or who approved it.
  * Data minimisation: only short scalar parameters are kept (text over 500 characters, lists and objects are dropped) and,
    when you pass `rules=` or `fields=`, only the fields your rules look at. Names, addresses and message bodies never reach
    the file unless a rule needs them.
  * It never breaks your agent: if the file cannot be written you get ONE warning and the call goes ahead. That makes it a
    measuring tool, not a security control. Enforcement (agents that must ask first) is not part of this module.
  * A tool you forgot to wrap is invisible. Wrap them all, or use your framework's trace export instead (see `import`).
"""
from __future__ import annotations

import functools
import inspect
import json
import os
import threading
import time
import uuid
import warnings
from typing import Callable, Iterable, Optional, Union

from .importers import fields_in_rules, params_from


class Recorder:
    def __init__(self, path: Union[str, os.PathLike] = "agent-events.jsonl", *, rules: Union[None, str, os.PathLike, dict] = None,
                 fields: Optional[Iterable[str]] = None, clock: Optional[Callable[[], float]] = None):
        """path    where the events go (JSON Lines, appended)
        rules   a rules file (path or dict): keep only the parameters those rules look at
        fields  extra parameter names to keep (added to the ones the rules look at)
        clock   a function returning seconds since 1970; for tests and demos"""
        self.path = os.fspath(path)
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._warned = False
        keep = set(fields) if fields is not None else None
        if rules is not None:
            doc = rules
            if not isinstance(doc, dict):
                with open(rules, encoding="utf-8-sig") as f:
                    doc = json.load(f)
            keep = (keep or set()) | fields_in_rules(doc)
        self._keep = keep

    # ───────────────────────── writing ─────────────────────────
    def record(self, tool: str, params: Optional[dict] = None, *, external_id: Optional[str] = None,
               occurred_at: Optional[float] = None) -> dict:
        """Append one event by hand (for code that cannot be wrapped). Returns the event."""
        clean = params_from(params or {})
        if self._keep is not None:
            clean = {k: v for k, v in clean.items() if k in self._keep}
        ev = {"tool": str(tool), "params": clean, "external_id": external_id or uuid.uuid4().hex[:12],
              "occurred_at": float(occurred_at if occurred_at is not None else self._clock())}
        line = json.dumps(ev, ensure_ascii=False)
        try:
            with self._lock:
                with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(line + "\n")
        except OSError as e:
            if not self._warned:
                self._warned = True
                warnings.warn(f"agentdryrun Recorder could not write {self.path} ({e}); the agent keeps running without recording", RuntimeWarning, stacklevel=3)
        return ev

    # ───────────────────────── wrapping ─────────────────────────
    def tool(self, name: Union[None, str, Callable] = None):
        """Decorator: `@rec.tool("payments.send")`, or bare `@rec.tool` (the function's own name). Works for sync and async."""
        if callable(name):
            return self._wrap(name, None)
        return lambda fn: self._wrap(fn, name)

    def wrap(self, fn: Callable, name: Optional[str] = None) -> Callable:
        """Wrap a function you did not write: `send = rec.wrap(client.send_payment, "payments.send")`."""
        return self._wrap(fn, name)

    def _wrap(self, fn: Callable, name: Optional[str]) -> Callable:
        tool_name = name or getattr(fn, "__name__", "tool")
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            sig = None

        def arguments(args, kwargs) -> dict:
            if sig is None:
                return dict(kwargs)
            try:
                bound = sig.bind_partial(*args, **kwargs)
            except TypeError:
                return dict(kwargs)
            out: dict = {}
            for pname, value in bound.arguments.items():
                kind = sig.parameters[pname].kind
                if pname in ("self", "cls") or kind is inspect.Parameter.VAR_POSITIONAL:
                    continue
                if kind is inspect.Parameter.VAR_KEYWORD and isinstance(value, dict):
                    out.update(value)
                else:
                    out[pname] = value
            return out

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                self.record(tool_name, arguments(args, kwargs))
                return await fn(*args, **kwargs)
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            self.record(tool_name, arguments(args, kwargs))
            return fn(*args, **kwargs)
        return wrapper
