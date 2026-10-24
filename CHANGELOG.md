# Changelog

## 0.1.0 (2026-10-24)
First public release of the open parts.
- `verify.py`: offline evidence-bundle verifier (single file, standard library only; pure-Python Ed25519 fallback)
- `omnios/witnessd.py`, `omnios/tlog.py`: independent witness and Merkle-tree/checkpoint code
- `omnios/policy.py`, `omnios/shadow.py`, `omnios/report.py`: rules language and local shadow report
- `docs/`: rules reference, bundle format, witness protocol, known limits
- `examples/`: rules, 45 invented events, a shadow report, a valid and a tampered bundle, public keys
- 23 tests (no network)
