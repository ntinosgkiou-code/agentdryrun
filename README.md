# agentdryrun

[![tests](https://github.com/ntinosgkiou-code/agentdryrun/actions/workflows/tests.yml/badge.svg)](https://github.com/ntinosgkiou-code/agentdryrun/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

**What did your coding agent actually do last month?**

Anthropic reports that users accept [93% of Claude Code's manual permission prompts](https://anthropic.com/engineering/claude-code-auto-mode). That is a lot of commands nobody read. One command reads the session history Claude Code already keeps on your machine and shows what your rules **would have stopped**: recursive deletes, force pushes to `main`, `curl | sh`, secret files read, files sent to other hosts, destructive database and cloud commands. It also shows where the tool output (and so the tokens) piled up.

*Think `terraform plan`, but for what your coding agent did: read-only, local, zero dependencies, nothing is sent anywhere.*

![Terminal recording of python -m agentdryrun scan on invented sample transcripts: 48 actions judged, 24 would pass, 19 would need approval, 5 would be refused, grouped by kind](docs/assets/scan.gif)

*The real output of `scan` on the invented sample in this repository. Regenerate it with [`tools/make_demo_gif.py scan`](tools/make_demo_gif.py).*

**Try it on your own history.** Python 3.9 or newer, nothing to install, nothing leaves your machine:

```bash
git clone https://github.com/ntinosgkiou-code/agentdryrun && cd agentdryrun && python -m agentdryrun scan
```

It reads `~/.claude/projects` (last 30 days; `--days 90`, `--project my-app`, `--root PATH` to change that), prints a summary and writes `agent-report-card.html`. Add `--no-previews` before you share the page: by default it contains excerpts of your commands (secrets are hidden on a best-effort basis).

No Claude Code history yet? Try the invented sample: `python -m agentdryrun scan --root examples/claude-code-sample/projects --days 0`. [Open a sample report card](https://ntinosgkiou-code.github.io/agentdryrun/agent-report-card.html) in your browser.

![The top of a sample report card: 48 actions judged, 24 would have passed, 19 would have needed approval, 5 would have been refused, with a table by kind of action](docs/assets/report-card.png)

**What the scan is, honestly.**
- It names what the agent **attempted**, by pattern-matching its commands. It misses things (a script that deletes files, `python -c`, a path built at run time) and flags a few harmless ones. It cannot know whether a command worked or whether you approved it.
- The verdicts come from a **starter rules pack** ([`agentdryrun/packs/coding-agent.json`](agentdryrun/packs/coding-agent.json)). Copy it, change it to how you work, pass it with `--rules`. Your own history will show the pack is too strict in places and too loose in others; that is the point of a dry run.
- **Claude Code only, for now.** Reading its transcripts is based on the files as they looked on 2026-10-25; that format is not a documented interface and can change. Codex, Cursor and others are not read yet ([help wanted](https://github.com/ntinosgkiou-code/agentdryrun/issues)).
- It is not a sandbox and does not stop anything. Auto mode, permission rules and sandboxes are the tools for that; this tells you what they would have had to catch.

**Beyond coding agents.** The same dry-run engine judges any agent's tool calls (Python or JavaScript recorder, MCP proxy, Langfuse / LangSmith / OpenTelemetry exports) and can verify a tamper-evident record offline; see below.

> **Status: prototype.** No external security review. Never run with a real customer or bank. Read [what it cannot prove](docs/KNOWN-LIMITS.md) before relying on any of it.

**Jump to:** [Install](#install-2-minutes) · [Try it on the example](#1-see-where-rules-would-have-stopped-an-agent-shadow-report) · [Use it on your own data](#2-use-it-on-your-own-data) · [Verify an evidence bundle](#3-verify-an-evidence-bundle) · [Run a witness](#4-run-a-witness) · [Community vs Gateway](#community-edition-this-repo-and-the-gateway) · [Limits](#what-this-does-not-do)

---

## What you get here

| | |
|---|---|
| **`scan`** | Reads your Claude Code history and writes one report card: what the agent did, what your rules would have stopped, where the output piled up. Read-only. |
| **Recorder** | Two lines around your agent's tool functions write what it does to a local file. No vendor, no export, never breaks your agent. Python and JavaScript/TypeScript. |
| **MCP recorder** | `mcp-record` sits between your MCP client and any MCP server (stdio) and records every `tools/call`, with **no change to your agent or the server**. |
| **Rules drafter** | `suggest-rules` reads what your agent did and writes a first rules file to edit, so you do not start from a blank page. |
| **CI check (GitHub Action)** | Runs the dry run on every pull request and fails the build when the agent would do more than you accept. |
| **Shadow report** | Give it a list of what your agent did (the recorder's file, a CSV, or a **Langfuse / LangSmith / OpenTelemetry** trace export) and a rules file. It judges every action as a dry run (*would pass / would need approval / would be refused*), lists the tools your agent uses that **no rule covers**, and writes a report you can hand to a manager or an auditor. Runs locally. Nothing is blocked, nothing is sent anywhere. |
| **Offline verifier** | One Python file that checks an evidence bundle: every record it contains is unedited and in the signed tree; signed by the key you pinned; witnessed; the approval rules recorded in the log were followed; and it tells you when records are **missing** from the bundle. Hostile or malformed bundles end in FAILED, never in a crash or a false VERIFIED. |
| **Witness service** | A small service that remembers a log's checkpoints and refuses any that rewrite the past. |
| **Rules language** | The JSON format for "this tool needs two approvers above €1,000", with a strict validator. |
| **Specs and real examples** | The bundle format, the witness protocol, and a valid and a tampered bundle you can run against. |

---

## Install (2 minutes)

You need **Python 3.9 or newer**. The shadow report and the verifier need **nothing else**: no packages, no account, no network.

```bash
git clone https://github.com/ntinosgkiou-code/agentdryrun
cd agentdryrun
python -m agentdryrun demo          # the whole thing on the shipped example
python verify.py --help
python -m agentdryrun shadow --help
```

On Windows, use `py -3` instead of `python` if `python` is not found. No git? Use GitHub's **Code → Download ZIP** and unpack it.

Prefer pip? `pip install git+https://github.com/ntinosgkiou-code/agentdryrun` gives you the `agentdryrun` and `agentdryrun-verify` commands and `from agentdryrun.record import Recorder` (the demo and the examples live in the clone).

Only the witness service needs packages: `pip install -r requirements.txt` (or `pip install "agentdryrun[witness] @ git+https://github.com/ntinosgkiou-code/agentdryrun"`).

Check everything works: `python -m unittest discover -s tests` (114 tests, about twenty seconds; the JavaScript test is skipped when Node is not installed).

---

## 1. See where rules would have stopped an agent (shadow report)

The repository ships an example: a made-up company, 45 things its payments agent did over two weeks, and a rules file.

```bash
python -m agentdryrun shadow \
  --rules examples/rules-finance.json \
  --events examples/events.csv \
  --permissions finance:pay,finance:vendor-admin,finance:books \
  --name "Acme Demo Ltd" \
  --out my-report.html
```

```text
45 events judged: 16 would pass, 20 would need approval, 9 would be refused.
tools the agent used that no rule covers: contracts.sign (3), email.send (1)
report: my-report.html   (nothing was blocked or executed)
```

Open `my-report.html` in a browser. It shows the four numbers, a table by tool, why actions did not pass, and **"look at these first"**: the refused and escalated actions, newest first. A ready-made copy is in [`examples/shadow-report.html`](examples/shadow-report.html).

![The shadow report for the example: 45 actions reported, 16 would have been allowed, 20 would have needed approval, 9 would have been refused, and the two tools no rule covers](docs/assets/shadow-report.png)

*The top of the example report. It is marked SAMPLE because the company, vendors and amounts are invented.*

**How to read it.** The tools your agent uses that *no rule covers* are usually the most interesting finding: nobody decided whether it may do that. Then look at the refused actions (what would have been blocked, and why), then at the share that would have needed a human (is that a number your team could actually handle?).

---

## 2. Use it on your own data

### Your agent is Python? Record it in two lines

No export, no vendor, no change to what your agent does. Put `@rec.tool("name")` on each function the agent can call:

```python
from agentdryrun.record import Recorder

rec = Recorder("agent-events.jsonl", rules="my-rules.json")   # `rules=` keeps ONLY the parameters your rules look at

@rec.tool("refunds.issue")
def issue_refund(customer, amount_eur): ...
```

Every call appends one line to `agent-events.jsonl` *before* the function runs, then runs it unchanged. Then judge the file like any other: `python -m agentdryrun shadow --rules my-rules.json --events agent-events.jsonl`.

A complete, runnable example is [`examples/agent_demo.py`](examples/agent_demo.py): a toy front-office assistant (book, cancel, invoice, refund, message) that replays 50 invented calls, with [`examples/rules-front-office.json`](examples/rules-front-office.json):

```bash
python examples/agent_demo.py
python -m agentdryrun shadow --rules examples/rules-front-office.json --events agent-events.jsonl --out report.html
```

```text
50 events judged: 37 would pass, 11 would need approval, 2 would be refused.
tools the agent used that no rule covers: calendar.share (2)
report: report.html   (nothing was blocked or executed)
```

What the recorder is and is not:
- It records the **attempt**, not whether it succeeded or who approved it. A tool you did not wrap is invisible.
- **Data minimisation:** only short scalar parameters are kept, and with `rules=` only the fields your rules look at. In the example, customer names and message bodies never reach the file (a test checks it).
- **It never breaks your agent:** if the file cannot be written you get one warning and the call goes ahead. That makes it a measuring tool, not a security control. Making agents *ask first* is the Gateway's job, not this module's.
- Works with sync and async functions, threads, and code you cannot edit (`rec.wrap(client.send, "payments.send")`).

### Your agent is JavaScript or TypeScript? Same file, same report

```bash
npm install github:ntinosgkiou-code/agentdryrun      # zero dependencies, Node 18+
```

```js
const { Recorder } = require('agentdryrun');

const rec = new Recorder('agent-events.jsonl', { rules: 'my-rules.json' });
const issueRefund = rec.tool('refunds.issue', async ({ customer, amount_eur }) => { /* ... */ });
```

It writes exactly the file the Python side reads (`python -m agentdryrun shadow ...`). A test writes events from JavaScript and has the Python judge give the verdicts. Same limits as the Python recorder: it records the attempt, a tool you did not wrap is invisible, and a failure to write never breaks your agent. Types are in [`js/index.d.ts`](js/index.d.ts); it is **not published on npm yet**, so install it from GitHub as above.

### Your agent talks to MCP servers? Record without touching either side

[Model Context Protocol](https://modelcontextprotocol.io) servers are how many agents get their tools. `mcp-record` starts the server for you and forwards every message unchanged in both directions; it only copies the `tools/call` requests into the events file, before the server sees them.

```bash
# before: your client starts the server like this
#   python my_server.py
# after: the client starts it through agentdryrun (in the client's MCP config, "command" and "args")
python -m agentdryrun mcp-record --out mcp-events.jsonl --rules my-rules.json -- python my_server.py
python -m agentdryrun shadow --rules my-rules.json --events mcp-events.jsonl --out report.html
```

What was and was not checked:
- **Checked:** a test (`tests/test_mcp_record.py`) shows the bytes the client and server exchange are identical with and without the proxy; and between the **official MCP Python SDK** client and a server written with it, on SDK 1.30 and 2.3, the client gets the right results and both calls are recorded ([`tests/integration/mcp_sdk_check.py`](tests/integration/mcp_sdk_check.py), run in CI on Linux and Windows by [`mcp-compat.yml`](.github/workflows/mcp-compat.yml)).
- **Not checked:** desktop clients such as Claude Desktop, Cursor or VS Code, and servers written in other languages. Only the **stdio** transport exists (not HTTP). If yours misbehaves, open an issue with the client name and version.
- It records the **attempt** (name and the parameters that survive minimisation), not the result, and not whether a human approved it. It cannot stop anything: this is a measuring tool.
- Anything the server prints on stdout must be valid MCP, as the protocol requires; the proxy writes its own notes to stderr only.

### Do not know what your rules should say? Let it draft them

```bash
python -m agentdryrun suggest-rules --events agent-events.jsonl --out rules.draft.json
```

```text
5 tools seen in 45 calls. Draft written to rules.draft.json: 0 look read-only (no approval), 5 need a human.
THIS IS A DRAFT, NOT A POLICY. It is guessed from tool names only: read every tool before you rely on it.
  note: payments.send: numeric field `amount_eur` seen 21 time(s), from 240 to 12400 (median 1500). Consider a deny/escalate rule or a limit.
```

It only looks at the **names** of the tools. A tool that looks read-only (`get_`, `list_`, `search_`) gets no approval; anything that looks like paying, sending, deleting or changing, and anything it does not recognise, needs one approval. It never writes a limit, a refusal or an escalation: those depend on your business, so it prints the numbers it saw and leaves the decision to you. The file passes `rules check`, and you then run the normal `shadow` command on it. A name can lie (`get_and_delete`): that is why every entry says `REVIEW ME`.

### Already tracing your agent with Langfuse, LangSmith or OpenTelemetry? Skip step 1

Point `--events` straight at the export. The tool calls are found and judged; everything else (model calls, retrieval) is skipped.

```bash
python -m agentdryrun shadow --rules examples/rules-finance.json --events examples/traces/langfuse.json \
  --permissions finance:pay,finance:vendor-admin,finance:books --out report.html
```

```text
read a Langfuse export: 90 observations, 45 tool calls
45 events judged: 16 would pass, 20 would need approval, 9 would be refused.
tools the agent used that no rule covers: contracts.sign (3), email.send (1)
report: report.html   (nothing was blocked or executed)
```

| Your tool | What to export | What counts as a tool call |
|---|---|---|
| **Langfuse** | observations as JSON or JSON Lines (a list, `{"data": [...]}`, or traces that carry `observations`). From the v2 API ask for `fields=core,basic,io`: `input` is not in the default field groups | `type: TOOL` (name = the tool, `input` = its parameters) |
| **LangSmith** | runs as JSON or JSON Lines (a list or `{"runs": [...]}`) | `run_type: tool` (name = the tool, `inputs` = its parameters) |
| **OpenTelemetry** | OTLP/JSON (`resourceSpans`) | a span with `gen_ai.operation.name = execute_tool` or `gen_ai.tool.name`; parameters from `gen_ai.tool.call.arguments` (upstream these GenAI conventions are still marked *Development*, so names may change) |

To see what was read before judging it, or to keep only the parameters your rules look at (recommended before you share a file): `python -m agentdryrun import export.json --rules my-rules.json --out events.jsonl`.

**Read this before trusting it on your own export.**
- **What was checked, and what was not.** On 2026-10-24 the field names were checked against the primary sources: the [OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai) (`execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, and the opt-in `gen_ai.tool.call.arguments`), the [Langfuse source](https://github.com/langfuse/langfuse) (`type` `TOOL`, `startTime`, `input`) and the [LangSmith run data format](https://docs.langchain.com/langsmith/run-data-format) (`run_type` `tool`, `inputs`, `start_time`). The readers were then run only on **invented** fixtures ([`examples/traces/`](examples/traces/)), never on an export from a live system. If yours is read wrongly or not at all, open an issue with a redacted sample: that is the most useful report you can send.
- OpenTelemetry records tool **arguments** only if your instrumentation is set to (the convention makes it opt-in). Without them, rules that need a field send those actions to a human, and the tool says how many.
- Your tool names must match the names in the rules file. Names that match no rule show up under *tools the agent used that no rule covers*, which is usually the finding.
- An export does not say whether a call **succeeded** or who approved it. A failed call is still an attempted action.
- Everything runs locally, like the rest of the shadow report.

### Otherwise, step 1: write down what your agent did

A CSV file (or JSON Lines) with one row per action. Export it from your logs, your agent framework, or your payment system.

| Column | Required | What |
|---|---|---|
| `tool` | yes | the name of the action, e.g. `payments.send` |
| `occurred_at` | no | when it happened: `2026-10-01T09:30:00` (UTC) or seconds since 1970. Limits use this. Without it, "now" is used |
| `external_id` | no | your own id, so the same row is counted once |
| *anything else* | no | one column per parameter your rules look at, e.g. `amount_eur`, `vendor` |

```csv
tool,external_id,occurred_at,amount_eur,vendor
payments.send,pay-001,2026-10-06T21:00:00,320,Delta Supplies
payments.send,pay-002,2026-10-07T15:00:00,1250,Orion Logistics
invoices.mark_paid,inv-001,2026-10-07T23:00:00,,
```

Empty cells are left out. JSON Lines works too: `{"tool": "payments.send", "params": {"amount_eur": 320}, "occurred_at": "2026-10-06T21:00:00"}` on each line.

**Send only the fields your rules need.** Use internal codes instead of names or personal data. Nothing leaves your machine, but the report is a file you may share.

### Step 2: write (or copy) the rules

Start from [`examples/rules-finance.json`](examples/rules-finance.json) and change the tool names, permissions and numbers. The format is explained in [`docs/RULES.md`](docs/RULES.md). Check it:

```bash
python -m agentdryrun rules check my-rules.json
```

### Step 3: run it

```bash
python -m agentdryrun shadow --rules my-rules.json --events my-events.csv --permissions finance:pay,finance:books --out report.html
```

Pass `--permissions` with the permissions your agent **really** holds. Without it the tool assumes the agent holds every permission named in the rules, and says so.

Changing the rules and re-running takes a second. Try it: set a lower payment ceiling, run again, and see which actions flip.

### In CI: fail the build when your agent does too much

A GitHub Action runs the same dry run on every pull request and fails the build when more actions would be refused (or would need approval, or use a tool no rule covers) than you accept:

```yaml
# .github/workflows/agent-check.yml
name: agent check
on: [pull_request]
jobs:
  dry-run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ntinosgkiou-code/agentdryrun@v0.7.0
        with:
          rules: rules.json
          events: tests/agent-events.jsonl   # recorded by your tests with the Recorder, or a trace export
          max-refused: 0                     # fail if any action would be refused
          max-unmapped: 0                    # fail if the agent uses a tool no rule covers
```

It writes a table into the job summary, uploads the HTML report as an artifact and exits with code 4 when a limit is exceeded. Inputs: `rules`, `events`, `permissions`, `max-refused`, `max-pending`, `max-unmapped`, `name`, `report`, `python-version`; outputs: `total`, `would-pass`, `would-need-approval`, `would-be-refused`. The same limits work on the command line: `python -m agentdryrun shadow ... --max-refused 0` (exit code 4). The Action is tested in this repository's own CI, on Linux and Windows, including the case where it must fail ([`action-selftest.yml`](.github/workflows/action-selftest.yml)).

---

## 3. Verify an evidence bundle

An **evidence bundle** is the zip an auditor, insurer or customer receives. The repository includes two real ones. Both were made by the gateway for the same made-up company; one was then edited.

```bash
python verify.py examples/bundle-valid.zip \
  --log-key MHY2fDusvOBeEJjZJngCGuF/NjHtLpGLcgrHgM0EhWA= \
  --witness auditor-witness=Mwi9ce86bGM/9ctAKQeNu+bVxN9AlGJec/bNcsRab88= \
  --witness insurer-witness=wh8uZprcOMB/IjMVDoLD1cVQxvYRZ8jzoXIAssy5jbg= \
  --min-witnesses 2 --require-all
```

```text
tenant           acme-demo   (profile production, admin quorum 2)
log              omnios/acme-demo   size 67
log key pinned   YES
records checked  67   (signature check: cryptography)
witnesses        auditor-witness@67, insurer-witness@67   (covers records 0..66)
witness policy   at least 2   (records 0..66 are covered)
  act-00001: payments.send by ap-agent; approvers ['alice', 'bob']; proposed > approved > approved > executed
  act-00003: payments.send by ap-agent; approvers []; denied
============================================================
RESULT: VERIFIED
```

Now the same bundle after someone changed one approval (`alice` became `mallory`) and re-zipped it:

```bash
python verify.py examples/bundle-tampered.zip --log-key ... --witness ... --min-witnesses 2 --require-all
```

```text
PROBLEM  file records.jsonl does not match manifest.json
PROBLEM  record 11: text does not hash to its leaf
PROBLEM  scope 'all' promised 67 records, 66 verified
PROBLEM  RULE: action act-00001: record 13 (action.executed) happened with 1 approval(s), the rules required 2
============================================================
RESULT: FAILED
```

Editing the manifest does not help the attacker: its hash check is only a convenience. The real checks are the Merkle inclusion proofs and the signed checkpoint.

**The keys are public** and live in [`examples/KEYS.txt`](examples/KEYS.txt). In real use you obtain them from the log's owner **by another route** (a call, a signed contract). A bundle that vouches for its own key proves nothing, so without `--log-key` the verifier says `UNPINNED` and warns you.

Exit codes: `0` verified (warnings may exist), `2` failed, `3` unreadable or malformed. Flags: `--min-witnesses K`, `--max-age 36h`, `--require-all`, `--max-bytes N`, `--json`.

**Three rules for whoever receives a bundle.**
1. **Use your own copy of `verify.py`** (this repository), never the one inside the bundle: whoever made the bundle wrote that one.
2. **Ask for completeness with `--require-all`.** `manifest.json` is not signed, so its `scope` label proves nothing; someone can leave records out and relabel the scope. Without `--require-all` you still get an `INCOMPLETE` warning when the bundle holds fewer records than the signed checkpoint covers, but only the flag turns it into a failure.
3. **Pin the keys** (`--log-key`, `--witness`) from a source the log's operator does not control.

A hostile bundle is treated as hostile input: members that would inflate beyond `--max-bytes` (default 256 MiB) are refused before they are read, and wrong types, deep nesting or damaged files give a clean result. [`tests/test_adversarial.py`](tests/test_adversarial.py) runs the attacks (edited, removed, repeated and reordered records, forged leaves, proofs and checkpoints, the wrong key, stripped witnesses, relabelled scope, oversize and malformed files). That shows those attacks fail. It is not an audit.

### What `verify.py` checks

1. The bundle's files match their manifest hashes (a convenience, not a security check).
2. The checkpoint is signed by the **pinned** log key.
3. Every record: its text hashes to its leaf, the leaf is in that tree (inclusion proof, RFC 9162), the text is canonical JSON, consecutive records are chained.
4. Witness cosignatures: which trusted witnesses signed which size and when, and whether the log provably extends what they saw.
5. **Completeness:** whether the bundle holds every record the signed checkpoint covers (`INCOMPLETE` warning, or a failure with `--require-all`).
6. **The rules recorded in the log were followed:** enough distinct approvers, none of them the agent, approver groups respected, no execution before approval, and every change to rules or keys had the other admins' approvals it needed.

Full format: [`docs/EVIDENCE-BUNDLE-SPEC.md`](docs/EVIDENCE-BUNDLE-SPEC.md). Anyone can write a second verifier from that page. If it disagrees with this one on any bundle, that is a bug report ([SECURITY.md](SECURITY.md)).

---

## 4. Run a witness

A witness is a service run by **someone other than the log's operator** (an auditor, an insurer, your internal audit). It remembers the last checkpoint it accepted and cosigns a new one only with proof that it extends the old. A log that rewrites the past cannot get a witness to sign.

```bash
pip install -r requirements.txt
python -m agentdryrun witness init --out witness --name my-witness            # prints the witness's public key
python -m agentdryrun witness serve --config witness/witness.json --port 8100  # put TLS in front
```

Give the log's owner your public key and your URL. A witness only ever says *"I saw this checkpoint and it extends the previous one"*. It does **not** say the history is correct or complete. Details, independence levels and failure modes: [`docs/WITNESS.md`](docs/WITNESS.md).

**Independence is relative.** A witness you run yourself for a log you also run proves nothing about you.

---

## How it works

```text
 AI agent ──► GATEWAY ──────────────► append-only log
              rules, limits,           every step is a record
              2-person approval        leaf = SHA-256(0x00 | record)
              (commercial)             Merkle tree (RFC 9162), signed checkpoint
                                              │
                                              ▼
                                    WITNESSES (other servers, other keys)
                                    cosign a checkpoint only if it extends the
                                    last one they saw; otherwise refuse and alert
                                              │
                                              ▼
                              evidence bundle (.zip) ──► verify.py  (offline, any machine)
```

1. **Every step is a record**, written *before* the action happens: the proposal, each approval, the execution. Records carry identifiers, digests and the rule-generated reason for each decision, never raw parameters or credentials (a reason can quote a number, such as a daily total over a limit).
2. **Records form a Merkle tree**, and the log signs the tree's root with Ed25519 as a checkpoint, laid out as in the [C2SP](https://c2sp.org) signed-note and tlog-checkpoint specifications (implemented from the published text, not yet cross-checked against another implementation).
3. **Witnesses** remember checkpoints; a rewritten past cannot be witnessed.
4. **The verifier works offline from one file.** You choose the bar: which keys you trust, how many witnesses, how recent.

---

## Community edition (this repo) and the Gateway

The split is deliberate and it is the whole idea: **the part you have to trust is the part you can read.**
The Gateway produces evidence; you do not have to trust it, because the verifier here checks what it produced.

| | Community (this repository, open) | Gateway (commercial) |
|---|---|---|
| Shadow report on your own exports, locally | ✅ | ✅ (also live, continuously, through an API or one line of SDK code) |
| Rules language and validator | ✅ | ✅ |
| Verify evidence bundles offline | ✅ | ✅ |
| Run a witness | ✅ | ✅ |
| **Agents ask before acting; approvals enforced; fail-closed** | not included | ✅ |
| **Signed append-only log written for you**, evidence bundles on demand | not included | ✅ |
| Approver and admin screens, roles, two-person rule for changing the rules | not included | ✅ |
| Proxy mode (the gateway holds the credentials and makes the call) | not included | ✅ |
| Multi-customer isolation, key handling, witness pushing and monthly witness reports | witness side ✅ | ✅ |
| Rule design, pilot, set-up, support | | service |

You can inspect, run and re-implement everything needed to **check** the evidence. Running the Gateway for real, on your agent, with your rules and your approvers, is a service I provide: see [work with me](#work-with-me).

---

## What this does not do

- **It does not stop prompt injection.** The Gateway limits what a fooled agent can do *through it*, and leaves evidence of what it did. The shadow report only judges what you report.
- **An agent that never asks is invisible.** Evidence covers actions that pass through the Gateway (or that you report).
- **Approvals are not yet signed by the humans themselves.** The platform attests *"alice approved"*. Approver-held keys are the next step.
- **A false record added now is not caught by a witness.** Only rewriting the past is.
- **The shadow report sees only what you give it**, the time of an event is the one you claim, and the verdicts are a simulation. It says nothing about whether the actions were right.
- **It is not a certification** and does not make you compliant with any regulation.

The complete list is in [`docs/KNOWN-LIMITS.md`](docs/KNOWN-LIMITS.md).

## FAQ

**Is this a blockchain?** No. It is a transparency log (the design behind Certificate Transparency), with witnesses instead of consensus.

**Why not just write logs to write-once storage?** Object Lock stops deletion at the storage layer, but you still trust the cloud account, and it says nothing about order, completeness or whether the approval rules were followed. If write-once storage plus a separate security team is enough for you, you may not need this. This is for the case where a third party must check without trusting you or us.

**Why is the Gateway not open?** Because the verifier makes it unnecessary to trust. The code that produces evidence is checked by code anyone can read.

**Does the shadow report send my data anywhere?** No. It is a local command and the output is a file on your disk.

**Which standards?** RFC 9162 (Merkle trees and proofs), C2SP `signed-note` and `tlog-checkpoint`, `cosignature/v1`, Ed25519 (RFC 8032). Our witness *push* protocol is our own JSON and is **not** yet wire-compatible with the C2SP `tlog-witness` protocol.

## Repository map

```text
verify.py                    the offline verifier (single file, standard library only)
agentdryrun/demo.py               `python -m agentdryrun demo`: the shadow report and the verifier on the example, in one command
agentdryrun/scan.py, coding.py    `scan`: reads Claude Code transcripts, names what the agent did, writes the report card
agentdryrun/packs/                the starter rules pack for coding agents
examples/claude-code-sample/      invented transcripts for `scan` (made by tools/make_claude_sample.py)
agentdryrun/record.py             `Recorder`: two lines that write your agent's tool calls to a local events file
js/index.js, index.d.ts           the same recorder for JavaScript/TypeScript (zero dependencies, Node 18+)
agentdryrun/mcprec.py             `mcp-record`: a stdio proxy that records MCP `tools/call` requests unchanged
agentdryrun/suggest.py            `suggest-rules`: drafts a first rules file from what the agent did
agentdryrun/importers.py          reads tool calls from Langfuse, LangSmith and OpenTelemetry exports; the `import` command
pyproject.toml               makes `pip install git+https://github.com/ntinosgkiou-code/agentdryrun` work
agentdryrun/shadow.py             the dry-run judge and the `shadow` command
agentdryrun/report.py             the shadow report (numbers and HTML) and the CSV/JSONL loader
agentdryrun/policy.py             the rules language: validation and evaluation
agentdryrun/witnessd.py, tlog.py  the witness service and the Merkle-tree code
docs/                        RULES, EVIDENCE-BUNDLE-SPEC, WITNESS, KNOWN-LIMITS
ROADMAP.md, BUILD-LOG.md, CHANGELOG.md, CONTRIBUTING.md   how it is built, in public
examples/                    rules, events, a report, a valid and a tampered bundle, public keys
action.yml                   the GitHub Action: dry run in CI, fails the build over your limits
tests/                       114 tests, no network (test_adversarial.py attacks the verifier with hostile bundles); tests/integration/ needs `pip install mcp`
examples/agent_demo.py       a toy agent recorded with two lines; rules-front-office.json are its rules
examples/traces/             invented Langfuse, LangSmith and OpenTelemetry exports of the same 45 actions
tools/make_trace_examples.py re-creates examples/traces/ from examples/events.csv
tools/make_demo_gif.py       optional (needs Pillow): re-creates docs/assets/demo.gif from the real demo output
docs/assets/                 the recording, the report screenshot and the social preview image
```

## Built in public

This is an open-source tool built in the open. The [roadmap](ROADMAP.md) says what is done and what is next, the [build log](BUILD-LOG.md) records what worked and what was wrong (including corrections), and [CONTRIBUTING.md](CONTRIBUTING.md) lists the contributions that help most: breaking the verifier, writing a second one, and checking the Langfuse, LangSmith and OpenTelemetry readers against real exports. Issues are welcome.

## Roadmap

Approver-signed approvals (passkeys / Ed25519) · post-quantum hybrid signatures (ML-DSA, FIPS 204) alongside Ed25519 for long-lived records · C2SP witness-protocol compatibility · an independent second verifier implementation · an external security review.

## Work with me

I am looking for a few teams that run AI agents on money, customer or data flows to try the two-week pilot (you report what your agent does; you get the report and a signed record), and for auditors, insurers and consultants who are asked *"how do you prove what the agent did?"* and want to tell me how they answer today.

To talk: **open an issue titled `pilot`** or `question` in this repository (no personal details needed), or use the contact on the GitHub profile that owns it.

## License

Apache License 2.0 (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)). The Gateway is a separate commercial product and is not covered by this license.

---

### Ελληνικά (σύντομα)
Το agentdryrun δείχνει τι έκανε ένας AI agent, πού θα τον σταματούσαν οι κανόνες σου, και δίνει αποδείξεις που ελέγχει οποιοσδήποτε τρίτος **χωρίς να εμπιστευτεί το σύστημα που τις παρήγαγε**. Εδώ έχεις ό,τι μπορείς να διαβάσεις και να τρέξεις: την αναφορά «shadow» πάνω στα δικά σου δεδομένα (τοπικά, χωρίς δίκτυο), τον verifier σε ένα αρχείο Python, τον ανεξάρτητο μάρτυρα, τη γλώσσα κανόνων και παραδείγματα. Ο gateway που εφαρμόζει τους κανόνες στην πράξη και γράφει το υπογεγραμμένο αρχείο είναι υπηρεσία, όχι μέρος αυτού του repository. Είναι πρωτότυπο, χωρίς εξωτερικό έλεγχο ασφαλείας· τα όριά του είναι στο [`docs/KNOWN-LIMITS.md`](docs/KNOWN-LIMITS.md).
