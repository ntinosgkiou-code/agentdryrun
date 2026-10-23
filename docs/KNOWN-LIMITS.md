# Known limits

Written first because a verification tool that hides what it cannot prove is worse than none.

## What `VERIFIED` proves
The records are exactly what was committed; they sit in the tree a signed checkpoint describes; the pinned log key signed that checkpoint;
with trusted witnesses, the log did not rewrite what a witness had already seen; the rules written *inside* the log were followed.

## What it does not prove
| Limit | Why it matters |
|---|---|
| **Records are not necessarily true.** A signature proves the operator wrote a record, not that it happened. | A malicious operator can append a false record *now*; only a rewrite of the past is caught by a witness. |
| **Approvals are not yet signed by the approvers themselves.** The platform attests "alice approved". | The strongest next step is approver-held keys (passkeys / Ed25519) so a record carries the human's own signature. Designed, not built. |
| **An agent that never asks is invisible.** | Evidence only covers actions that pass through the gateway (or that a system reports in observe mode). |
| **Records are not free of numbers.** The log keeps identifiers, digests and rule-generated reasons, never raw parameters, but a reason can quote a computed figure (for example `limit exceeded: amount_eur 19800 would pass 15000 per day`). | Share a bundle only with people who may see those figures. |
| **Observe mode sees only what is reported**, and the time of an event is claimed by the reporter. | Verdicts are a simulation under the rules in force. They do not say the actions were right. |
| **Witness independence is relative.** A witness run by the log's operator proves nothing about the operator. | Choose witnesses run by someone the verifier trusts (an auditor, an insurer, internal audit) and require `--min-witnesses`. |
| **The witness push protocol is our own JSON,** not wire-compatible with the C2SP `tlog-witness` protocol. | Interoperability with third-party witnesses is untested. |
| **`verify.py` inside a bundle was produced by whoever produced the bundle.** | Use a copy you obtained separately (this repository) and compare hashes. |
| **No external security audit, no penetration test, never run with a real customer or bank.** | Treat it as a design you can inspect, not a hardened product. |
| **It does not stop prompt injection.** | It limits what a fooled agent can do *through the gateway* and leaves evidence of what it did. |

## What it is not
Not a certification, not legal advice, not a guarantee of compliance with any regulation.
