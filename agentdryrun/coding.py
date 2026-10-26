"""coding.py: read a coding agent's OWN session logs and turn what it did into events the dry run can judge.

Supported today: Claude Code transcripts (`~/.claude/projects/**/*.jsonl`, or `$CLAUDE_CONFIG_DIR/projects`).
The format was read from real transcripts on 2026-10-25 (assistant `tool_use` blocks, user `tool_result` blocks, `timestamp`, `cwd`);
it is not a documented, stable interface, so a future Claude Code version can break the reader. Codex, Cursor and others are NOT read yet.

A shell command is split into its parts (`a && b | c`) and each part is named by what it does (`shell.delete_recursive`,
`git.force_push`, `secrets.read`, ...), with a few parameters (where, how far from the project) that the rules language can test.

This is pattern matching, not understanding. It will miss things (`python -c "shutil.rmtree(...)"`, a script that deletes files,
a path built at run time) and it will flag a few harmless ones. It reads only what the agent attempted; it cannot know what
you approved, or whether the command worked. Everything runs on your machine and nothing is sent anywhere.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import posixpath
import re
import shlex
from pathlib import Path
from typing import Iterable, Optional

from .suggest import classify as _classify_name

# ───────────────────────────── hiding secrets in anything we print ─────────────────────────────
_HIDE = re.compile("|".join([
    r"sk-ant-[A-Za-z0-9_\-]{10,}", r"sk-[A-Za-z0-9_\-]{16,}", r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
    r"xox[abprs]-[A-Za-z0-9\-]{10,}", r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{30,}",
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i:bearer|basic)\s+[A-Za-z0-9._~+/\-=]{12,}",
    r"(?i:(?:token|apikey|api_key|api-key|secret|password|passwd|pwd|auth)\w*)\s*[=:]\s*['\"]?(?:(?i:bearer|basic|token)\s+)?[^\s'\"&;|]{6,}",
    r"(?i:(?:token|apikey|api_key|api-key|secret|password|passwd|pwd)\w*)\s+(?=[^\s'\"&;|]*\d)[^\s'\"&;|]{12,}",
    r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)",
    r"[A-Za-z0-9+/_\-]{40,}={0,2}",
]))


def hide_secrets(text: str, limit: int = 140) -> str:
    """Best effort: replace things that look like keys, tokens and passwords, collapse spaces and cut to `limit` characters.
    It is a courtesy, not a guarantee: read an excerpt before you share it."""
    t = _HIDE.sub("<hidden>", " ".join(str(text).split()))
    return t if len(t) <= limit else t[: limit - 1] + "…"


# ───────────────────────────── paths ─────────────────────────────
_HOME_RE = re.compile(r"^(/Users/[^/]+|/home/[^/]+|/root|[A-Za-z]:/Users/[^/]+)", re.I)
_SYSTEM = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/var", "/opt", "/system", "/library", "/applications",
           "c:/windows", "c:/program files", "c:/program files (x86)", "c:/programdata")
_TEMP = ("/tmp", "/var/tmp", "/private/tmp", "/dev/shm")
_HOME_VARS = re.compile(r"^(\$\{?HOME\}?|\$\{?USERPROFILE\}?|%USERPROFILE%|\$env:USERPROFILE|\$env:HOME|~)(?=/|\\|$)", re.I)


def _slash(p: str) -> str:
    p = p.replace("\\", "/")
    m = re.match(r"^/([A-Za-z])/(.*)$", p)               # git-bash style /c/Users/x
    if m and m.group(2):
        p = f"{m.group(1)}:/{m.group(2)}"
    return p


class Ctx:
    """Where a command ran: the working directory (the project) and the user's home directory."""

    def __init__(self, cwd: str = "", home: str = ""):
        self.cwd = posixpath.normpath(_slash(cwd)) if cwd else ""
        m = _HOME_RE.match(self.cwd)
        self.home = posixpath.normpath(_slash(home)) if home else (m.group(1) if m else "")
        self.ci = bool(re.match(r"^[A-Za-z]:", self.cwd or self.home))      # Windows paths compare without case
        self.base: Optional[str] = self.cwd                                  # where relative paths start (changes with `cd`); None = unknown
        self.vars: dict = {}                                                 # NAME=value assignments seen earlier in the same command

    def copy(self) -> "Ctx":
        c = Ctx.__new__(Ctx)
        c.__dict__.update(self.__dict__)
        c.vars = dict(self.vars)
        return c

    def expand(self, p: str) -> str:
        for _ in range(3):
            n = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: self.vars.get(m.group(1) or m.group(2), m.group(0)), p)
            if n == p:
                break
            p = n
        return p

    def _k(self, p: str) -> str:
        return p.lower() if self.ci else p

    def resolve(self, raw: str) -> Optional[str]:
        """An absolute, normalised path, or None when it depends on a variable or substitution we cannot know."""
        p = raw.strip().strip("'\"")
        if not p:
            return None
        p = self.expand(p)
        m = _HOME_VARS.match(p)
        if m:
            if not self.home:
                return None
            p = self.home + p[m.end():].replace("\\", "/")
        p = _slash(p)
        if re.search(r"[`$]|%\w+%|\$\(", p):
            return None
        if not (p.startswith("/") or re.match(r"^[A-Za-z]:/", p)):
            if not self.base:
                return None
            p = self.base + "/" + p
        return posixpath.normpath(p)

    def scope(self, raw: str) -> str:
        """root | home | system | project_root | inside_project | temp | outside_project | unresolved_variable"""
        p = self.resolve(raw.rstrip("*").rstrip("/\\") if raw.strip() not in ("/", "*") else raw)
        if raw.strip() in ("*", "./*", "*/"):
            p = self.base or None                                  # everything in the directory the shell is in now (after any `cd`)
        if p is None:
            return "unresolved_variable"
        k = self._k(p)
        if k == "/" or re.fullmatch(r"[a-z]:/?", k):
            return "root"
        if self.home and k == self._k(self.home):
            return "home"
        for t in _TEMP:
            if k == t or k.startswith(t + "/"):
                return "temp"
        if re.search(r"/appdata/local/temp(/|$)", k):
            return "temp"
        for s in _SYSTEM:
            if k == s or k.startswith(s + "/"):
                return "system"
        project_ok = bool(self.cwd) and self._k(self.cwd) not in ("/", self._k(self.home))
        if project_ok:
            c = self._k(self.cwd)
            if k == c:
                return "project_root"
            if k.startswith(c + "/"):
                return "inside_project"
        return "outside_project"


