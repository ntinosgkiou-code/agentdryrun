# Changelog

## 0.5.0 (2026-10-25)  New name: agentdryrun
- **Renamed from OmniOS to agentdryrun.** OmniOS is the name of an unrelated, actively released operating system (omnios.org), which made the project impossible to find and risked confusion. Python package, commands (`python -m agentdryrun`, `agentdryrun-verify`), repository (`ntinosgkiou-code/agentdryrun`; the old URL redirects), docs and tests all use the new name. The old repository URL keeps working through GitHub's redirect.
- **Kept on purpose:** the evidence-bundle format identifier `omnios-evidence-bundle` and the `omnios/<tenant>` origin prefix inside the signed examples. They name a format, not the project, and changing them would invalidate existing bundles.
- README leads with the problem and a one-line analogy (a dry run for AI agents, like `terraform plan`), badges for Python, dependencies and licence; "independent witness" is now "witness service" everywhere (independence depends on who runs it).
- Regenerated the demo recording, the report screenshot and the social preview image.
- **GitHub Action** (`action.yml`): runs the dry run in CI and fails the build (exit code 4) when more actions would be refused, need approval or use a tool no rule covers than you accept; writes a job summary table and uploads the HTML report. New flags on `shadow`: `--max-refused`, `--max-pending`, `--max-unmapped`, `--summary-md`. Self-tested in this repository's CI on Linux and Windows, including the failing case.
- 74 tests.

## 0.4.0 (2026-10-24)  Record your own agent
- `omnios.record.Recorder`: two lines (`@rec.tool("name")`) write an agent's tool calls to a local events file before each call runs. Sync and async, threads, `rec.wrap` for code you cannot edit. Keeps only short scalar parameters and, with `rules=`, only the fields the rules look at. Never breaks the agent (one warning if the file cannot be written). Records the attempt only.
- `examples/agent_demo.py` + `examples/rules-front-office.json`: a toy front-office assistant (50 invented calls: book, cancel, invoice, refund, message, win-back) and the rules for it; tests pin the verdicts (37 pass, 11 need approval, 2 refused) and check that names and message bodies never reach the file.
- `pyproject.toml`: `pip install git+https://github.com/ntinosgkiou-code/omnios` gives the `omnios` and `omnios-verify` commands and the `Recorder` import (checked in a clean virtual environment). Optional extra `[witness]`.
- `shadow` no longer prints the "no --permissions" note when the rules name no permission.
- 68 tests.

## 0.3.0 (2026-10-24)  Verifier hardening
Found by attacking our own verifier (`tests/test_adversarial.py`, 19 cases; an earlier exploratory run of 76 hostile bundles).
- **Fixed: silent omission.** A bundle with records removed and its unsigned `scope` label changed verified with no warning. `verify.py` now warns `INCOMPLETE` whenever the bundle holds fewer records than the signed checkpoint covers, and `--require-all` makes it a failure.
- **Fixed: crashes.** 24 of 76 hostile bundles (missing or damaged files, wrong JSON types, deep nesting) ended in a Python traceback and exit 1. They now end in a clean FAILED or unreadable result (exit 2 or 3). Never `VERIFIED`, before or after.
- **Fixed: unbounded read.** A 327 KB zip inflating to 300 MB was read whole (~600 MB of memory). Members above `--max-bytes` (default 256 MiB) are refused before reading; duplicate zip entry names and more than 64 entries are refused.
- Stricter `records.jsonl`: each record once, ascending, with correctly typed fields (repeating or swapping lines used to pass harmlessly; it now fails).
- `--log-key` and `--witness` keys are validated (32-byte base64) with a clear message.
- Docs: README no longer says the verifier checks that records were "not removed" without qualification; three rules for whoever receives a bundle; removed two references to files that exist only in the private repository.
- Importers: field names checked against the OpenTelemetry, Langfuse and LangChain primary sources; Langfuse `fields=core,basic,io` caveat documented.
- 58 tests.

## 0.2.0 (2026-10-24)
- `shadow --events` now reads **Langfuse, LangSmith and OpenTelemetry (OTLP/JSON)** trace exports directly; only tool calls are judged
- `python -m omnios import export.json [--rules rules.json] --out events.jsonl`: see what was read, keep only the parameters your rules look at
- `examples/traces/`: invented exports of the same 45 actions in the three formats; all give the same verdicts as `events.csv` (a test checks it)
- The readers follow the vendors' documented field names and are **not yet checked against real exports** (stated in the README and in `omnios/importers.py`)
- 39 tests

## 0.1.1 (2026-10-24)
- `python -m omnios demo`: the shadow report and the verifier (one bundle that verifies, one that fails) on the shipped example, in one command
- README: real clone URL, one-command quick start, terminal recording, report screenshot, CI badge
- `docs/assets/`: recording, report screenshot, social preview image; `tools/make_demo_gif.py` re-creates the recording from the real output (optional, needs Pillow)
- CI: pinned to `ubuntu-24.04` (`ubuntu-latest` no longer ships Python 3.9) and `fail-fast: false`
- 24 tests

## 0.1.0 (2026-10-24)
First public release of the open parts.
- `verify.py`: offline evidence-bundle verifier (single file, standard library only; pure-Python Ed25519 fallback)
- `omnios/witnessd.py`, `omnios/tlog.py`: independent witness and Merkle-tree/checkpoint code
- `omnios/policy.py`, `omnios/shadow.py`, `omnios/report.py`: rules language and local shadow report
- `docs/`: rules reference, bundle format, witness protocol, known limits
- `examples/`: rules, 45 invented events, a shadow report, a valid and a tampered bundle, public keys
- 23 tests (no network)
