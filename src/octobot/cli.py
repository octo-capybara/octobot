from __future__ import annotations

import sys
import click

from .config import load_config
from .analyzer import Analyzer
from .state import StateDB
from .youtrack import YouTrackClient


@click.command()
@click.argument("ticket_id")
@click.option(
    "--comment", is_flag=True,
    help="After showing the analysis, ask confirmation and post it as a YouTrack comment.",
)
def analyze(ticket_id: str, comment: bool):
    """Analyze a YouTrack bug ticket and print the findings.

    TICKET_ID: YouTrack readable ID, e.g. OR-123

    Without --comment: runs analysis and prints it. Never posts to YouTrack.
    With    --comment: runs analysis, prints it, asks confirmation, then posts.
    """
    config = load_config()
    state = StateDB(config.state.db_path)
    yt = YouTrackClient(config.youtrack.base_url, config.youtrack.token, config.youtrack.ssl_verify)
    analyzer = Analyzer(config)

    # ------------------------------------------------------------------
    # 1. Fetch the issue
    # ------------------------------------------------------------------
    click.echo(f"Fetching {ticket_id}...")
    try:
        issue = yt.get_issue(ticket_id)
    except Exception as e:
        click.echo(f"Error fetching issue: {e}", err=True)
        sys.exit(1)

    click.echo(f"  {issue.readable_id}: {issue.summary}")

    # ------------------------------------------------------------------
    # 2. Check ignore tag
    # ------------------------------------------------------------------
    if config.youtrack.ignore_tag in issue.tags:
        click.echo(f"Note: ticket has tag '{config.youtrack.ignore_tag}'.")

    # ------------------------------------------------------------------
    # 3. Run analysis
    # ------------------------------------------------------------------
    click.echo("\nRunning analysis...")
    try:
        analysis = analyzer.analyze(issue)
    except Exception as e:
        click.echo(f"Analysis failed: {e}", err=True)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. Always show the analysis
    # ------------------------------------------------------------------
    click.echo("\n" + "─" * 60)
    click.echo(analysis)
    click.echo("─" * 60)

    if not comment:
        click.echo("\n(Analysis shown but not posted. Use --comment to post it.)")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 5. --comment: check for existing comment, warn if present
    # ------------------------------------------------------------------
    existing_comment_id = _find_existing_comment(ticket_id, issue.id, state, yt, config.youtrack.bot_login)

    if existing_comment_id:
        record = state.get_record(ticket_id)
        analyzed_at = record["analyzed_at"] if record else "unknown date"
        click.echo(f"\nNote: a previous analysis exists (comment {existing_comment_id}, {analyzed_at}).")
        click.echo("Posting will delete the old comment and replace it.")

    # ------------------------------------------------------------------
    # 6. Ask confirmation before posting
    # ------------------------------------------------------------------
    if not click.confirm("\nPost this analysis as a comment on YouTrack?", default=True):
        click.echo("Not posted.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 7. Delete old comment if replacing
    # ------------------------------------------------------------------
    if existing_comment_id:
        click.echo(f"Deleting previous comment {existing_comment_id}...")
        try:
            yt.delete_comment(issue.id, existing_comment_id)
        except Exception as e:
            click.echo(f"Warning: could not delete old comment: {e}", err=True)

    # ------------------------------------------------------------------
    # 8. Post
    # ------------------------------------------------------------------
    click.echo("Posting...")
    try:
        new_comment_id = yt.add_comment(issue.id, analysis)
        state.save(ticket_id, new_comment_id)
        click.echo(f"Done — comment {new_comment_id} posted on {ticket_id}.")
    except Exception as e:
        click.echo(f"Failed to post comment: {e}", err=True)
        sys.exit(1)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _find_existing_comment(
    ticket_id: str,
    issue_yt_id: str,
    state: StateDB,
    yt: YouTrackClient,
    bot_login: str,
) -> str | None:
    """Return the existing bot comment ID, checking SQLite then YouTrack."""
    record = state.get_record(ticket_id)
    if record and record["status"] == "analyzed" and record["comment_id"]:
        return record["comment_id"]

    try:
        yt_comment = yt.get_bot_comment(issue_yt_id, bot_login)
        if yt_comment:
            state.save(ticket_id, yt_comment.id)
            return yt_comment.id
    except Exception:
        pass

    return None
