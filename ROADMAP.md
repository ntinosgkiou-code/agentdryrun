# Roadmap

Honest status, updated as things ship. Checked = in this repository and tested.

## Done
- [x] Offline verifier, one file, standard library only (`verify.py`)
- [x] Witness service and Merkle-tree/checkpoint code
- [x] Rules language with strict validation (`docs/RULES.md`)
- [x] Local shadow report: judge what an agent did against a rules file, no network
- [x] Bundle format and witness protocol written down (`docs/`)
- [x] Real example bundles: one valid, one tampered, with public keys
- [x] Known limits published first (`docs/KNOWN-LIMITS.md`)

- [x] Readers for Langfuse, LangSmith and OpenTelemetry (OTLP/JSON) trace exports (`agentdryrun/importers.py`), tested on invented fixtures only

- [x] Attack tests for the verifier: hostile bundles, relabelled scope, oversize and malformed files (`tests/test_adversarial.py`); `--require-all`, `--max-bytes`

- [x] `Recorder`: two lines around an agent's tool functions write the events the shadow report reads; `pip install git+...`

- [x] `mcp-record`: record MCP `tools/call` requests with no change to the agent or the server (stdio; tested against the official Python SDK)
- [x] `suggest-rules`: a draft rules file from what the agent did
- [x] JavaScript/TypeScript recorder (`js/`)

- [x] `scan`: report card from Claude Code transcripts, with a starter rules pack

## Next
- [ ] Submit the plugin to Anthropic's directory (needs a paid claude.ai plan and the developer portal; the author does this)
- [ ] `scan` for Codex CLI sessions, then Cursor and others (needs a real sample of each format: open an issue with a redacted one)
- [ ] `scan --fix`: print the matching permission rules for the agent's own settings, once the exact syntax of each version is verified
- [ ] Per-project rules: `.agentdryrun.json` in a repository, so a team shares one pack
- [ ] Check `mcp-record` against real MCP clients (Claude Desktop, Cursor, VS Code) and servers in other languages; the HTTP transport
- [ ] Publish the JavaScript package on npm and the Python package on PyPI once someone outside this project uses it
- [ ] Adapters for the common agent frameworks' tool decorators
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

## Not now: waits for a real, paying user
These are real needs of a large company, and building them before anyone depends on the tool would be guessing. Each is started when a user who runs this in production asks for it.
- A PostgreSQL or other managed store for the log, and a multi-region, highly available service. The recorder and the dry run are local and fail open; they do not need it.
- Single sign-on and identity-provider integration (Okta, Entra), role mapping.
- Approvals from Slack, Teams or a phone, with buttons.
- Signing approvals with a passkey (WebAuthn). The direction is right and is listed under *Later*; it is not a promise that a forged approval becomes impossible (a compromised device can still sign what it is shown).
- Reports for a specific regulation. This project does not certify anything and will not claim to; any mapping will say "relevant to", never "compliant with".
