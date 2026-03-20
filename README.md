# Octobot

Automated bug analysis daemon for YouTrack, powered by Claude (Anthropic API).

Octobot monitors your YouTrack project for new bug tickets, reads the relevant source code, and posts a structured analysis comment directly on each ticket — root cause, affected code, and proposed fix. It responds in the same language as the ticket.

---

## How it works

1. **Polling** — Octobot polls YouTrack every N minutes for tickets tagged as bugs, created after a configurable cutoff date, without the `octobot-ignore` tag.
2. **Analysis** — For each new ticket it pulls the latest code from all configured repositories, reads the `CLAUDE.md` project guide, identifies relevant files, and generates a structured analysis via Claude API.
3. **Commenting** — The analysis is posted as a comment on the YouTrack ticket under the bot account.
4. **State tracking** — Every analyzed ticket is recorded in a local SQLite database so it is never processed twice, unless explicitly requested.
5. **Schedule** — The daemon is active between configurable hours (default 08:00–21:00). Tickets that arrive overnight are picked up at the next wake.

---

## Requirements

- Python 3.11+
- Git
- A YouTrack Cloud instance with a permanent API token
- An Anthropic API key
- One or more git repositories accessible from the server (SSH or HTTPS)

---

## Installation

### 1. Clone this repository on the target server

```bash
git clone https://github.com/your-org/octobot.git /opt/octobot-src
cd /opt/octobot-src
```

### 2. Run the setup wizard

The wizard requires no dependencies beyond Python 3.11+. It will:
- Collect and validate your YouTrack and Anthropic tokens
- Configure your repositories (SSH or HTTPS), detect the default branch, and optionally clone them
- Set active hours, poll interval, log paths
- Write a `config.yaml` with `chmod 600`

```bash
python3 setup_wizard.py
```

### 3. Install system-wide

```bash
sudo bash install.sh
```

This will:
- Create an `octobot` system user
- Install the package into `/opt/octobot/.venv`
- Symlink `analyze` and `octobot-status` to `/usr/local/bin`
- Install the `octobot.service` systemd unit

### 4. Start the daemon

```bash
sudo systemctl enable --now octobot
sudo journalctl -fu octobot
```

---

## Configuration

The config file is searched in this order:

1. `$OCTOBOT_CONFIG` environment variable
2. `config.yaml` in the current working directory
3. `~/.octobot/config.yaml` (default for non-root installs)
4. `/etc/octobot/config.yaml` (default for root/systemd installs)

Any string value in the config can reference an environment variable using `${VAR}` syntax:

```yaml
youtrack:
  token: "${YOUTRACK_TOKEN}"
anthropic:
  token: "${ANTHROPIC_TOKEN}"
repositories:
  - name: "backend"
    git_token: "${GITLAB_TOKEN}"
```

See [`config/config.yaml.example`](config/config.yaml.example) for the full reference.

> **Security note:** `config.yaml` contains API tokens. It is written with `chmod 600` by the wizard and must never be committed to version control. It is listed in `.gitignore`.

---

## The CLAUDE.md guide

Each repository should have a `CLAUDE.md` at its root (path configurable via `claude_md_path`). This file is the primary way you tell the bot about your codebase — architecture, key files, conventions, known bug-prone areas.

A well-written `CLAUDE.md` directly reduces API costs by letting Claude go straight to the relevant code instead of exploring the whole tree.

A template is provided at [`config/CLAUDE.md.example`](config/CLAUDE.md.example).

---

## Controlling analysis with YouTrack tags

| Tag | Effect |
|---|---|
| `octobot-ignore` | Daemon skips this ticket entirely |

Add `octobot-ignore` to tickets that are still being defined, are duplicates, or should not be analyzed automatically. Remove the tag later to let the daemon pick it up on the next poll, or trigger manual analysis with `analyze TICKET`.

---

## CLI commands

All commands are available system-wide after installation. Use `OCTOBOT_CONFIG=/path/to/config.yaml <command>` to target a non-default config.

