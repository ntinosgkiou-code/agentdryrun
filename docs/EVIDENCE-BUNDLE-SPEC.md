# Evidence bundle, format `omnios-evidence-bundle` version 1

> **A note on the name.** This project was called *OmniOS* until 2026-10-25 and is now **agentdryrun** (OmniOS is also the name of an unrelated operating system). The identifier `omnios-evidence-bundle` and the origin prefix `omnios/<tenant>` are the **historical names of the format and are kept on purpose**, so every existing bundle and checkpoint keeps verifying. They name a format, not this project.

The file an auditor, insurer or customer receives. Anyone can write a verifier from this page; the reference one is `verify.py` in the root of this repository, which is also inside every bundle as `verify.py`.

## 1. Layout (a zip)

| File | Contents |
|---|---|
| `manifest.json` | `format`, `version`, `tenant`, `name`, `origin`, `key_name`, `log_public_key` (base64, 32 bytes, **a convenience only**), `size`, `scope` `{kind, id?}`, `profile`, `admin_quorum`, `generated_at`, `witnesses_registered`, `files` (sha-256 hex of every other file) |
| `checkpoints.json` | `main`: `{note}`, the log's signed checkpoint at `size`. `witnessed`: up to eight `{note, consistency}` (one for the latest size each witness has cosigned): an older checkpoint with the log signature **and** witness cosignature lines, plus the RFC 9162 consistency proof (base64 hashes) from that older size to `size` |
| `records.jsonl` | one JSON object per line: `seq`, `body` (the record's exact canonical text), `leaf` (hex), `proof` (RFC 9162 inclusion proof, hex hashes, against `size`) |
| `README.txt` | how to verify, in plain words, and what "VERIFIED" does not mean |
| `verify.py` | the reference verifier (Python ≥ 3.9, stdlib; uses `cryptography` if present, else an inline RFC 8032 implementation) |

The bundle never contains raw parameters, comments or credentials: records hold identifiers, digests and the rule-generated reasons for each decision. A reason can quote a number (for example a daily total that exceeded a limit).

## 2. Record

`body` is UTF-8 JSON, canonical: keys sorted, separators `,` and `:` without spaces, non-ASCII characters not escaped.

```json
{"at":1760000000.0,"data":{...},"prev":"<64 hex>","seq":7,"tenant":"acme-ap","type":"action.approved","v":1}
```

- `leaf = SHA-256(0x00 ‖ body bytes)`; `node = SHA-256(0x01 ‖ left ‖ right)`; tree and proofs as RFC 9162 §2.1.
- `prev` = lowercase hex SHA-256 of the previous record's `body` bytes; record 0 has 64 zeros.
- `data.id` identifies the action or change the record is about (`act-00012`, `chg-0003`).
- Types and fields: see §8 below.

## 3. Checkpoint

A C2SP `signed-note` over a C2SP `tlog-checkpoint` body:

```
omnios/<tenant>
<size>
<base64 root hash>

— omnios/<tenant> <base64( keyid(4) ‖ Ed25519 signature )>
```

The log's key name is its origin, `omnios/<tenant>`. A witness adds a line: either a plain signed-note line, or `cosignature/v1` (type byte 0x04; signed message `cosignature/v1\ntime <t>\n` + checkpoint body; payload keyid(4) ‖ timestamp(8) ‖ signature(64)). `cosignature/v1` is implemented from the published description and tested only against this implementation.

## 4. What a verifier must check, in order

1. **Format.** `format` is `omnios-evidence-bundle` and `version` is 1, otherwise stop.
2. **Files.** Every file's SHA-256 equals `manifest.files[...]`. (This only detects accidental damage: whoever edits the bundle can edit the manifest. The checks below are the real ones.)
3. **Checkpoint signature** against the **pinned** log public key. If the key was not pinned, report `UNPINNED`: the check proves nothing about who runs the log. If it was pinned and the manifest names another key, fail.
4. **For every record** (`records.jsonl` lists each record once, in ascending `seq`; a line that is malformed, repeated or out of order fails the bundle): `SHA-256(0x00‖body) == leaf`; the inclusion proof leads from `leaf` at index `seq` to the checkpoint's root of size `size`; `body` is canonical JSON; `seq` and `tenant` match; `prev` equals the hash of record `seq − 1` (when both are present); record 0 starts at genesis. For scope `all`, exactly `size` records must verify. **`manifest.json` is not signed, so its `scope` label is not trusted:** if fewer than `size` records verified under any other label, report `INCOMPLETE` (a warning; a failure when the recipient asked for completeness, `--require-all`).
5. **Witnesses.** For each `witnessed` entry: the log signed it; each cosignature line is checked against the **pinned witness keys**; a cosigned size smaller than `size` must be shown to be a prefix of the main tree with its consistency proof, otherwise fail ("does NOT extend"). Per witness, keep the largest size proven to be a prefix and the timestamp of that cosignature (`cosignature/v1` only; a plain signed-note line has none). Then apply the policy the *recipient* chose:
   - `min_witnesses = K`: at least K **distinct pinned** witnesses must have such a cosignature, otherwise fail;
   - `max_age = S` (implies K ≥ 1): a witness counts only if its latest cosignature is at most S seconds old; one without a timestamp does not count;
   - report which witnesses counted, how far K of them cover the log (`witnessed_by_required_up_to`), and warn about the tail not yet witnessed by K witnesses. With no policy: warn when no witness keys were given or when coverage is partial.
6. **Rules recorded in the ledger** (these apply even though the cryptography is valid; a signature proves the operator wrote it, not that the rules were followed):
   - each `policy.activated` record's `policy` hashes (canonical JSON, SHA-256) to its `policy_hash`;
   - an applied change had at least `quorum − 1` approvals from admins other than its proposer;
   - for each action: no approver approved twice; the agent is not among the approvers; if the tool requires approver groups (taken from the policy active at the time), each approval carries one; no execution record exists for an action the rules denied; every `action.executing` and every agent-reported `action.executed` happened after at least the required number of approvals;
   - an `action.executing` with no `executed`/`failed` afterwards is reported as *dangling* (warning).

A verifier must also treat the bundle as hostile input: refuse a zip with duplicate names, more than a handful of entries, or a member that would inflate beyond a bound (`verify.py`: 256 MiB, `--max-bytes`), and turn any malformed JSON or wrong type into a failure rather than a crash. A bundle that cannot be read is never `VERIFIED`.

Exit codes of `verify.py`: `0` verified (warnings may exist), `2` failed, `3` unreadable, malformed or bad arguments. Flags: `--log-key`, `--witness NAME=KEY` (repeatable), `--min-witnesses K`, `--max-age 36h|7d|3600`, `--require-all`, `--max-bytes N`, `--json`.

## 5. Scopes

| Scope | Records | Use |
|---|---|---|
| `all` | every record up to the checkpoint | the monthly pack; full audit |
| `action` (+ `id`) | that action's records, the `policy.activated` records it relied on, and the changes that activated those policies | "show me this payment" |
| `changes` | tenant, policy, change, principal and witness records | "who can change the rules, and who did" |

A partial scope proves that *those records are in the log*; it cannot prove nothing else relevant exists. Use `all` for completeness, and run the verifier with `--require-all`.

## 6. What VERIFIED does and does not mean

It means: the records in the bundle are exactly what was committed; they sit in the tree a signed checkpoint states; the log key signed it; (with a trusted witness) the log did not rewrite what the witness had seen; and the recorded rules were followed.

It does **not** mean: the decisions were right; every action the agent took was logged (an agent that never asks is invisible in decision mode; use proxy mode for anything that matters); approvals were made by the people named (they are attested by the platform, not signed by the approvers' own keys: see [KNOWN-LIMITS.md](KNOWN-LIMITS.md)); the software has had an independent security review; or any legal compliance.

## 7. Using a verifier you did not receive with the bundle

`verify.py` inside the zip was produced by the same party as the zip. A careful recipient downloads the verifier separately (from the vendor's release, or writes their own from this page) and compares its SHA-256 with a value published elsewhere. [`tests/test_adversarial.py`](../tests/test_adversarial.py) runs the cases a hostile bundle would use, each with the manifest repaired: edited, removed, repeated and reordered records, forged leaves and proofs, a changed or re-signed checkpoint, the wrong pinned key, stripped witness signatures, dropped records under a relabelled scope, wrong JSON types, deep nesting, duplicate zip entries and oversize members. Passing them shows those attacks fail; it is not a security audit.

## 8. Record types

| Type | Written when | Key fields |
|---|---|---|
| `tenant.created`, `tenant.suspended/resumed`, `witness.registered` | operator actions | profile, quorum, log public key |
| `policy.activated` | an applied rule change | the full policy, its hash, previous hash, who, via which change |
| `principal.changed` | a key is created, rotated or revoked | name, role, groups, permissions, who, approvers |
| `change.proposed/approved/rejected/applied` | changes to rules or keys | kind, proposer, quorum, summary, approvers |
| `action.proposed` / `action.denied` | an agent proposes an action | tool, agent, `params_digest`, policy hash, risk, approvals required, reasons |
| `action.approved` / `action.rejected` | an approver decides | approver, n of N, groups |
| `action.executing` then `action.executed` / `action.failed` | before and after the call (gateway-executed) | approvers, attestation, result digest |
| `action.executed` (attestation `agent_report`) | the agent reports the outcome | approvers, result digest |
| `action.compensating/compensated`, `action.expired` | undo and timeout | |
| `action.observed` | observe mode: a system reports what its agent did | tool, agent, `params_digest`, dry-run verdict (allow / pending / deny), approvals it would have needed, reasons, policy hash |

`action.observed` records are counted by the verifier but never checked against the approval rules: nothing was decided, approved or executed.
