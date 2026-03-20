import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".octobot" / "config.yaml"


@dataclass
class YouTrackConfig:
    base_url: str
    token: str
    project: str
    bot_login: str = "octobot"
    bug_tag: str = "tipo: bug"
    ignore_tag: str = "octobot-ignore"
    cutoff_date: str = "2024-01-01"
    ssl_verify: bool = True     # set False if behind a corporate SSL-inspection proxy


@dataclass
class AnthropicConfig:
    token: str
    model: str = "claude-sonnet-4-6"


@dataclass
class RepositoryConfig:
    name: str                   # short identifier used as prefix in file paths, e.g. "backend"
    path: str                   # absolute local path
    url: str = ""               # git remote — used to clone if path doesn't exist
    branch: str = "main"
    claude_md_path: str = "CLAUDE.md"
    git_token: str = ""         # optional token injected in HTTPS URL for private repos


@dataclass
class SchedulerConfig:
    start_hour: int = 8
    end_hour: int = 21
    poll_interval_minutes: int = 15


@dataclass
class StateConfig:
    db_path: str = str(Path.home() / ".octobot" / "state.db")
    log_file: str = "/var/log/octobot/octobot.log"
    log_max_bytes: int = 10_485_760
    log_backup_count: int = 5


@dataclass
class OctobotConfig:
    youtrack: YouTrackConfig
    anthropic: AnthropicConfig
    repositories: list[RepositoryConfig]
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    state: StateConfig = field(default_factory=StateConfig)


def load_config(config_path: str | None = None) -> OctobotConfig:
    path = Path(config_path) if config_path else _find_config()

    if not path.exists():
        print(f"Config file not found: {path}", file=sys.stderr)
        print(f"Create one from the example: cp config.yaml.example {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        raw = yaml.safe_load(f)

    _expand_env(raw)

    try:
        repos = [RepositoryConfig(**r) for r in raw["repositories"]]

        return OctobotConfig(
            youtrack=YouTrackConfig(**raw["youtrack"]),
            anthropic=AnthropicConfig(**raw["anthropic"]),
            repositories=repos,
            scheduler=SchedulerConfig(**raw.get("scheduler", {})),
            state=StateConfig(**raw.get("state", {})),
        )
    except (KeyError, TypeError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)


def _expand_env(obj):
    """Recursively expand ${VAR} placeholders in string values using os.environ."""
    import re
    pattern = re.compile(r"\$\{([^}]+)\}")

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                def replacer(m):
                    var = m.group(1)
                    val = os.environ.get(var)
                    if val is None:
                        print(f"Warning: env var '{var}' referenced in config is not set.", file=sys.stderr)
                        return ""
                    return val
                obj[key] = pattern.sub(replacer, value)
            else:
                _expand_env(value)
    elif isinstance(obj, list):
        for item in obj:
            _expand_env(item)


def _find_config() -> Path:
    env = os.environ.get("OCTOBOT_CONFIG")
    if env:
        return Path(env)

    local = Path.cwd() / "config.yaml"
    if local.exists():
        return local

    return DEFAULT_CONFIG_PATH
