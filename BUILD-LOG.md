# Build log

A dated, honest log of what was built, what worked, and what was wrong. Newest first. Nothing here is a customer story: there are none yet.

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