### `analyze`

```
analyze TICKET_ID [--comment]
```

| Usage | Behaviour |
|---|---|
| `analyze OR-123` | Runs analysis and prints it to the terminal. **Never posts to YouTrack.** |
| `analyze --comment OR-123` | Runs analysis, prints it, asks for posting confirmation, then posts. If a previous bot comment exists, warns and asks before replacing it. |

### `octobot-status`

```
octobot-status [--all] [--reset TICKET_ID]
```

| Usage | Behaviour |
|---|---|
| `octobot-status` | Shows summary and last 10 analyzed tickets. |
| `octobot-status --all` | Shows all tickets in the state DB. |
| `octobot-status --reset OR-123` | Removes a ticket from the state DB so the daemon will re-analyze it on next poll. Asks for confirmation. |

### `octobot-setup`

Re-runs the interactive setup wizard. Useful to update tokens, add a repository, or change the schedule.

```bash
octobot-setup
```

### `octobot-daemon`

The daemon entry point, managed by systemd. Can also be run directly for testing:

```bash
OCTOBOT_CONFIG=/etc/octobot/config.yaml octobot-daemon
```

---

## Multi-repository support

Octobot can analyze tickets across multiple repositories simultaneously. Each repo has a short `name` used as a prefix in file references (e.g. `backend:src/api/handler.py`). Claude sees the combined file tree of all repos and picks the relevant files across all of them.

```yaml
repositories:
  - name: "backend"
    url: "git@github.com:org/backend.git"
    path: "/opt/repos/backend"
    branch: "main"
  - name: "frontend"
    url: "git@github.com:org/frontend.git"
    path: "/opt/repos/frontend"
    branch: "main"
```

If a repository path does not exist at runtime, Octobot will attempt to clone it automatically. If one repo fails (permissions, network), it is skipped and the others are still analyzed.

---

## Logs

```bash
# Live logs via systemd
sudo journalctl -fu octobot

# Log file
tail -f /var/log/octobot/octobot.log
```

Log rotation: 10 MB per file, 5 files kept (configurable via `state.log_max_bytes` and `state.log_backup_count`).

---

## Adding a new repository

1. Add an entry to the `repositories` list in `config.yaml`.
2. Add a `CLAUDE.md` to the repo (see template).
3. Restart the daemon: `sudo systemctl restart octobot`.

The daemon will clone the repo automatically on next start if `url` is set and the path does not exist.

---

## Project structure

```
octobot/
├── src/octobot/
│   ├── analyzer.py     — core analysis logic (git sync, Claude API calls)
│   ├── cli.py          — analyze command
│   ├── config.py       — config loading, env var expansion, dataclasses
│   ├── daemon.py       — daemon entry point and logging setup
│   ├── scheduler.py    — polling loop, active hours, ticket queue
│   ├── state.py        — SQLite state tracking
│   ├── status.py       — octobot-status command
│   ├── wizard.py       — interactive setup wizard
│   └── youtrack.py     — YouTrack REST API client
├── config/
│   ├── config.yaml.example
│   └── CLAUDE.md.example
├── docs/
│   ├── architecture.md
│   ├── configuration.md
│   └── writing-claude-md.md
├── setup_wizard.py     — standalone wizard launcher (no install needed)
├── install.sh          — system installation script
├── octobot.service     — systemd unit
└── pyproject.toml
```

---

## Cost considerations

Octobot makes two Claude API calls per ticket:

1. **File selection** — CLAUDE.md + combined file tree + ticket summary. Max 512 output tokens.
2. **Analysis** — selected file contents + ticket details. Max 2048 output tokens.

To keep costs low:
- Write a detailed `CLAUDE.md` — it eliminates guesswork in the file selection step.
- Use `octobot-ignore` on incomplete or irrelevant tickets.
- Prefer `claude-sonnet-4-6` (default) over Opus for routine analysis.
- The active hours window avoids polling when no one is working.