# ───────────────────────────── what a path is ─────────────────────────────
_ENV_TEMPLATE = re.compile(r"\.(example|sample|template|dist|defaults?|schema)$", re.I)


def secret_kind(path: str) -> Optional[str]:
    """What kind of secret file this path looks like, or None."""
    p = _slash(path.strip().strip("'\"")).lower()
    base = p.rsplit("/", 1)[-1]
    if re.fullmatch(r"\.env(\.[\w.\-]+)?", base) and not _ENV_TEMPLATE.search(base):
        return "dotenv"
    if "/.ssh/" in p or re.fullmatch(r"id_(rsa|dsa|ecdsa|ed25519)(\.pub)?", base):
        return None if base.endswith(".pub") or base in ("known_hosts", "config") else "ssh_key"
    if "/.aws/" in p and base in ("credentials", "config"):
        return "cloud_credentials"
    if "/.config/gcloud/" in p or "/.azure/" in p or p.endswith("/.kube/config") or p.endswith("/.docker/config.json"):
        return "cloud_credentials"
    if base in (".npmrc", ".pypirc", ".netrc", "_netrc", ".git-credentials", ".pgpass", ".my.cnf"):
        return "registry_or_login"
    if re.search(r"\.(pem|key|p12|pfx|keystore|jks|ppk)$", base):
        return "key_file"
    if re.search(r"(secret|credential|token|apikey|api_key|password)s?\.(json|ya?ml|txt|env|toml|ini)$", base):
        return "token_file"
    return None


_STARTUP = {".bashrc", ".zshrc", ".profile", ".bash_profile", ".zprofile", ".zshenv", ".bash_login", "config.fish",
            "microsoft.powershell_profile.ps1", "profile.ps1"}


def write_kind(path: str) -> str:
    """normal | shell_startup | ssh | git_hooks | ci_workflow | agent_config | system_config | persistence"""
    p = _slash(path.strip().strip("'\"")).lower()
    base = p.rsplit("/", 1)[-1]
    if "/.ssh/" in p:
        return "ssh"
    if base in _STARTUP:
        return "shell_startup"
    if "/.git/hooks/" in p:
        return "git_hooks"
    if "/.github/workflows/" in p or base in (".gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml"):
        return "ci_workflow"
    if re.search(r"/\.claude/(settings|hooks)|/\.claude\.json$|(^|/)\.mcp\.json$|/\.cursor/(mcp|rules|hooks)|/\.codex/(config|hooks)|/\.gemini/settings", p):
        return "agent_config"
    if p.startswith("/etc/") or p.startswith("c:/windows/"):
        return "system_config"
    if "/launchagents/" in p or "/.config/systemd/" in p or base in ("crontab",) or "/start menu/programs/startup/" in p:
        return "persistence"
    return "normal"


