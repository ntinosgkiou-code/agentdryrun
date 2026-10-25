---
name: scan
description: Scan your own Claude Code history for what your rules would have stopped (recursive deletes, force pushes, curl | sh, secret files read, uploads) and where the tool output piled up. Read-only and local.
argument-hint: "[--days N] [--project NAME]"
disable-model-invocation: true
---

The user ran `/agentdryrun:scan`. This is a read-only, local dry run on their own Claude Code history. Nothing is sent anywhere and nothing is changed.

1. Say in one sentence what is about to happen: the scanner reads the transcripts Claude Code keeps on this machine (`~/.claude/projects`), judges what the agent did against a starter rules pack, and writes one HTML report card.

2. Run exactly one command, from the current directory. Use the form that matches the shell tool in this session.

   Bash (macOS, Linux, Git Bash on Windows):
   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m agentdryrun scan --no-previews --out "$HOME/agent-report-card.html" $ARGUMENTS
   ```
   If `python3` is not found, use `python`. On Windows with PowerShell:
   ```powershell
   $env:PYTHONPATH = "${CLAUDE_PLUGIN_ROOT}"; python -m agentdryrun scan --no-previews --out "$env:USERPROFILE\agent-report-card.html" $ARGUMENTS
   ```
   Python 3.9 or newer is required and nothing needs to be installed. `$ARGUMENTS` may hold `--days N` (default 30; `0` means everything) or `--project NAME`.

3. Show the command's summary to the user as it was printed: the counts of actions that would pass, would need approval and would be refused, the kinds of action behind them, the tool-output estimate and the path of the report card. Do not add numbers, do not guess what a flagged action was, and do not open, read or quote the HTML file.

4. Tell the user, briefly:
   - The report was written without command text (`--no-previews`). To see excerpts of their own commands, they can re-run it themselves without that flag and keep that page private.
   - The scan is pattern matching on commands: it misses scripts and paths built at run time, and flags a few harmless things. The verdicts come from a starter rules pack they can copy and edit. It is not a sandbox and stops nothing.
   - Reports of false alarms and misses are welcome at https://github.com/ntinosgkiou-code/agentdryrun/issues

5. If the command says there are no transcripts, explain that `--root PATH` points it at another folder. If Python is missing, say so. Do not run anything else and do not change any setting or file.
