"""Interactive setup wizard for Octobot."""
from __future__ import annotations

import getpass
import json
import os
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path
from textwrap import dedent


# ──────────────────────────────────────────────────────────────────────────────
# ANSI colours (disabled automatically if not a TTY)
# ──────────────────────────────────────────────────────────────────────────────

def _supports_colour() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_COLOUR = _supports_colour()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text

def ok(text: str)   -> str: return _c("32", text)
def warn(text: str) -> str: return _c("33", text)
def err(text: str)  -> str: return _c("31", text)
def bold(text: str) -> str: return _c("1",  text)
def dim(text: str)  -> str: return _c("2",  text)


# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    """Prompt the user for input, showing a default value."""
    if default:
        display_prompt = f"  {prompt} {dim(f'[{default}]')}: "
    else:
        display_prompt = f"  {prompt}: "

    while True:
        try:
            if secret:
                value = getpass.getpass(display_prompt)
            else:
                value = input(display_prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print(err("\nSetup cancelled."))
            sys.exit(1)

        if value:
            return value
        if default:
            return default
        print(warn("    This field is required."))


def ask_int(prompt: str, default: int, min_val: int = 0, max_val: int = 9999) -> int:
    while True:
        raw = ask(prompt, str(default))
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(warn(f"    Must be between {min_val} and {max_val}."))
        except ValueError:
            print(warn("    Please enter a number."))


def ask_bool(prompt: str, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    raw = ask(prompt, default_str).lower()
    if raw in ("y", "yes", "y/n"):
        return True
    if raw in ("n", "no", "y/n", "n/y"):
        return not default if raw in ("y/n", "n/y") else False
    return default


def choose(prompt: str, options: list[tuple[str, str]], default: int = 1) -> str:
    """Present a numbered choice list, return the chosen value."""
    print(f"  {prompt}:")
    for i, (value, label) in enumerate(options, 1):
        marker = ok("▶") if i == default else " "
        print(f"    {marker} {i}) {label}")
    while True:
        raw = ask(f"Choose", str(default))
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
            print(warn(f"    Enter a number between 1 and {len(options)}."))
        except ValueError:
            print(warn("    Please enter a number."))


def section(title: str):
    print()
    print(bold(f"  ┌─ {title} {'─' * max(0, 52 - len(title))}"))
    print()


def rule():
    print(dim("  " + "─" * 56))


# ──────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_yt_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if "://" not in url:
        if "." not in url:
            url = f"{url}.youtrack.cloud"
        url = f"https://{url}"
    return url


def _http_get(url: str, headers: dict, verify_ssl: bool = True) -> dict | None:
    ctx = None
    if not verify_ssl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise ValueError(f"Connection error: {e.reason}")


def validate_youtrack(base_url: str, token: str, ssl_verify: bool = True) -> str:
    """Return the bot's YouTrack login if the token is valid."""
    url = f"{_normalize_yt_url(base_url)}/api/users/me?fields=login,name"
    data = _http_get(url, {"Authorization": f"Bearer {token}", "Accept": "application/json"}, ssl_verify)
    return data.get("login", "unknown")


def validate_anthropic(token: str, ssl_verify: bool = True) -> bool:
    """Return True if the Anthropic token is accepted."""
    url = "https://api.anthropic.com/v1/models"
    headers = {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "Accept": "application/json",
    }
    _http_get(url, headers, ssl_verify)
    return True


# ──────────────────────────────────────────────────────────────────────────────
# YAML writer (no PyYAML dependency needed at wizard-run time)
# ──────────────────────────────────────────────────────────────────────────────

def _write_yaml(cfg: dict) -> str:
    yt    = cfg["youtrack"]
    ant   = cfg["anthropic"]
    repos = cfg["repositories"]
    sch   = cfg["scheduler"]
    st    = cfg["state"]

    repos_block = ""
    for r in repos:
        repos_block += (
            f"  - name: \"{r['name']}\"\n"
            f"    url: \"{r['url']}\"\n"
            f"    path: \"{r['path']}\"\n"
            f"    branch: \"{r['branch']}\"\n"
            f"    claude_md_path: \"{r['claude_md_path']}\"\n"
            f"    git_token: \"{r.get('git_token', '')}\"\n"
        )

    return (
        f"youtrack:\n"
        f"  base_url: \"{yt['base_url']}\"\n"
        f"  token: \"{yt['token']}\"\n"
        f"  project: \"{yt['project']}\"\n"
        f"  bot_login: \"{yt['bot_login']}\"\n"
        f"  bug_tag: \"{yt['bug_tag']}\"\n"
        f"  ignore_tag: \"{yt['ignore_tag']}\"\n"
        f"  cutoff_date: \"{yt['cutoff_date']}\"\n"
        f"  ssl_verify: {str(yt.get('ssl_verify', True)).lower()}\n"
        f"\n"
        f"anthropic:\n"
        f"  token: \"{ant['token']}\"\n"
        f"  model: \"{ant['model']}\"\n"
        f"\n"
        f"repositories:\n"
        f"{repos_block}"
        f"\n"
        f"scheduler:\n"
        f"  start_hour: {sch['start_hour']}\n"
        f"  end_hour: {sch['end_hour']}\n"
        f"  poll_interval_minutes: {sch['poll_interval_minutes']}\n"
        f"\n"
        f"state:\n"
        f"  db_path: \"{st['db_path']}\"\n"
        f"  log_file: \"{st['log_file']}\"\n"
        f"  log_max_bytes: {st['log_max_bytes']}\n"
        f"  log_backup_count: {st['log_backup_count']}\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Wizard sections
# ──────────────────────────────────────────────────────────────────────────────

def _section_youtrack() -> dict:
    section("1 / 5  —  YouTrack")

    raw_url  = ask("Instance URL  (e.g. mycompany  or  https://mycompany.youtrack.cloud)")
    base_url = _normalize_yt_url(raw_url)
    if base_url != raw_url:
        print(dim(f"  → normalized to {base_url}"))

    ssl_verify = True
    login = "octobot"

    while True:
        token = ask("API Token  (perm-… or perm:…)", secret=True)
        print(f"  {dim('Testing connection...')} ", end="", flush=True)
        try:
            login = validate_youtrack(base_url, token, ssl_verify)
            print(ok(f"✓  Connected as '{login}'"))
            break
        except ValueError as e:
            msg = str(e)
            print(err(f"✗  {msg}"))

            if "SSL" in msg or "certificate" in msg.lower():
                print(warn("  SSL certificate verification failed — likely a corporate proxy."))
                if ask_bool("  Retry without SSL verification?", default=True):
                    ssl_verify = False
                    print(f"  {dim('Retrying without SSL verification...')} ", end="", flush=True)
                    try:
                        login = validate_youtrack(base_url, token, ssl_verify=False)
                        print(ok(f"✓  Connected as '{login}'"))
                        print(warn("  ssl_verify: false will be saved to config."))
                        break
                    except ValueError as e2:
                        print(err(f"✗  {e2}"))

            if not ask_bool("  Try a different token?", default=True):
                print(warn("  Skipping validation — fix the token in config.yaml later."))
                break

    project    = ask("Project key  (e.g. PROJ)")
    bot_login  = ask("Bot YouTrack username", default=login)
    bug_tag    = ask("Bug tag", default="tipo: bug")
    ignore_tag = ask("Ignore tag", default="octobot-ignore")
    cutoff     = ask("Cutoff date — ignore tickets before  (YYYY-MM-DD)", default="2025-01-01")

    return dict(
        base_url=base_url, token=token, project=project,
        bot_login=bot_login, bug_tag=bug_tag, ignore_tag=ignore_tag,
        cutoff_date=cutoff, ssl_verify=ssl_verify,
    )


def _section_anthropic(ssl_verify: bool = True) -> dict:
    section("2 / 5  —  Claude API  (Anthropic)")

    while True:
        token = ask("API Token  (sk-ant-…)", secret=True)
        print(f"  {dim('Validating token...')} ", end="", flush=True)
        try:
            validate_anthropic(token, ssl_verify)
            print(ok("✓  Token accepted"))
            break
        except ValueError as e:
            msg = str(e)
            print(err(f"✗  {msg}"))
            if "SSL" in msg or "certificate" in msg.lower():
                print(dim("  (Using same SSL setting as YouTrack)"))
            if not ask_bool("  Try a different token?", default=True):
                print(warn("  Skipping validation — fix the token in config.yaml later."))
                break

    model = choose(
        "Model",
        [
            ("claude-sonnet-4-6",          "Sonnet 4.6   — recommended (balanced cost / quality)"),
            ("claude-haiku-4-5-20251001",  "Haiku 4.5    — faster and cheaper"),
            ("claude-opus-4-6",            "Opus 4.6     — best quality, higher cost"),
        ],
        default=1,
    )

    return dict(token=token, model=model)


def _try_clone(url: str, path: str, branch: str) -> bool:
    """Attempt a git clone. Returns True on success, prints error on failure."""
    import subprocess
    print(f"  {dim('Cloning...')} ", end="", flush=True)
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(err(f"✗  Permission denied creating parent directory: {e}"))
        print(dim(f"     Try: sudo mkdir -p {Path(path).parent} && sudo chown $(whoami) {Path(path).parent}"))
        return False

    result = subprocess.run(
        ["git", "clone", "--branch", branch, url, path],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(ok("✓  Cloned"))
        return True

    msg = result.stderr.strip()
    print(err(f"✗  {msg}"))
    if "Permission denied" in msg or "could not create" in msg.lower():
        print(dim(f"     Try: sudo chown -R $(whoami) {Path(path).parent}"))
    return False


def _detect_default_branch(url: str, token: str = "") -> str | None:
    """Try to detect the default branch via git ls-remote."""
    import subprocess
    clone_url = url
    if token and "://" in url and "@" not in url.split("://")[1].split("/")[0]:
        scheme, rest = url.split("://", 1)
        clone_url = f"{scheme}://{token}@{rest}"

    result = subprocess.run(
        ["git", "ls-remote", "--symref", clone_url, "HEAD"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("ref: refs/heads/")[1].split("\t")[0].strip()
    return None


def _is_ssh_url(url: str) -> bool:
    return url.startswith("git@") or url.startswith("ssh://")


def _collect_one_repo(index: int) -> dict:
    """Collect config for a single repository."""
    print()
    print(dim(f"  ── Repo #{index} ──────────────────────────────────────────"))

    name = ask(f"  Short name (used as prefix, e.g. 'backend')")

    print(dim("  URL can be SSH (git@host:org/repo.git) or HTTPS (https://host/org/repo.git)"))
    url = ask(f"  Git URL")

    # token only makes sense for HTTPS
    if _is_ssh_url(url):
        git_token = ""
        print(dim("  SSH URL detected — using system SSH key, no token needed."))
    else:
        git_token = ask(f"  HTTPS token for private repo (leave empty if public)", default="")

    # auto-detect default branch
    print(f"  {dim('Detecting default branch...')} ", end="", flush=True)
    detected = None
    try:
        detected = _detect_default_branch(url, git_token)
    except Exception:
        pass
    if detected:
        print(ok(f"✓  {detected}"))
    else:
        print(warn("✗  Could not detect — enter manually."))

    branch = ask(f"  Branch", default=detected or "main")

    # build the clone URL (inject token only for HTTPS)
    clone_url = url
    if git_token and not _is_ssh_url(url):
        scheme, rest = url.split("://", 1)
        clone_url = f"{scheme}://{git_token}@{rest}"

    repo = None
    while True:
        path = ask(f"  Local path (existing repo dir, or parent dir to clone into)")
        candidate = Path(path).expanduser()

        if candidate.is_dir() and (candidate / ".git").exists():
            print(ok("    ✓  Git repository found"))
            repo = candidate
            break

        # if it looks like a parent dir (exists but no .git), clone into name/ subdir
        clone_target = candidate / name if candidate.is_dir() else candidate

        if candidate.is_dir():
            print(warn(f"    ✗  Not a git repo — will clone into {clone_target}"))
        else:
            print(warn(f"    ✗  Not found — will clone into {clone_target}"))

        if ask_bool("    Clone here now?", default=True):
            if _try_clone(clone_url, str(clone_target), branch):
                repo = clone_target
                break
        else:
            if ask_bool("    Continue anyway (clone manually later)?", default=False):
                repo = clone_target
                break

    claude_md = ask(f"  CLAUDE.md path (relative to repo root)", default="CLAUDE.md")
    if (repo / claude_md).exists():
        print(ok("    ✓  CLAUDE.md found"))
    else:
        print(warn(f"    ⚠  CLAUDE.md not found — create it before starting the daemon."))
        print(dim( "       Template: config/CLAUDE.md.example"))

    return dict(name=name, url=url, path=str(repo),
                branch=branch, claude_md_path=claude_md, git_token=git_token)


def _section_repositories() -> list[dict]:
    section("3 / 5  —  Repositories")
    print(dim("  Add all repositories the bot should have access to."))

    repos = []
    index = 1
    while True:
        repos.append(_collect_one_repo(index))
        index += 1
        print()
        if not ask_bool("  Add another repository?", default=False):
            break

    return repos


def _section_scheduler() -> dict:
    section("4 / 5  —  Schedule & Polling")

    start = ask_int("Active from hour  (0–23)", default=8,  min_val=0, max_val=23)
    end   = ask_int("Active until hour (0–23)", default=21, min_val=1, max_val=24)
    while end <= start:
        print(warn(f"  End hour must be after start hour ({start})."))
        end = ask_int("Active until hour (0–23)", default=21, min_val=1, max_val=24)

    interval = ask_int("Poll interval in minutes", default=15, min_val=1, max_val=1440)

    return dict(start_hour=start, end_hour=end, poll_interval_minutes=interval)


def _section_paths() -> dict:
    section("5 / 5  —  Storage & Logging")

    db_path  = ask("SQLite state DB path", default="~/.octobot/state.db")
    log_file = ask("Log file path",        default="/var/log/octobot/octobot.log")

    return dict(
        db_path=db_path,
        log_file=log_file,
        log_max_bytes=10_485_760,
        log_backup_count=5,
    )


def _default_config_path() -> Path:
    if os.geteuid() == 0:
        return Path("/etc/octobot/config.yaml")
    return Path.home() / ".octobot" / "config.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# Summary & write
# ──────────────────────────────────────────────────────────────────────────────

def _print_summary(cfg: dict, dest: Path):
    yt   = cfg["youtrack"]
    ant  = cfg["anthropic"]
    repos = cfg["repositories"]
    sch  = cfg["scheduler"]
    st   = cfg["state"]

    rule()
    print()
    print(bold("  Configuration summary"))
    print()
    print(f"  YouTrack   {yt['base_url']}  (project: {yt['project']}, bot: {yt['bot_login']})")
    print(f"  Anthropic  {ant['model']}")
    for r in repos:
        print(f"  Repo       [{r['name']}]  {r['path']}  branch: {r['branch']}")
    print(f"  Schedule   {sch['start_hour']:02d}:00 – {sch['end_hour']:02d}:00,  "
          f"every {sch['poll_interval_minutes']} min")
    print(f"  State DB   {st['db_path']}")
    print(f"  Log file   {st['log_file']}")
    print(f"  Config →   {dest}")
    print()
    rule()


def _write_config(cfg: dict, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_write_yaml(cfg), encoding="utf-8")
    dest.chmod(0o600)   # token file — keep private


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print()
    print(bold("  ╔══════════════════════════════════════════╗"))
    print(bold("  ║          Octobot  —  Setup Wizard        ║"))
    print(bold("  ╚══════════════════════════════════════════╝"))
    print()
    print(dim("  This wizard will create your config.yaml."))
    print(dim("  Tokens are stored locally and never transmitted except to YouTrack / Anthropic."))
    print()

    yt = _section_youtrack()
    cfg = {
        "youtrack":     yt,
        "anthropic":    _section_anthropic(ssl_verify=yt.get("ssl_verify", True)),
        "repositories": _section_repositories(),
        "scheduler":    _section_scheduler(),
        "state":        _section_paths(),
    }

    default_dest = _default_config_path()
    dest_raw = ask(
        "\n  Write config to",
        default=str(default_dest),
    )
    dest = Path(dest_raw).expanduser()

    _print_summary(cfg, dest)

    if not ask_bool("  Confirm and write config?", default=True):
        print(warn("  Setup cancelled — nothing written."))
        sys.exit(0)

    try:
        _write_config(cfg, dest)
    except PermissionError:
        print(err(f"  ✗  Permission denied writing to {dest}."))
        print(dim( "     Try running with sudo, or choose a path inside your home directory."))
        sys.exit(1)

    print()
    print(ok(f"  ✓  Config written to {dest}"))
    print()
    print(bold("  Next steps:"))

    if os.geteuid() != 0:
        print("    1.  sudo bash install.sh")
        print(f"   (the installer will read your config from {dest})")
    else:
        print("    1.  bash install.sh   (already running as root)")

    print("    2.  sudo systemctl enable --now octobot")
    print("    3.  sudo journalctl -fu octobot")
    print()
    print(dim("  Manual analysis at any time:"))
    print("    analyze PROJ-123")
    print("    analyze --comment PROJ-123")
    print()
