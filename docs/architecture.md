# Architecture

## Overview

Octobot is a Python application composed of three independent entry points that share the same core modules:

```
┌─────────────────────────────────────────────────────┐
│                    Entry Points                      │
│  octobot-daemon  │  analyze (CLI)  │  octobot-setup  │
└────────┬─────────┴────────┬────────┴────────┬────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────┐
│                    Core Modules                      │
│  scheduler  │  analyzer  │  youtrack  │  state       │
└─────────────┴─────┬──────┴─────┬──────┴─────────────┘
                    │            │
                    ▼            ▼
            Anthropic API   YouTrack REST API
```

---

## Modules

### `config.py`
Loads and validates `config.yaml`. Supports `${ENV_VAR}` substitution in any string value. The config is searched in order: `$OCTOBOT_CONFIG` → `./config.yaml` → `~/.octobot/config.yaml` → `/etc/octobot/config.yaml`.

### `youtrack.py`
Thin wrapper around the YouTrack REST API. All requests go through a single `requests.Session` with the Bearer token set. Handles URL normalization (e.g. `mycompany` → `https://mycompany.youtrack.cloud`) and optional SSL verification bypass for corporate proxy environments.

Key operations:
- `get_new_bugs()` — YouTrack query: `project: X tag: {bug_tag} -tag: {ignore_tag} created: cutoff .. Today`
- `get_issue()` — fetch a single issue by readable ID
- `add_comment()` / `delete_comment()` — post and replace bot comments
- `get_bot_comment()` — find existing comments by bot login (used for duplicate detection)

### `analyzer.py`
The core analysis engine. For each ticket:

1. **Sync repos** — `git pull` on each configured repo, or `git clone` if the path does not exist. If a repo fails, it is skipped with a warning; others continue.
2. **Read CLAUDE.md** — concatenates the `CLAUDE.md` from each available repo, labelled by repo name.
3. **Build file list** — runs `git ls-files` on each repo, prefixes each path with the repo name (`backend:src/foo.py`).
4. **File selection call** — sends CLAUDE.md + file list + ticket to Claude. Claude returns the 10 most relevant file paths.
5. **Read files** — reads those files from disk.
6. **Analysis call** — sends CLAUDE.md + ticket + file contents to Claude. Claude returns the structured analysis in the ticket's language.

### `state.py`
SQLite-backed state store. Single table `analyzed_tickets` with columns: `ticket_id`, `analyzed_at`, `comment_id`, `status` (`analyzed` | `error`). Used to prevent re-processing tickets the daemon has already handled.

On startup, if a ticket is not found in the local DB, the analyzer falls back to querying YouTrack directly for an existing bot comment — this makes the system resilient to DB loss or reinstallation.

### `scheduler.py`
Polling loop for the daemon. On each cycle:
1. Checks if current time is within active hours (`start_hour`–`end_hour`). If not, sleeps until `start_hour`.
2. Queries YouTrack for new unanalyzed bug tickets.
3. For each ticket, checks local DB and YouTrack for existing bot comments.
4. Processes the queue, stopping early if active hours are exceeded mid-run.

### `cli.py`
The `analyze` command. Designed for SSH-based manual use:
- Without `--comment`: runs analysis and prints to terminal. Never posts.
- With `--comment`: runs analysis, prints, asks confirmation, posts. Warns and asks again if a previous bot comment exists.

### `wizard.py`
Interactive setup wizard. Zero external dependencies (stdlib only) — can be run before `pip install`. Validates YouTrack and Anthropic tokens over the network, auto-detects the default git branch via `git ls-remote --symref`, handles SSL bypass for corporate environments.

---

## Data flow — daemon

```
YouTrack poll
    │
    ▼
Filter: bug_tag + not ignore_tag + created >= cutoff_date
    │
    ▼
For each ticket not in state DB (and no bot comment on YouTrack)
    │
    ├─► git pull all repos
    │
    ├─► Claude call 1: which files?
    │       input:  CLAUDE.md + file tree + ticket
    │       output: list of repo:path
    │
    ├─► read files from disk
    │
    ├─► Claude call 2: analyze
    │       input:  CLAUDE.md + files + ticket
    │       output: analysis (in ticket's language)
    │
    └─► POST comment to YouTrack
            └─► save to state DB
```

---

## State DB schema

```sql
CREATE TABLE analyzed_tickets (
    ticket_id   TEXT PRIMARY KEY,
    analyzed_at TEXT NOT NULL,   -- ISO8601 UTC
    comment_id  TEXT,            -- YouTrack comment ID, null on error
    status      TEXT NOT NULL    -- 'analyzed' | 'error'
);
```

---

## SSL and corporate proxies

Some corporate networks use SSL inspection proxies that replace the server certificate with a company-issued one. Python's `ssl` module rejects these by default. Octobot exposes `ssl_verify: false` in the YouTrack config section to disable certificate verification. This affects both the YouTrack REST client (`requests`) and the wizard's validation calls (`urllib`). The Anthropic SDK uses its own HTTP stack and is not affected.

---

## Git authentication

| URL type | Auth mechanism |
|---|---|
| SSH (`git@host:...`) | System SSH key (`~/.ssh/`) — no token needed |
| HTTPS + `git_token` | Token injected into clone URL: `https://TOKEN@host/...` |
| HTTPS, no token | Interactive prompt (or credential helper) |

The `git_token` is only injected during `git clone`. Subsequent `git pull` operations rely on the credentials stored by git's credential helper, or the SSH key for SSH remotes.
