# Build log

A dated, honest log of what was built, what worked, and what was wrong. Newest first. Nothing here is a customer story: there are none yet.

## 2026-10-24 (late night): the recorder
- **Why:** every way in so far needed an export or a hand-made CSV. The shortest path from "I have an agent" to "show me what it would have needed approval for" is two lines of code around its tool functions.
- **Built** `omnios.record.Recorder`, a front-office example with rules, and `pyproject.toml` so `pip install git+...` works. Checked the install in a clean virtual environment and ran `omnios`, `omnios-verify` and `Recorder` from another directory.
- **Honest limits, also in the README:** it records attempts, not outcomes or approvals; a tool you forget to wrap is invisible; it is a measuring tool, not a security control.
- The example agent is a script replaying invented calls. It is **not** a customer and the numbers in the example report say nothing about real agents.
- Still pending: the name (see the entry below), and a first real user.

## 2026-10-24 (night): attacking our own verifier
- **I wrote 76 hostile bundles and ran them against `verify.py`.** Nothing changed was ever accepted as `VERIFIED` (edited, removed, reordered or forged records, forged checkpoints, wrong key, stripped witnesses). That is the part that matters, and it held.
- **But three things were wrong, and one of them was a real hole.**
  1. *Silent omission (real).* `manifest.json` is not signed. I removed 37 of 67 records and changed the `scope` label: `VERIFIED`, no warning. The README had said the verifier checks records were "not removed", which was only true when the scope said `all`. The label is attacker-controlled, so the code now trusts only the record count, warns `INCOMPLETE`, and offers `--require-all`. README, spec and KNOWN-LIMITS corrected.
  2. *Crashes.* 24 of the 76 ended in a traceback with exit 1 (documented exit codes are 0, 2, 3). They never passed, but a clean failure is the contract.
  3. *Unbounded read.* A 327 KB zip inflating to 300 MB was read whole and verified. Now capped.
- **A false alarm of mine:** I first thought removing one witness left the bundle verified. The valid bundle carries both cosignatures on one note, so my test removed nothing. Removing a witness's signature line fails correctly.
- **Two broken references** in the public docs pointed at files that exist only in the private repository (`TRUST-GAPS.md`, `tests/test_evidence.py`). Fixed.
- **Checked against primary sources:** the OpenTelemetry `execute_tool` conventions (status Development), Langfuse `TOOL` observations (the `input` field is in the `io` group, not returned by default in API v2) and LangSmith's run format. The readers were not changed; the Langfuse caveat was added to the docs.
- **Found and not fixed here:** the name. "OmniOS" is also an actively released illumos distribution (omnios.org, release r151058 in May 2026) with a GitHub organization of the same name. Trademark status was not verified (no registry lookup was possible). A rename decision is pending.
- Not done: a second implementation to cross-check our checkpoint bytes; a real external review.

## 2026-10-24 (evening)
- **Added trace readers** (Langfuse, LangSmith, OpenTelemetry OTLP/JSON) so the shadow report runs on an export in one command instead of a hand-made CSV. The three invented example exports give the same 45 verdicts as `events.csv` (16 / 20 / 9), and a test keeps it that way.
- **What is NOT verified:** I wrote the readers from the vendors' documented field names and did not check them against exports from live systems (a documentation lookup was not done before writing them). The README and the module say so. If a reader is wrong on your data, that is a bug report, not a surprise.
- Known gaps: OpenTelemetry tool arguments are opt-in in the convention, so many exports will have none; an export does not say whether a call succeeded; tool names must match the rules file.

## 2026-10-24 (later)
- **Published** this repository. The first CI run **failed**: `ubuntu-latest` is now Ubuntu 26.04, which has no Python 3.9 build, and the other two matrix jobs were cancelled by fail-fast. Not a code problem; fixed by pinning `ubuntu-24.04` and setting `fail-fast: false`. All three versions pass.
- **A mistake, corrected:** the README said `git clone <this repository>` until it was actually published. It now has the real URL.
- **Added** `python -m omnios demo` (one command shows the shadow report, a bundle that verifies and a tampered one that fails), a terminal recording, a screenshot of the example report and a social preview image. The recording is generated from the real output of the command by `tools/make_demo_gif.py`; only the typing speed is staged. The demo prints only the lines that decide each outcome; the full output is `verify.py`'s.
- Still true: no external review, no customers, no known users. 24 tests.

## 2026-10-24
- **Checked** that `verify.py` runs with no third-party packages at all. With `cryptography` blocked it reports `signature check: pure-python` and still returns `VERIFIED` on the example bundle.
- **Added** this log, the roadmap, the changelog and contribution notes, so progress and mistakes are visible.

## 2026-10-23
- **Cut the public repository** out of a private prototype: verifier, witness, rules language and the local shadow report.
- **Equivalence check:** the shadow judge in this repository gave the same verdict and the same reasons as the gateway's decision engine on all 45 example events. If the gateway's logic changes, that comparison has to be run again.
- **A mistake, corrected:** earlier text said the log holds "identifiers and digests only". That is not quite true: a decision record also keeps the rule-generated reason, and a reason can quote a number (for example a daily total over a limit). Docs now say so (`docs/EVIDENCE-BUNDLE-SPEC.md`, `docs/KNOWN-LIMITS.md`).
- **Tamper test:** editing one approval (`alice` to `mallory`) in a bundle is caught four ways (manifest hash, leaf hash, record count, and the approval rule).

## Earlier, in the private prototype
- A tamper-evident log with signed checkpoints and witnesses that refuse to cosign a rewritten history.
- An observe mode that judges what an agent already did without blocking anything, which became the shadow report here.
- 175 tests in the private platform. This repository has its own 23.