# ───────────────────────────── splitting a shell command ─────────────────────────────
def split_command(cmd: str) -> list:
    """[(segment, operator_that_follows)] for `a && b | c; d`. Quotes, $( ) and backticks are respected (not parsed)."""
    out, cur, i, n = [], [], 0, len(cmd)
    q = None
    depth = 0
    while i < n:
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == "\\" and q == '"' and i + 1 < n:
                cur.append(cmd[i + 1])
                i += 1
            elif ch == q:
                q = None
        elif ch in "'\"":
            q = ch
            cur.append(ch)
        elif ch == "\\" and i + 1 < n:
            cur.append(ch + cmd[i + 1])
            i += 1
        elif cmd.startswith("$(", i) or cmd.startswith("<(", i):
            depth += 1
            cur.append(cmd[i:i + 2])
            i += 1
        elif ch == ")" and depth:
            depth -= 1
            cur.append(ch)
        elif depth:
            cur.append(ch)
        elif ch == "`":
            j = cmd.find("`", i + 1)
            j = n - 1 if j < 0 else j
            cur.append(cmd[i:j + 1])
            i = j
        else:
            op = None
            for cand in ("&&", "||", "|&"):
                if cmd.startswith(cand, i):
                    op = cand
                    break
            if op is None and ch in "|;\n":
                op = ch
            if op:
                out.append(("".join(cur).strip(), "|" if op == "|&" else op))
                cur = []
                i += len(op) - 1
            else:
                cur.append(ch)
        i += 1
    out.append(("".join(cur).strip(), None))
    return [(s, o) for s, o in out if s]


def _words(seg: str, posix: bool = True) -> list:
    try:
        return shlex.split(seg, posix=posix)
    except ValueError:
        return seg.split()


_WRAPPERS = {"sudo", "doas", "env", "nohup", "time", "command", "exec", "nice", "stdbuf", "builtin", "setsid", "caffeinate", "timeout"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
_INTERP = _SHELLS | {"python", "python3", "node", "perl", "ruby", "php", "powershell", "pwsh"}


def _program(tokens: list) -> tuple:
    """(program, args, used_sudo) after skipping env assignments and wrappers such as sudo/env/nohup."""
    sudo = False
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"^[A-Za-z_]\w*=", t):
            i += 1
            continue
        base = t.rsplit("/", 1)[-1].lstrip("\\")
        if base in _WRAPPERS:
            if base in ("sudo", "doas"):
                sudo = True
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in ("-u", "-g", "-n", "-s", "-k", "-t") and i + 1 < len(tokens) and base != "env" else 1
            if base == "timeout" and i < len(tokens) and re.match(r"^\d", tokens[i]):
                i += 1
            continue
        return base.lower(), tokens[i + 1:], sudo
    return "", [], sudo


# ───────────────────────────── naming what a command does ─────────────────────────────
_SCOPE_RANK = {"root": 7, "home": 6, "system": 5, "unresolved_variable": 4, "piped_input": 3, "project_root": 2,
               "outside_project": 1, "inside_project": 0, "temp": 0}
_PROTECTED = re.compile(r"^(main|master|trunk|prod|production|release|stable|live|develop)$|^release[/\-]", re.I)
_PROD = re.compile(r"\b(prod|production|live|primary)\b", re.I)
_SQL_BAD = re.compile(r"\b(drop\s+(table|database|schema|index|view|user)|truncate\s+(table\s+)?\w|alter\s+table\s+\S+\s+drop\s)", re.I)
_SQL_DELETE_ALL = re.compile(r"\bdelete\s+from\s+[\w.\"`\[\]]+\s*(;|[\"'`]|$)", re.I)
_DB_RESET = re.compile(r"\b(dropdb|flushall|flushdb|db:drop|db:reset|db:schema:load|migrate\s+reset|db\s+reset|drizzle-kit\s+drop|"
                       r"sequelize\S*\s+db:(drop|migrate:undo:all)|mysqladmin\s+drop)\b", re.I)
_DB_CLI = {"psql", "mysql", "mariadb", "sqlite3", "mongosh", "mongo", "redis-cli", "sqlcmd", "clickhouse-client", "cockroach",
           "supabase", "prisma", "drizzle-kit", "sequelize", "knex", "alembic", "rails", "rake", "dropdb", "mysqladmin", "turso",
           "pscale", "neon", "neonctl", "npx", "pnpm", "yarn", "bun", "bunx", "npm", "python", "python3", "node", "php", "docker", "kubectl"}
# A script that merely contains SQL text (a parser's test, a docstring) is not a database command; one that can run it is.
_SCRIPT_RUNNERS = {"python", "python3", "node", "php", "npx", "pnpm", "yarn", "bun", "bunx", "npm"}
_SQL_RUN_CUE = re.compile(r"\.(execute|executemany|executescript|exec|query|raw|run)\s*\(|\b(psycopg2?|pymysql|mysql\.connector|sqlite3|sqlalchemy|"
                          r"create_engine|asyncpg|aiosqlite|mysqli|PDO|mongoose|sequelize|knex|prisma|drizzle|typeorm)\b", re.I)
