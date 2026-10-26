# Build log

A dated, honest log of what was built, what worked, and what was wrong. Newest first. Nothing here is a customer story: there are none yet.

## 2026-10-26: three suggestions from outside, triaged
A list of four ideas for `agentdryrun` arrived (from someone who read the project). Decisions, with the reason:
- **"Run commands in an invisible sandbox and freeze the dangerous ones"**: not as stated. It would make the tool a security product with a much larger failure surface, it is Linux-only for the proposed mechanism (eBPF), sandboxes are already built into the agents and sold by others, and "the AI thinks the command ran" is deception that breaks easily. What was built instead is the honest small version: a live hook that uses the same rules and can only make things stricter (deny or ask), with an observe mode first.
- **"A small local LLM to judge intent instead of pattern matching"**: not in the core. A judge that is itself a model is non-deterministic, heavy, and can be talked around: that is the same class of weakness reported against classifier-based permission modes in 2026. Pattern matching misses things, and the README says exactly which; a model would miss different things silently. Possibly an optional second opinion later, never the gate.
- **"Support Cursor, Copilot, LangChain, AutoGPT"**: the right direction and already on the roadmap, but each needs a verified session format. The MCP recorder already works for MCP tools in any client; Codex (open source) is next; closed formats wait for a redacted sample.
- **"Learn the user's habits for three days and write their rules"**: built, without the three days: `scan --write-rules` uses the history that is already on disk and locks the kinds of action you never do.

## 2026-10-25 (night): aiming at a real problem, not at the part I had built
- **The question I was asked:** can this be known on GitHub, and be the answer to a problem people have *now*, not a tool nobody wants? I checked instead of guessing. On 2026-10-25 I counted stars with the GitHub search API. Repositories created since August on the topic *agent-security*: the best has 671 stars, the next ones under 550. Since April, "agent firewall" tools for coding agents: the best has 173, then 39. MCP security scanners: the best has 49. Tools that stop `--dangerously-skip-permissions` mistakes: under 250. Meanwhile local-log tools for coding agents that tell you something about yourself have thousands (`ccusage` 19 k, `agentsview` 6 k), and the biggest repositories around Claude Code deal with cost, memory and skills, with six-figure counts (some of these numbers may be inflated; I did not audit them). **So the part of this project I had polished the most, evidence and governance, sits in the least-starred corner, with several look-alikes.** That is not proof it is worthless (its buyers are not people who star repositories); it is proof it should not be the front door of a repository that wants attention.
- **What the news says:** coding agents deleting things is current (reported 2026 incidents with Codex, Cursor and Claude Code; I could verify only secondary reports, so none is cited in the README), and Anthropic's own engineering post says users accept 93% of manual prompts and that its auto mode is not a drop-in replacement for careful human review on high-stakes infrastructure. That is the gap `scan` addresses: you cannot review what you approved without looking.
- **What I built:** `scan`, because the pattern that wins in this space is *one command on your own machine that shows you something about yourself in seconds*, and because the engine already existed (importers, rules, judge, report).
- **What I did not do:** a permission-allowlist generator ("approve less"). Anthropic reportedly made auto mode the default in August 2026 (secondary reports); that slot is taken by the platform itself.
- **Tested on a real history, then fixed.** Run on one developer's real 90-day Claude Code history (about 11,000 tool calls) the first version said 2,130 actions needed approval and 25 would be refused. Most was noise from the tool itself: `curl | python -c` flagged as "pipe to shell", writes outside the working directory (extra directories are normal), `rm -rf` of a variable set one line earlier, here-document text read as commands. After fixes: 355 (3.2%) and 2. The two refusals were real force pushes to `main`. The lesson stays: **invented fixtures would have shown none of this**; the pack is still too coarse for other people's habits, which is why the report says so on its first screen.
- **Honest expectation:** stars cannot be promised and are not bought. A decent tool in a crowded corner gets tens to hundreds; the realistic upside is that this is the first tool in its slot with a *judgement* (what would your rules have stopped) rather than a bill. No customers, no known users yet.

## 2026-10-25 (later): fewer steps to the first report
- **Why:** every way in still needed either code in the agent, an export, or a hand-written rules file. Three additions remove one step each: record MCP calls without touching anything (`mcp-record`), draft the rules from what was seen (`suggest-rules`), and a JavaScript recorder.
- **An "enterprise wish list" I was handed** (Postgres, multi-region failover, SSO, Slack approvals, passkeys, a "SOC 2 / EU AI Act report signed by independent witnesses") was triaged instead of built. None of it helps someone who wants to try the tool today; all of it is guessing before a user exists. It is written down under *Not now* in the roadmap with the reason. Two claims in it are not made anywhere in this project: that a compliance report can be produced (this is not a certification, and the EU AI Act's high-risk obligations have been postponed to December 2027 as far as I know: check the current text before relying on any date), and that signed approvals make forgery impossible.
- **A real bug, found only by using a real client:** my own tests passed, but running the proxy between the official MCP SDK client and server showed "Fatal Python error" when the server exited while the client still held stdin open. A background thread was blocked reading stdin while the interpreter shut down. Fix: flush and `os._exit` with the server's code. I wrote the test first, saw it fail without the fix, then fixed it.
- **What is verified:** byte-identical forwarding against a fake server; the official SDK 1.30 and 2.3, client and server, both calls recorded; Node recorder with `node:test`; events written by JavaScript judged by the Python side.
- **What is not:** any desktop MCP client, servers in other languages, the HTTP transport. The MCP proxy space already has several small projects; this one is meant to feed the dry run and CI, not to compete as a firewall.

## 2026-10-25: a new name
- **The project was called OmniOS, which is also an unrelated operating system** (omnios.org, release r151058 in May 2026) with a GitHub organization of the same name. Searching for it would never have found this repository. The trademark status was not checked (no registry lookup was possible); renaming early, with zero stars, was the cheap way to avoid finding out the hard way.
- **Chosen name: agentdryrun**, after checking that it is free on PyPI, npm and GitHub (no repository, user or organization). It says what it does: a dry run for AI agents.
- **Done with a script and checked by the tests** (68 pass). **Left unchanged on purpose:** the bundle format identifier `omnios-evidence-bundle` and the `omnios/<tenant>` origin in the signed examples, because changing them would break existing signed bundles (see the note in `docs/EVIDENCE-BUNDLE-SPEC.md`).
- **Evidence I used on what makes repositories grow** (so the next steps are not guesses): developers check stars before using a project and promotion matters most (Borges and Valente, 2018); a Hacker News post raises stars, mostly for well-documented projects, but the *median* launch is far below the average (Kraishan 2025, KIT causal study); bought stars give a boost under two months and then become a liability (ICSE 2026). Nothing in this repository buys or trades stars.

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
