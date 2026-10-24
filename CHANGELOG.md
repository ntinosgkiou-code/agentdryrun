# Changelog

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