_PATTERN_FIRST = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "findstr", "select-string", "sls", "sed", "awk"}
_READERS = {"cat", "head", "tail", "less", "more", "bat", "type", "get-content", "gc", "grep", "egrep", "fgrep", "rg", "sed", "awk", "cp",
            "scp", "base64", "xxd", "strings", "source", ".", "od", "hexdump", "tr", "cut", "sort", "tac", "nl", "rsync", "curl", "wget",
            "open", "code", "vim", "vi", "nano", "ag", "ack", "findstr", "select-string", "sls", "copy", "xcopy", "mv", "move"}
_REMOTE = {"ssh", "scp", "sftp", "rsync", "nc", "ncat", "netcat", "socat", "telnet", "ftp", "mosh"}
_PUBLISH = {("npm", "publish"), ("pnpm", "publish"), ("yarn", "publish"), ("yarn", "npm"), ("twine", "upload"), ("cargo", "publish"),
            ("gem", "push"), ("docker", "push"), ("gh", "release"), ("vsce", "publish"), ("uv", "publish"), ("poetry", "publish"),
            ("dotnet", "nuget"), ("mvn", "deploy"), ("gradle", "publish"), ("helm", "push"), ("ovsx", "publish")}


def _flags(args: list) -> str:
    return "".join(a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--") and len(a) > 1)


def _targets(args: list) -> list:
    out, after = [], False
    for a in args:
        if after:
            out.append(a)
        elif a == "--":
            after = True
        elif not a.startswith("-") or a == "-":
            out.append(a)
    return out


def _delete_event(targets: list, ctx: Ctx, force: bool, via: str) -> Optional[tuple]:
    if not targets:
        return None
    best = max(targets[:12], key=lambda t: _SCOPE_RANK.get(ctx.scope(t), 1))
    scope = ctx.scope(best)
    return ("shell.delete_recursive", {"scope": scope, "target": hide_secrets(best, 80), "force": force, "via": via})


def _git(args: list, ctx: Ctx) -> list:
    sub = next((a for a in args if not a.startswith("-")), "")
    rest = args[args.index(sub) + 1:] if sub in args else []
    f = _flags(rest) + " " + " ".join(a for a in rest if a.startswith("--"))
    out = []
    if sub == "push":
        pos = [a for a in rest if not a.startswith("-")]
        force = bool(re.search(r"\b(force|force-with-lease)\b", f)) or "f" in _flags(rest) or any(a.startswith("+") for a in pos)
        branch = ""
        for a in pos[1:]:
            branch = a.lstrip("+").split(":")[-1].split("/")[-1] if ":" not in a else a.split(":")[-1]
            break
        if "--delete" in rest or any(a.startswith(":") for a in pos):
            out.append(("git.force_push", {"protected_branch": bool(_PROTECTED.match(branch.lstrip(":"))), "branch": branch.lstrip(":")[:40], "kind": "delete_remote_branch"}))
        elif force:
            out.append(("git.force_push", {"protected_branch": bool(_PROTECTED.match(branch)), "branch": branch[:40] or "(current)", "kind": "force"}))
    elif sub == "reset" and "--hard" in rest:
        out.append(("git.discard_changes", {"kind": "reset_hard"}))
    elif sub == "clean" and ("f" in _flags(rest) or "--force" in rest):
        out.append(("git.discard_changes", {"kind": "clean"}))
    elif sub in ("checkout", "restore") and any(a in (".", "--", ":/") for a in rest) and "." in rest:
        out.append(("git.discard_changes", {"kind": "checkout_all"}))
    elif sub == "branch" and ("D" in _flags(rest) or "--delete" in rest and "--force" in rest):
        out.append(("git.discard_changes", {"kind": "branch_force_delete"}))
    elif sub in ("filter-branch", "filter-repo"):
        out.append(("git.discard_changes", {"kind": "rewrite_history"}))
    elif sub == "stash" and rest[:1] in (["drop"], ["clear"]):
        out.append(("git.discard_changes", {"kind": "stash_drop"}))
    return out


def _infra(prog: str, args: list, text: str) -> Optional[tuple]:
    a = [x for x in args if not x.startswith("-")]
    s = " ".join(args).lower()
    action = None
    if prog in ("terraform", "tofu") and (("destroy" in a[:1]) or ("apply" in a[:1] and "-auto-approve" in args)):
        action = "destroy" if "destroy" in a[:1] else "apply_auto_approve"
    elif prog == "kubectl" and a[:1] in (["delete"], ["drain"]):
        action = a[0]
    elif prog == "helm" and a[:1] in (["uninstall"], ["delete"]):
        action = "uninstall"
    elif prog == "docker" and (a[:2] in (["system", "prune"], ["volume", "rm"], ["volume", "prune"]) or (a[:1] == ["rm"] and "-f" in args and "-v" in args)):
        action = "prune_or_volume_delete"
    elif prog == "aws" and (any(re.match(r"^(delete|terminate|remove|deregister|destroy|purge)-", x) for x in a) or a[:2] in (["s3", "rm"], ["s3", "rb"]) and ("--recursive" in args or a[1] == "rb")):
        action = "aws_delete"
    elif prog in ("gcloud", "az", "doctl", "linode-cli", "hcloud") and "delete" in a:
        action = "cloud_delete"
    elif prog == "gh" and a[:2] == ["repo", "delete"]:
        action = "repo_delete"
    elif prog in ("heroku",) and any(x in s for x in ("destroy", "pg:reset", "pg:backups:delete")):
        action = "destroy"
    elif prog in ("railway", "fly", "flyctl", "vercel", "netlify", "supabase", "pscale", "neonctl", "wrangler", "firebase") and any(
            x in a for x in ("delete", "destroy", "remove", "rm", "down")) and prog != "supabase":
        action = "delete"
    elif prog == "supabase" and (a[:2] in (["db", "reset"], ["projects", "delete"])):
        action = "db_reset"
    if action:
        return ("infra.destructive", {"tool": prog, "action": action, "production_hint": bool(_PROD.search(text))})
    return None


def _net(prog: str, args: list, ctx: Ctx, text: str) -> Optional[tuple]:
    uploads, secret = False, False
    i = 0
    host = ""
    for t in args:
        m = re.match(r"https?://([^/\s:?#]+)", t)
        if m and not host:
            host = m.group(1)
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else ""
        for flag in ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "-F", "--form", "--json", "--post-file", "--body-file"):
            val = None
            if a == flag:
                val = nxt
            elif a.startswith(flag + "=") and flag.startswith("--"):
                val = a.split("=", 1)[1]
            if val is not None:
                at = val.split("=", 1)[-1] if flag in ("-F", "--form") else val
                if at.startswith("@") or flag in ("--post-file", "--body-file"):
                    uploads = True
                    secret = secret or bool(secret_kind(at.lstrip("@")))
        if a in ("-T", "--upload-file"):
            uploads = True
            secret = secret or bool(secret_kind(nxt))
        i += 1
    for m in re.finditer(r"\$\((?:cat|type|get-content)\s+([^)]+)\)|<\s*([^\s|&;]+)", text):
        p = (m.group(1) or m.group(2) or "").strip().split()[0] if (m.group(1) or m.group(2)) else ""
        if p and secret_kind(p):
            uploads = secret = True
    if uploads:
        return ("net.upload", {"program": prog, "host": host[:60], "secret_file": secret})
    return ("net.fetch", {"program": prog, "host": host[:60]})


_HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")
_PS_HERE = re.compile(r"@(['\"])[ \t]*\r?\n.*?\r?\n[ \t]*\1@", re.S)


def strip_heredocs(cmd: str) -> str:
    """Remove here-document bodies (a `<<MARK` block, a PowerShell @' block): they are text or code, not commands of their own."""
    cmd = _PS_HERE.sub("@HERE", cmd)
    out, pending = [], []
    for line in cmd.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        out.append(line)
        pending += [m.group(2) for m in _HEREDOC.finditer(line)]
    return "\n".join(out)


def _blank_quotes(s: str) -> str:
    out, q = [], None
    for ch in s:
        if q:
            out.append(ch if ch == q else "_")
            if ch == q:
                q = None
        else:
            out.append(ch)
            if ch in "'\"":
                q = ch
    return "".join(out)


def _stdin_runs(prog: str, args: list) -> bool:
    """Does `<fetch> | prog args` run what was downloaded? (`| python -c "..."` or `| jq` only read it.)"""
    if prog in _SHELLS:
        return "-c" not in args and "-lc" not in args
    if prog in ("python", "python3", "node", "perl", "ruby", "php", "pwsh", "powershell"):
        return not args or args == ["-"]
    return False


def classify_command(cmd: str, ctx: Ctx, powershell: bool = False) -> list:
    """The things one shell command does: a list of (tool, params). A command that matches nothing is `shell.command`."""
    found: list = []
    ctx = ctx.copy()
    cmd = strip_heredocs(cmd)
    segs = split_command(cmd)
    progs = []
    for idx, (seg, op) in enumerate(segs):
        toks = _words(seg, posix=not powershell)
        # NAME=value or $name = "value" on a line of its own: remember it so a later `rm -rf "$NAME/x"` can be placed
        am = re.match(r"^\$?([A-Za-z_]\w*)\s*=\s*(.*)$", seg)
        if am and (len(toks) == 1 or (powershell and seg.lstrip().startswith("$"))):
            vtoks = _words(am.group(2), posix=not powershell)
            ctx.vars[am.group(1)] = vtoks[0].strip("'\"") if vtoks else ""
            progs.append("")
            continue
        if toks and toks[0].lower() in ("cd", "pushd", "set-location", "sl", "chdir"):
            tg = [t for t in toks[1:] if not t.startswith("-") or t == "-"]
            ctx.base = ctx.resolve(tg[0]) if tg and tg[0] != "-" else None
            progs.append("cd")
            continue
        if powershell:
            toks = [t.strip("'\"") for t in toks]
        prog, args, sudo = _program(toks)
        if toks[:1] == ["env"] and len(toks) == 1:
            prog, args = "printenv", []
        progs.append(prog)
        if not prog:
            continue
        if sudo:
            found.append(("shell.sudo", {"program": prog}))
        # a shell started with -c: look inside the string it runs
        if prog in _INTERP and ("-c" in args or "-command" in [x.lower() for x in args] or "-lc" in args or "-ic" in args):
            k = next((j for j, x in enumerate(args) if x in ("-c", "-lc", "-ic") or x.lower() == "-command"), None)
            if k is not None and k + 1 < len(args) and prog != "python" and prog != "python3" and prog != "node":
                found += [f for f in classify_command(args[k + 1], ctx, powershell=prog in ("powershell", "pwsh")) if f[0] != "shell.command"]
        if prog == "eval" and args:
            found += [f for f in classify_command(" ".join(args), ctx) if f[0] != "shell.command"]
        # removal
        flags = _flags(args)
        long = " ".join(a for a in args if a.startswith("--")).lower()
        if prog in ("rm", "unlink", "shred") and (("r" in flags or "R" in flags) or "--recursive" in long):
            ev = _delete_event(_targets(args), ctx, "f" in flags or "--force" in long, "rm")
            if ev:
                found.append(ev)
        elif prog == "xargs" and args and args[-1:] and any(x in ("rm", "rmdir") for x in args) and ("-r" in args or "-rf" in args or "-fr" in args):
            found.append(("shell.delete_recursive", {"scope": "piped_input", "target": "(from the previous command)", "force": True, "via": "xargs rm"}))
        elif prog == "find" and ("-delete" in args or ("-exec" in args and any(x in ("rm", "rmdir") for x in args))):
            root = next((a for a in args if not a.startswith("-") and not a.startswith("(") and a != "!"), ".")
            sc = ctx.scope(root)
            if sc == "project_root" and any(x in args for x in ("-name", "-iname", "-path", "-regex", "-type", "-newer", "-mtime", "-empty")):
                sc = "inside_project"                       # `find . -name '*.pyc' -delete` is not "delete the project"
            found.append(("shell.delete_recursive", {"scope": sc, "target": hide_secrets(root, 80), "force": True, "via": "find"}))
        elif prog in ("remove-item", "ri", "del", "erase", "rd", "rmdir") and (
                any(x.lower() in ("-recurse", "-r", "/s") for x in args) or ("-recurse" in long) or (prog in ("rd", "rmdir") and "/s" in [x.lower() for x in args])):
            ev = _delete_event([a for a in args if not a.startswith("-") and not a.startswith("/")], ctx, True, prog)
            if ev:
                found.append(ev)
        # git
        elif prog == "git":
            found += _git(args, ctx)
        # permissions
        elif prog in ("chmod", "icacls", "chown") and ("777" in args or "a+rwx" in args or "o+w" in args or ("-R" in args and "777" in " ".join(args))):
            found.append(("shell.chmod_open", {"program": prog, "recursive": "-R" in args or "/t" in [x.lower() for x in args]}))
        # databases
        elif prog in _DB_CLI and (_SQL_BAD.search(seg) or _SQL_DELETE_ALL.search(seg) or _DB_RESET.search(seg)) and (
                prog not in _SCRIPT_RUNNERS or _SQL_RUN_CUE.search(seg) or _DB_RESET.search(seg)):
            found.append(("db.destructive_sql", {"program": prog, "production_hint": bool(_PROD.search(seg))}))
        elif prog in ("dropdb", "flushall", "flushdb"):
            found.append(("db.destructive_sql", {"program": prog, "production_hint": bool(_PROD.search(seg))}))
        # infra
        elif _infra(prog, args, seg):
            found.append(_infra(prog, args, seg))
        # publishing
        elif (prog, next((a for a in args if not a.startswith("-")), "")) in _PUBLISH and not (prog == "gh" and "create" not in args):
            found.append(("package.publish", {"program": prog}))
        # network
        elif prog in ("curl", "wget", "http", "https", "xh", "invoke-webrequest", "iwr", "invoke-restmethod", "irm"):
            nxt = segs[idx + 1][0] if idx + 1 < len(segs) and op in ("|",) else ""
            nprog, _na, nsudo = _program(_words(nxt)) if nxt else ("", [], False)
            if nprog and _stdin_runs(nprog, _na):
                found.append(("shell.pipe_to_shell", {"fetcher": prog, "into": nprog, "sudo": nsudo or sudo}))
            else:
                ev = _net(prog, args, ctx, seg)
                if ev and ev[0] == "net.upload" and any(a in ("@-", "-") or a.endswith("=@-") for a in args) and any(f[0] == "secrets.read" for f in found):
                    ev[1]["secret_file"] = True             # the secret was piped in from the previous part of the command
                if ev:
                    found.append(ev)
        elif prog in _REMOTE and (prog in ("nc", "ncat", "netcat", "socat", "telnet", "ssh", "mosh") or any("@" in a or re.match(r"^[\w.\-]+:", a) for a in args)) \
                and not (prog in ("nc", "ncat", "netcat", "telnet") and (_targets(args)[:1] or [""])[0] in ("localhost", "127.0.0.1", "::1", "0.0.0.0")):
            found.append(("net.remote_access", {"program": prog}))
        # reading secrets
        if prog in _READERS or prog in ("env", "printenv", "set", "export", "get-childitem", "gci", "ls", "dir"):
            tgts = _targets(args)
            if prog in _PATTERN_FIRST and tgts and not any(a in ("-e", "-f", "--regexp", "--file") or a.startswith("--regexp=") for a in args):
                tgts = tgts[1:]                       # the first word is the pattern or the script, not a file it reads
            for t in tgts:
                k = secret_kind(t) if not t.startswith("$") else None
                if k:
                    found.append(("secrets.read", {"via": prog, "path_kind": k}))
                    break
        if prog in ("printenv", "env") and not _targets(args):
            found.append(("secrets.dump_env", {"program": prog}))
        elif prog in ("get-childitem", "gci", "ls", "dir") and any(re.match(r"^env:", a, re.I) for a in args):
            found.append(("secrets.dump_env", {"program": prog}))
        elif prog == "export" and "-p" in args:
            found.append(("secrets.dump_env", {"program": prog}))
        # redirection into a sensitive file
        blank = _blank_quotes(seg)
        for m in re.finditer(r"(?<![<>&\d\-=|])>>?\s*(\"[^\"]+\"|'[^']+'|[^\s|&;<>()]+)", blank):
            tgt = seg[m.start(1):m.end(1)].strip("'\"")
            if tgt in ("/dev/null", "/dev/stderr", "/dev/stdout", "nul", "$null") or tgt.startswith("&"):
                continue
            res = ctx.resolve(tgt)
            kind = write_kind(res or tgt)
            sc = ctx.scope(tgt)
            if kind != "normal" or sc not in ("inside_project", "temp", "project_root"):
                found.append(("file.write", {"scope": sc, "kind": kind, "path": hide_secrets(tgt, 80), "via": "redirect"}))
    # a download piped into an interpreter that curl_matched above, or `bash <(curl ...)`
    if re.search(r"\b(ba|z|da|k)?sh\s+(-\w+\s+)*<\(\s*(curl|wget)\b|\b(ba|z)?sh\s+-c\s+[\"']\$\(\s*(curl|wget)\b", cmd) and not any(f[0] == "shell.pipe_to_shell" for f in found):
        found.append(("shell.pipe_to_shell", {"fetcher": "curl", "into": "sh", "sudo": False}))
    if not found:
        first = next((p for p in progs if p), "")
        found.append(("shell.command", {"program": first[:30]}))
    # one event per distinct (tool, params)
    seen, out = set(), []
    for t, p in found:
        key = (t, json.dumps(p, sort_keys=True))
        if key not in seen:
            seen.add(key)
            out.append((t, p))
    return out


