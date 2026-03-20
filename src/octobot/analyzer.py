from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import anthropic

from .config import OctobotConfig, RepositoryConfig
from .youtrack import YTIssue

logger = logging.getLogger("octobot.analyzer")

ANALYSIS_SYSTEM_PROMPT = """You are Octobot, an automated bug analysis assistant.
You have been given a bug ticket and access to one or more project repositories.

IMPORTANT: Detect the language used in the ticket (summary and description) and write your entire response in that same language.

Your task is to:
1. Understand the bug described in the ticket
2. Identify the most likely root cause in the code
3. Propose a concrete, actionable fix

File paths are prefixed with the repository name, e.g. "backend:src/foo.py".

Be concise and technical. Use the following structure, translating the section headers into the detected language:

## [Root Cause]
[Brief explanation of what is causing the bug]

## [Affected Code]
[File paths (with repo prefix) and relevant code sections]

## [Proposed Fix]
[Concrete steps or code changes to fix the bug]

---
*[Automated Octobot analysis — verify before applying]*"""


class Analyzer:
    def __init__(self, config: OctobotConfig):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic.token)

    def analyze(self, issue: YTIssue) -> str:
        """Run full analysis on a ticket and return the comment text."""
        available_repos = self._sync_all_repos()

        if not available_repos:
            raise RuntimeError("No repositories available for analysis.")

        claude_md   = self._read_all_claude_mds(available_repos)
        file_list   = self._get_combined_file_list(available_repos)
        relevant    = self._identify_relevant_files(issue, claude_md, file_list)
        file_contents = self._read_files(relevant, available_repos)
        return self._generate_analysis(issue, claude_md, file_contents)

    # ------------------------------------------------------------------
    # Repository sync
    # ------------------------------------------------------------------

    def _sync_all_repos(self) -> list[RepositoryConfig]:
        """Pull (or clone) every repo. Returns repos that are ready."""
        available = []
        for repo in self.config.repositories:
            try:
                self._sync_repo(repo)
                available.append(repo)
            except RuntimeError as e:
                logger.error(f"[{repo.name}] Skipping — {e}")
        return available

    def _sync_repo(self, repo: RepositoryConfig):
        path = Path(repo.path)
        if not path.exists() or not (path / ".git").exists():
            if path.exists() and not (path / ".git").exists():
                logger.warning(f"[{repo.name}] Directory exists but is not a git repo — attempting clone into it.")
            _git_clone(repo)
        else:
            _git_pull(repo)

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def _read_all_claude_mds(self, repos: list[RepositoryConfig]) -> str:
        sections = []
        for repo in repos:
            md_path = Path(repo.path) / repo.claude_md_path
            if md_path.exists():
                content = md_path.read_text(encoding="utf-8")
                sections.append(f"## Repository: {repo.name}\n\n{content}")
            else:
                sections.append(f"## Repository: {repo.name}\n\n(No CLAUDE.md found)")
        return "\n\n---\n\n".join(sections)

    def _get_combined_file_list(self, repos: list[RepositoryConfig]) -> str:
        lines = []
        for repo in repos:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=repo.path,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning(f"[{repo.name}] git ls-files failed: {result.stderr.strip()}")
                continue
            for f in result.stdout.splitlines():
                lines.append(f"{repo.name}:{f}")
        return "\n".join(lines)

    def _identify_relevant_files(self, issue: YTIssue, claude_md: str, file_list: str) -> list[str]:
        prompt = f"""You have the following project context (one or more repositories):

<claude_md>
{claude_md}
</claude_md>

<file_list>
{file_list}
</file_list>

<bug_ticket>
ID: {issue.readable_id}
Summary: {issue.summary}
Description: {issue.description}
</bug_ticket>

Based on the context and the bug, list the files most likely relevant to this bug.
Return ONLY a newline-separated list of paths in "repo_name:relative/path" format, nothing else.
Maximum 10 files."""

        response = self.client.messages.create(
            model=self.config.anthropic.model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _read_files(self, prefixed_paths: list[str], repos: list[RepositoryConfig]) -> str:
        repo_map = {r.name: r for r in repos}
        chunks = []
        for entry in prefixed_paths:
            if ":" not in entry:
                continue
            repo_name, rel_path = entry.split(":", 1)
            repo = repo_map.get(repo_name)
            if not repo:
                continue
            full_path = Path(repo.path) / rel_path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                chunks.append(f"### {repo_name}:{rel_path}\n```\n{content}\n```")
            except Exception as e:
                logger.warning(f"Could not read {entry}: {e}")
        return "\n\n".join(chunks)

    def _generate_analysis(self, issue: YTIssue, claude_md: str, file_contents: str) -> str:
        prompt = f"""<claude_md>
{claude_md}
</claude_md>

<bug_ticket>
ID: {issue.readable_id}
Summary: {issue.summary}
Description: {issue.description}
</bug_ticket>

<relevant_code>
{file_contents}
</relevant_code>

Analyze this bug and provide your assessment."""

        response = self.client.messages.create(
            model=self.config.anthropic.model,
            max_tokens=2048,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


# ------------------------------------------------------------------
# Git helpers (module-level, reused by wizard too)
# ------------------------------------------------------------------

def _git_clone(repo: RepositoryConfig):
    if not repo.url:
        raise RuntimeError(
            f"Path '{repo.path}' does not exist and no 'url' is configured."
        )
    path = Path(repo.path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise RuntimeError(
            f"Permission denied creating '{path.parent}'. "
            f"Ensure the bot user has write access to that directory."
        )

    clone_url = _inject_token(repo.url, repo.git_token)
    result = subprocess.run(
        ["git", "clone", "--branch", repo.branch, clone_url, str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = result.stderr.strip()
        if "Permission denied" in msg or "could not create" in msg.lower():
            raise RuntimeError(
                f"Git clone failed with a permission error.\n"
                f"  Target : {path}\n"
                f"  Fix    : sudo chown -R $(whoami) {path.parent}\n"
                f"  Detail : {msg}"
            )
        # branch not found — try cloning without --branch (uses remote default)
        if "not found" in msg.lower() or "not found in upstream" in msg.lower():
            logger.warning(f"[{repo.name}] Branch '{repo.branch}' not found, retrying with remote default.")
            result2 = subprocess.run(
                ["git", "clone", clone_url, str(path)],
                capture_output=True, text=True,
            )
            if result2.returncode == 0:
                return
            msg = result2.stderr.strip()
        raise RuntimeError(f"git clone failed: {msg}")


def _inject_token(url: str, token: str) -> str:
    """Inject a token into an HTTPS git URL: https://token@host/..."""
    if not token or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    # avoid double-injecting if credentials already present
    if "@" in rest.split("/")[0]:
        return url
    return f"{scheme}://{token}@{rest}"


def _git_pull(repo: RepositoryConfig):
    result = subprocess.run(
        ["git", "pull", "origin", repo.branch],
        cwd=repo.path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git pull failed: {result.stderr.strip()}")
