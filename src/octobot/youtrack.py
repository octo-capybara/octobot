from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
import urllib3


ISSUE_FIELDS = "id,idReadable,summary,description,created,tags(name),comments(id,text,author(login))"


@dataclass
class YTIssue:
    id: str
    readable_id: str
    summary: str
    description: str
    created: int  # epoch ms
    tags: list[str]


@dataclass
class YTComment:
    id: str
    text: str
    author: str


class YouTrackClient:
    def __init__(self, base_url: str, token: str, ssl_verify: bool = True):
        self.base_url = _normalize_url(base_url)
        self.session = requests.Session()
        self.session.verify = ssl_verify
        if not ssl_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Issue queries
    # ------------------------------------------------------------------

    def get_new_bugs(self, project: str, bug_tag: str, ignore_tag: str, cutoff_date: str) -> list[YTIssue]:
        """Return unignored bug tickets created on or after cutoff_date."""
        query = (
            f"project: {project} "
            f"tag: {{{bug_tag}}} "
            f"-tag: {{{ignore_tag}}} "
            f"created: {cutoff_date} .. Today"
        )
        return self._search(query)

    def get_issue(self, readable_id: str) -> YTIssue:
        """Fetch a single issue by its readable ID (e.g. PROJ-123)."""
        # Search by readable id
        results = self._search(f"#{readable_id}")
        if not results:
            raise ValueError(f"Issue {readable_id} not found")
        return results[0]

    def _search(self, query: str) -> list[YTIssue]:
        resp = self.session.get(
            f"{self.base_url}/api/issues",
            params={"query": query, "fields": ISSUE_FIELDS, "$top": 200},
        )
        resp.raise_for_status()
        return [_parse_issue(raw) for raw in resp.json()]

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def get_bot_comment(self, issue_id: str, bot_login: str) -> YTComment | None:
        """Return the most recent comment written by bot_login, or None."""
        resp = self.session.get(
            f"{self.base_url}/api/issues/{issue_id}/comments",
            params={"fields": "id,text,author(login)"},
        )
        resp.raise_for_status()
        comments = resp.json()
        bot_comments = [c for c in comments if c.get("author", {}).get("login") == bot_login]
        if not bot_comments:
            return None
        last = bot_comments[-1]
        return YTComment(id=last["id"], text=last["text"], author=bot_login)

    def add_comment(self, issue_id: str, text: str) -> str:
        """Post a comment and return its ID."""
        resp = self.session.post(
            f"{self.base_url}/api/issues/{issue_id}/comments",
            json={"text": text},
            params={"fields": "id"},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def delete_comment(self, issue_id: str, comment_id: str) -> None:
        resp = self.session.delete(
            f"{self.base_url}/api/issues/{issue_id}/comments/{comment_id}"
        )
        resp.raise_for_status()

    def update_comment(self, issue_id: str, comment_id: str, text: str) -> None:
        resp = self.session.post(
            f"{self.base_url}/api/issues/{issue_id}/comments/{comment_id}",
            json={"text": text},
            params={"fields": "id"},
        )
        resp.raise_for_status()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalize_url(base_url: str) -> str:
    """Normalize various URL formats to a full https:// URL.

    Examples:
        mycompany                    → https://mycompany.youtrack.cloud
        mycompany.youtrack.cloud     → https://mycompany.youtrack.cloud
        https://mycompany.youtrack.cloud  → https://mycompany.youtrack.cloud
        https://youtrack.mycompany.com    → https://youtrack.mycompany.com
    """
    url = base_url.strip().rstrip("/")
    if "://" not in url:
        # bare hostname or short name
        if "." not in url:
            url = f"{url}.youtrack.cloud"
        url = f"https://{url}"
    return url


def _parse_issue(raw: dict[str, Any]) -> YTIssue:
    return YTIssue(
        id=raw["id"],
        readable_id=raw["idReadable"],
        summary=raw.get("summary", ""),
        description=raw.get("description") or "",
        created=raw.get("created", 0),
        tags=[t["name"] for t in raw.get("tags", [])],
    )