# ───────────────────────────── one tool call → events ─────────────────────────────
_IGNORE = {"TodoWrite", "ExitPlanMode", "EnterPlanMode", "AskUserQuestion", "ToolSearch", "TaskCreate", "TaskUpdate", "TaskList",
           "TaskGet", "TaskOutput", "TaskStop", "SendMessage", "KillShell", "BashOutput", "ListMcpResourcesTool", "ReadMcpResourceTool",
           "ScheduleWakeup", "CronCreate", "CronDelete", "CronList", "Monitor", "PushNotification", "EnterWorktree", "ExitWorktree", "Skill"}


def events_for_call(name: str, inp: dict, ctx: Ctx) -> list:
    """[(tool, params, preview)] for one tool call of the agent. Nothing for tools that are not actions (todo lists, questions)."""
    if name in _IGNORE:
        return []
    inp = inp if isinstance(inp, dict) else {}
    if name in ("Bash", "PowerShell"):
        cmd = str(inp.get("command") or "")
        return [(t, p, hide_secrets(cmd)) for t, p in classify_command(cmd, ctx, powershell=(name == "PowerShell"))]
    path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""
    if name == "Read":
        k = secret_kind(str(path))
        if k:
            return [("secrets.read", {"via": "Read", "path_kind": k}, hide_secrets(str(path)))]
        return [("file.read", {"scope": ctx.scope(str(path)) if path else "unresolved_variable"}, hide_secrets(str(path)))]
    if name in ("Glob", "Grep", "LS"):
        return [("file.read", {"scope": ctx.scope(str(path)) if path else "inside_project"}, hide_secrets(str(inp.get("pattern") or path)))]
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        res = ctx.resolve(str(path)) if path else None
        return [("file.write", {"scope": ctx.scope(str(path)) if path else "unresolved_variable", "kind": write_kind(res or str(path)),
                                "path": hide_secrets(str(path), 80), "via": name}, hide_secrets(str(path)))]
    if name in ("WebFetch", "WebSearch"):
        m = re.match(r"https?://([^/\s:?#]+)", str(inp.get("url") or ""))
        return [("web.fetch", {"domain": (m.group(1) if m else "search")[:60]}, hide_secrets(str(inp.get("url") or inp.get("query") or "")))]
    if name in ("Task", "Agent"):
        return [("agent.spawn", {"kind": str(inp.get("subagent_type") or "")[:30]}, hide_secrets(str(inp.get("description") or "")))]
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        server, tool = (parts[1], parts[2]) if len(parts) == 3 else ("", name)
        guess = _classify_name(tool)
        effect = "read" if guess["risk"] == "low" else ("unknown" if guess["why"].startswith("name not recognised") else "change")
        return [("mcp.call", {"server": server[:40], "tool": tool[:60], "effect": effect}, f"{server}/{tool}")]
    return [("agent.other", {"name": name[:40]}, name)]


