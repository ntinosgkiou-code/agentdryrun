"""`python -m agentdryrun mcp-record`: record every tool call of an MCP server without changing any code.

    python -m agentdryrun mcp-record --out mcp-events.jsonl -- <the command that starts your MCP server>

It sits between an MCP client and a server that speaks the stdio transport, passes every byte through unchanged, and appends
one line per `tools/call` request to an events file that `python -m agentdryrun shadow` can judge. It works for a server
written in any language and for any client that starts the server from a command.

What it is, honestly:
  * stdio only. Servers reached over HTTP are not covered.
  * It records the ATTEMPT (the request), not whether the tool succeeded.
  * It never blocks, changes or delays a message, and it never writes to stdout (that channel belongs to the protocol:
    the MCP specification forbids anything but valid messages there). Its own notes go to stderr.
  * Only short scalar parameters are kept, and with --rules / --fields only the fields you name (see Recorder).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from typing import Iterator, Optional

from .record import Recorder


def calls_in(line: bytes) -> Iterator[tuple]:
    """(tool name, arguments, JSON-RPC id) for every `tools/call` request in one line (a message, or an old-style batch)."""
    try:
        msg = json.loads(line)
    except (ValueError, UnicodeDecodeError):
        return
    for m in (msg if isinstance(msg, list) else [msg]):
        if isinstance(m, dict) and m.get("method") == "tools/call" and isinstance(m.get("params"), dict):
            p = m["params"]
            name = p.get("name")
            if isinstance(name, str) and name:
                yield name, (p["arguments"] if isinstance(p.get("arguments"), dict) else {}), m.get("id")


def run(command: list, rec: Recorder, stdin=None, stdout=None) -> int:
    """Start the server, pass bytes both ways, record tools/call on the way in. Returns the server's exit code."""
    exe = shutil.which(command[0]) or command[0]
    try:
        proc = subprocess.Popen([exe] + command[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE)   # stderr is inherited
    except OSError as e:
        print(f"agentdryrun: cannot start the server ({e})", file=sys.stderr)
        return 127
    session = uuid.uuid4().hex[:6]
    client_in = stdin if stdin is not None else sys.stdin.buffer
    client_out = stdout if stdout is not None else sys.stdout.buffer

    def to_server() -> None:
        try:
            for line in iter(client_in.readline, b""):
                try:
                    for tool, args, rpc_id in calls_in(line):
                        rec.record(tool, args, external_id=(f"{session}-{rpc_id}" if rpc_id is not None else None))
                except Exception:                      # recording must never get in the way of the protocol
                    pass
                try:
                    proc.stdin.write(line)
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    threading.Thread(target=to_server, daemon=True).start()
    try:
        for line in iter(proc.stdout.readline, b""):
            client_out.write(line)
            client_out.flush()
    except (BrokenPipeError, OSError):
        pass
    return proc.wait()


def main(args) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("agentdryrun mcp-record: put the server command after --, for example:\n"
              "  python -m agentdryrun mcp-record --out mcp-events.jsonl -- python my_server.py", file=sys.stderr)
        return 3
    try:
        rec = Recorder(args.out, rules=args.rules, fields=(args.fields.split(",") if args.fields else None))
    except (OSError, ValueError) as e:
        print(f"agentdryrun mcp-record: cannot read the rules file ({e})", file=sys.stderr)
        return 3
    print(f"agentdryrun: recording tools/call to {args.out} (nothing is blocked or changed)", file=sys.stderr)
    code = run(command, rec)
    # A real client keeps our stdin open, so the thread that reads it may still be blocked when the server has already exited.
    # Letting the interpreter shut down around a blocked reader ends in "Fatal Python error", so leave cleanly instead.
    # Every event is written and closed before the message is forwarded, so nothing is lost by exiting here.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(code)
