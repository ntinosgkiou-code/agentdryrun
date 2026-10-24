# Roadmap

Honest status, updated as things ship. Checked = in this repository and tested.

## Done
- [x] Offline verifier, one file, standard library only (`verify.py`)
- [x] Independent witness service and Merkle-tree/checkpoint code
- [x] Rules language with strict validation (`docs/RULES.md`)
- [x] Local shadow report: judge what an agent did against a rules file, no network
- [x] Bundle format and witness protocol written down (`docs/`)
- [x] Real example bundles: one valid, one tampered, with public keys
- [x] Known limits published first (`docs/KNOWN-LIMITS.md`)

- [x] Readers for Langfuse, LangSmith and OpenTelemetry (OTLP/JSON) trace exports (`omnios/importers.py`), tested on invented fixtures only

- [x] Attack tests for the verifier: hostile bundles, relabelled scope, oversize and malformed files (`tests/test_adversarial.py`); `--require-all`, `--max-bytes`

## Next
- [ ] Cross-check our checkpoint and `cosignature/v1` bytes against a second implementation (for example Go's `x/mod/sumdb/note`)
- [ ] Check the three readers against **real** exports (send a redacted sample), and fix what they get wrong
- [ ] More sources: OpenInference / Phoenix, Braintrust, Helicone, plain OpenAI and Anthropic tool-call logs
- [ ] Map findings to controls (ISO/IEC 42001, NIST AI RMF, OWASP Agentic Top 10), worded as "relevant to", never as compliance
- [ ] White-label report (your name and logo on the output)
- [ ] Optional value fields in the report: minutes and cost saved against a stated baseline
- [ ] A second, independent verifier implementation

## Later
- [ ] Approver-signed approvals (passkeys or Ed25519), so a record carries the human's own signature
- [ ] Post-quantum hybrid signatures (ML-DSA, FIPS 204) next to Ed25519 for long-lived records
- [ ] Wire compatibility with the C2SP `tlog-witness` protocol
- [ ] An external security review

## Not planned in this repository
- The production gateway (enforcement, approvals UI, multi-customer log writer). It is a separate commercial product.