# ───────────────────────────── reading Claude Code transcripts ─────────────────────────────
def claude_root(root: Optional[str] = None) -> Path:
    if root:
        return Path(root).expanduser()
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base).expanduser() if base else Path.home() / ".claude") / "projects"


def _ts(v) -> Optional[float]:
    if not v:
        return None
    try:
        return _dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _text_len(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) if isinstance(b, dict) else len(str(b)) for b in content)
    return 0


def read_calls(path: Path, since: Optional[float] = None) -> list:
    """Every tool call in one transcript file, with its outcome: [{id, name, input, at, cwd, session, error, result_chars}]."""
    calls: dict = {}
    results: dict = {}
    try:
        f = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return []
    with f:
        for line in f:
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            msg = o.get("message") if isinstance(o, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and isinstance(b.get("id"), str):
                    calls[b["id"]] = {"id": b["id"], "name": str(b.get("name") or ""), "input": b.get("input") or {},
                                      "at": _ts(o.get("timestamp")), "cwd": str(o.get("cwd") or ""), "session": str(o.get("sessionId") or path.stem),
                                      "sidechain": bool(o.get("isSidechain"))}
                elif b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str):
                    results[b["tool_use_id"]] = {"error": bool(b.get("is_error")), "chars": _text_len(b.get("content"))}
    out = []
    for cid, c in calls.items():
        if since is not None and (c["at"] is None or c["at"] < since):
            continue
        r = results.get(cid, {})
        c["error"] = r.get("error", False)
        c["result_chars"] = r.get("chars", 0)
        out.append(c)
    return out


