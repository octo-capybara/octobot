# Configuration Reference

Octobot is configured via a single `config.yaml` file. All string values support `${ENV_VAR}` substitution.

## File location

The config is searched in this order:

| Priority | Location |
|---|---|
| 1 | `$OCTOBOT_CONFIG` environment variable |
| 2 | `./config.yaml` in the current directory |
| 3 | `~/.octobot/config.yaml` |
| 4 | `/etc/octobot/config.yaml` |

The wizard writes to `~/.octobot/config.yaml` for non-root users and `/etc/octobot/config.yaml` for root. Always `chmod 600`.

---

## `youtrack`

```yaml
youtrack:
  base_url: "https://mycompany.youtrack.cloud"
  token: "${YOUTRACK_TOKEN}"
  project: "OR"
  bot_login: "octobot"
  bug_tag: "tipo: bug"
  ignore_tag: "octobot-ignore"
  cutoff_date: "2025-01-01"
  ssl_verify: true
```

| Field | Required | Description |
|---|---|---|
| `base_url` | yes | YouTrack instance URL. Can be a short name (`mycompany`), hostname (`mycompany.youtrack.cloud`), or full URL. |
| `token` | yes | Permanent API token (`perm-…`). Generate at `Profile → Account Security → Tokens`. |
| `project` | yes | Project ID prefix (e.g. `OR` for tickets like `OR-123`). |
| `bot_login` | no | YouTrack username of the bot account. Used to find existing bot comments. Default: `octobot`. |
| `bug_tag` | no | Tag that identifies bug tickets. Default: `tipo: bug`. |
| `ignore_tag` | no | Tag that prevents a ticket from being analyzed. Default: `octobot-ignore`. |
| `cutoff_date` | no | Tickets created before this date are ignored. Format: `YYYY-MM-DD`. Default: `2024-01-01`. |
| `ssl_verify` | no | Set `false` if behind a corporate SSL-inspection proxy. Default: `true`. |

---

## `anthropic`

```yaml
anthropic:
  token: "${ANTHROPIC_TOKEN}"
  model: "claude-sonnet-4-6"
```

| Field | Required | Description |
|---|---|---|
| `token` | yes | Anthropic API key (`sk-ant-…`). |
| `model` | no | Model ID. Default: `claude-sonnet-4-6`. See [model comparison](#model-comparison). |

### Model comparison

| Model | Cost | Quality | Recommended for |
|---|---|---|---|
| `claude-haiku-4-5-20251001` | Low | Good | High-volume, simple bugs |
| `claude-sonnet-4-6` | Medium | High | Default — best balance |
| `claude-opus-4-6` | High | Highest | Complex architectural bugs |

---

## `repositories`

```yaml
repositories:
  - name: "backend"
    url: "git@github.com:org/backend.git"
    path: "/opt/repos/backend"
    branch: "main"
    claude_md_path: "CLAUDE.md"
    git_token: ""
```

One entry per repository. Add as many as needed.

| Field | Required | Description |
|---|---|---|
| `name` | yes | Short identifier used as file path prefix (e.g. `backend:src/foo.py`). |
| `path` | yes | Absolute local path to the cloned repository. |
| `url` | no | Git remote URL. Used to clone automatically if `path` does not exist. |
| `branch` | no | Branch to pull before each analysis. Default: `main`. |
| `claude_md_path` | no | Path to the CLAUDE.md file, relative to the repo root. Default: `CLAUDE.md`. |
| `git_token` | no | Personal access token for private HTTPS repos. Injected as `https://TOKEN@host/...`. Leave empty for SSH or public repos. |

**SSH vs HTTPS:**
- SSH URL (`git@host:org/repo.git`) — uses the system SSH key, no token needed.
- HTTPS URL (`https://host/org/repo.git`) — requires `git_token` for private repos.

---

## `scheduler`

```yaml
scheduler:
  start_hour: 8
  end_hour: 21
  poll_interval_minutes: 15
```

| Field | Default | Description |
|---|---|---|
| `start_hour` | `8` | Hour of day when the daemon becomes active (0–23). |
| `end_hour` | `21` | Hour of day when the daemon stops (0–24, exclusive). |
| `poll_interval_minutes` | `15` | How often to poll YouTrack for new tickets. |

Tickets that arrive while the daemon is inactive are picked up at the next `start_hour`.

---

## `state`

```yaml
state:
  db_path: "~/.octobot/state.db"
  log_file: "/var/log/octobot/octobot.log"
  log_max_bytes: 10485760
  log_backup_count: 5
```

| Field | Default | Description |
|---|---|---|
| `db_path` | `~/.octobot/state.db` | SQLite database path. `~` is expanded. Created automatically. |
| `log_file` | `/var/log/octobot/octobot.log` | Rotating log file path. Falls back to stdout-only if not writable. |
| `log_max_bytes` | `10485760` (10 MB) | Maximum size of a single log file before rotation. |
| `log_backup_count` | `5` | Number of rotated log files to keep. |

---

## Environment variable substitution

Any string value in the config can reference an environment variable:

```yaml
youtrack:
  token: "${YOUTRACK_TOKEN}"
```

If the variable is not set, the value is replaced with an empty string and a warning is printed to stderr. To set variables for the systemd service:

```ini
# /etc/systemd/system/octobot.service
[Service]
Environment=YOUTRACK_TOKEN=perm-...
Environment=ANTHROPIC_TOKEN=sk-ant-...
Environment=GITLAB_TOKEN=glpat-...
```

Reload after editing: `sudo systemctl daemon-reload && sudo systemctl restart octobot`.
