# Checked on 2,000 public agent runs

`scan` was built and tuned on one person's Claude Code history. That is a small, friendly test. To find out how often the starter rules raise a false alarm on somebody else's data, they were run over a random sample of published agent runs. This page says what was done, what came out, what was wrong, and what the numbers do **not** show.

## What was done
- **Data:** a random sample of 2,000 runs (`seed 20261026`, 200 pages of 10 consecutive rows) of [nebius/SWE-rebench-openhands-trajectories](https://huggingface.co/datasets/nebius/SWE-rebench-openhands-trajectories), 67,074 runs of the OpenHands agent fixing GitHub issues, licensed CC-BY-4.0. Rows were read through the public datasets-server API; nothing was downloaded as a whole file and the data is not redistributed here.
- **Read-only:** no agent was run and nothing was executed. Each tool call in a run (`execute_bash`, `str_replace_editor`) was turned into the same events `scan` makes from a Claude Code transcript and judged by the starter rules (`agentdryrun/packs/coding-agent.json`).
- **Reproduce it:** `python tools/study_public_runs.py --pages 200 --per 10 --seed 20261026 --out study.json` (about 12 minutes; needs network).

## Result (v0.8.1)
| | Actions | Share |
|---|---|---|
| would pass | 121,184 | 99.97% |
| would need approval | 34 | 0.03% |
| would be refused | 1 | <0.01% |
| **Total judged** | **121,219** | |

19 of the 2,000 runs (0.95%) contained at least one flagged action. In v0.8.0 the same sample gave 48 approvals and 1 refusal in 29 runs.

## What the 35 remaining flags are
All are what the rules say they should be, and all are harmless inside these sandboxes:

| Kind | Count | Examples |
|---|---|---|
| Writes to CI files | 14 | edits to `.github/workflows/ci.yml` |
| `sudo` | 9 | `sudo dockerd`, `sudo mv /usr/bin/git ...` |
| Work thrown away | 5 | `git checkout .`, `git reset --hard HEAD` |
| Recursive deletes | 3 (2 approvals, 1 refusal) | `rm -rf ~/.cookiecutters/`, `... \| xargs rm -rf`, `rm -rf` under `site-packages` (refused: system folder) |
| Secret-like files read | 3 | a test `.env`, two `*.ini` token files |
| Environment dumped | 1 | `printenv \| head -3` |

## False alarms found by this check, and fixed in 0.8.1 (14 of the 49 flags)
| What the rules did wrong | Flags | Fix |
|---|---|---|
| Called SQL text inside `python -c` a destructive database command (a SQL parser's own tests) | 8 | For `python`, `node`, `npm` and similar, SQL counts only when the code can run it (`.execute(`, a DB driver) |
| Treated the pattern given to `grep` (`"tokens.txt"`, `".key"`) as a secret file being read | 4 | The first word of `grep`, `rg`, `sed`, `awk` is the pattern, not a file |
| `cd /tmp/work && rm -rf *` read as "delete the whole project" | 1 | `*` means the directory the shell moved to |
| `nc -zv localhost 7687` read as remote access | 1 | Local addresses are not remote |

Tests for each are in `tests/test_scan.py` (`FoundOnPublicRuns`).

## A mistake in the first attempt
The first pass of this study gave a much worse result (133 approvals, 72 runs flagged). The cause was in the study script, not the rules: it took the project folder from the task text with a pattern that kept a trailing `\n`, so every `rm -rf` inside the project looked like it was outside it. The script was fixed and the whole sample re-run before any number above was written down.

## What this does NOT show
- **Not a measure of danger.** These runs happen in disposable Docker sandboxes. A flag means "the rules would have asked", not "something bad happened or would have".
- **One agent, one kind of task** (OpenHands fixing issues in open source repositories). Other agents and real working machines behave differently; the false-alarm rate there is not known.
- **Only the starter rules.** Your own rules will flag more or less.
- **2,000 of 67,074 runs.** A random sample, not the whole set. No confidence interval was computed.
- **Misses are not measured.** This counts flags that were raised. A command the rules miss (a script that deletes, a path built at run time) does not appear, so these numbers say nothing about how much was missed. See [KNOWN-LIMITS](KNOWN-LIMITS.md).

## Credit
Data: Nebius, *SWE-rebench-openhands-trajectories*, CC-BY-4.0. Statistics and flagged command lines here are derived from it.