def scan_transcripts(root: Optional[str] = None, since: Optional[float] = None, project: Optional[str] = None) -> dict:
    """Read all transcripts under `root`. Returns {"events": [...], "calls": n, "sessions": n, "files": n, "projects": n, "meta": {id: {...}}}.
    Each event is {"tool", "params", "external_id", "occurred_at"}; `meta[external_id]` holds the masked preview, the project and the outcome;
    `calls_info` has one row per tool call (for the output-size and failure statistics)."""
    rootp = claude_root(root)
    if not rootp.is_dir():
        raise FileNotFoundError(f"no Claude Code transcripts at {rootp}. Use --root to point at them.")
    events, meta, calls_info = [], {}, []
    sessions, projects, files, ncalls = set(), set(), 0, 0
    seen_calls: set = set()
    for fp in sorted(rootp.rglob("*.jsonl")):
        try:
            if since is not None and fp.stat().st_mtime < since:
                continue                                  # not touched since the period began: it cannot hold a newer call
        except OSError:
            continue
        files += 1
        for c in read_calls(fp, since):
            if c["id"] in seen_calls:
                continue
            seen_calls.add(c["id"])
            proj = c["cwd"].replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "(unknown)"
            if project and project.lower() not in (c["cwd"].lower() + " " + fp.parent.name.lower()):
                continue
            ctx = Ctx(c["cwd"])
            evs = events_for_call(c["name"], c["input"], ctx)
            if not evs:
                continue
            ncalls += 1
            sessions.add(c["session"])
            projects.add(proj)
            calls_info.append({"tool": c["name"], "preview": evs[0][2], "project": proj, "session": c["session"], "error": c["error"],
                               "chars": c["result_chars"], "at": c["at"]})
            for k, (tool, params, preview) in enumerate(evs):
                ext = c["id"] if k == 0 else f"{c['id']}#{k}"
                events.append({"tool": tool, "params": params, "external_id": ext,
                               "occurred_at": c["at"] if c["at"] is not None else 0.0})
                meta[ext] = {"preview": preview, "project": proj, "source_tool": c["name"], "error": c["error"],
                             "chars": c["result_chars"], "session": c["session"]}
    events.sort(key=lambda e: e["occurred_at"])
    return {"events": events, "calls": ncalls, "sessions": len(sessions), "files": files, "projects": len(projects), "meta": meta,
            "calls_info": calls_info}
