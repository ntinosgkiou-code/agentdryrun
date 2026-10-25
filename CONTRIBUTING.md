# Contributing

agentdryrun (the open parts) is **built in public**: the code, the roadmap, the mistakes and the corrections are all in this repository.
You do not need permission to try it, break it or build on it. It is Apache-2.0.

## Run it
```bash
python -m unittest discover -s tests      # 114 tests, no network, about twenty seconds
python -m agentdryrun demo                     # the whole thing on the shipped example
python verify.py --help
python -m agentdryrun shadow --help
```
`verify.py` and the shadow report need Python 3.9+ and nothing else. Only the witness service needs `pip install -r requirements.txt`.

## Money, assignments and `help wanted`
This is an **unpaid, unfunded** open-source project. There is no budget for issues or pull requests, nobody is paid to work on it, and issues are not assigned: if you want to fix something, open a pull request (a comment first is welcome, not required). `help wanted` means "I would like help", not "there is a bounty". Contributions are accepted under Apache-2.0.

## What helps most (in this order)
0. **Run `python -m agentdryrun scan` on your own Claude Code history** and tell us what it flagged that was normal, what it missed, or whether it crashed (paste command text only, no secrets). A redacted Codex CLI session file would let `scan` read Codex too ([issue 11](https://github.com/ntinosgkiou-code/agentdryrun/issues/11)).
1. **Break the verifier.** A bundle that `verify.py` calls `VERIFIED` although a record was added, removed, edited or reordered is the most valuable report you can send. See [SECURITY.md](SECURITY.md).
2. **A second verifier.** Write one in any language from [`docs/EVIDENCE-BUNDLE-SPEC.md`](docs/EVIDENCE-BUNDLE-SPEC.md) and run it on `examples/`. Every place it disagrees with `verify.py` is either a bug or a hole in the spec. Open an issue titled *verifier disagreement*.
3. **Check the importers on a real export.** The Langfuse, LangSmith and OpenTelemetry readers in `agentdryrun/importers.py` were built from the vendors' documented field names and tested only on invented fixtures. Run `python -m agentdryrun import your-export.json`; if it reads it wrongly or not at all, open an issue with a **redacted** sample. New sources (OpenInference, Braintrust, Helicone, raw OpenAI or Anthropic tool-call logs) are welcome as pull requests with a fixture and a test.
4. **Rules examples** for other workflows (refunds, data deletion, outbound email). The language is in [`docs/RULES.md`](docs/RULES.md).
5. **Translations** of the README and docs.

## Ground rules
- No secrets, no customer data, no real people or companies in examples. Use invented data and say so.
- A change in behaviour comes with a test. `verify.py` stays a single file that uses only the standard library.
- Say what a thing proves **and what it does not prove**. If a claim cannot be checked, do not write it.
- Be specific in issues: the command you ran, what you expected, what happened.

## Scope
This repository is the verification and local-experiment side. The commercial gateway that enforces rules in production is not part of it (see the table in the README).
