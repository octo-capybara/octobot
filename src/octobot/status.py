from __future__ import annotations

import sys
import click

from .config import load_config
from .state import StateDB


STATUS_ICON = {
    "analyzed": "✓",
    "error":    "✗",
}

STATUS_COLOUR = {
    "analyzed": "\033[32m",  # green
    "error":    "\033[31m",  # red
}
RESET = "\033[0m"
DIM   = "\033[2m"
BOLD  = "\033[1m"


def _colour(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"{code}{text}{RESET}"
    return text


def _fmt_status(status: str) -> str:
    icon = STATUS_ICON.get(status, "?")
    code = STATUS_COLOUR.get(status, "")
    return _colour(f"{icon}  {status}", code)


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    # "2026-03-20T09:15:42.123456" → "2026-03-20 09:15"
    return iso[:16].replace("T", " ")


@click.command("octobot-status")
@click.option("--all", "show_all", is_flag=True, help="Show all tickets, not just the last 10.")
@click.option("--reset", "reset_ticket", default=None, metavar="TICKET_ID",
              help="Remove a ticket from the state so it gets re-processed on next poll.")
def status(show_all: bool, reset_ticket: str | None):
    """Show the current Octobot analysis state.

    Use --reset TICKET_ID to remove a ticket from the state DB,
    making it eligible for re-analysis on the next daemon poll.
    """
    config = load_config()
    db = StateDB(config.state.db_path)

    # ── reset mode ────────────────────────────────────────────────────────────
    if reset_ticket:
        record = db.get_record(reset_ticket)
        if not record:
            click.echo(f"  {reset_ticket} — not found in state DB.")
            sys.exit(1)

        click.echo(f"\n  Ticket:   {reset_ticket}")
        click.echo(f"  Status:   {record['status']}")
        click.echo(f"  Analyzed: {_fmt_date(record['analyzed_at'])}")
        if record["comment_id"]:
            click.echo(f"  Comment:  {record['comment_id']}")
        click.echo()

        if not click.confirm("  Remove from state? (daemon will re-analyze on next poll)", default=False):
            click.echo("  Aborted.")
            sys.exit(0)

        db.delete(reset_ticket)
        click.echo(_colour(f"  ✓  {reset_ticket} removed from state.", "\033[32m"))
        return

    # ── summary ───────────────────────────────────────────────────────────────
    s = db.summary()
    total    = s["total"]    or 0
    analyzed = s["analyzed"] or 0
    errors   = s["errors"]   or 0

    click.echo()
    click.echo(_colour("  Octobot — State", BOLD))
    click.echo()
    click.echo(f"  Analyzed tickets : {_colour(str(analyzed), BOLD)}")
    if errors:
        click.echo(f"  Errors           : {_colour(str(errors), '\033[31m')}")
    if s["last_ticket"]:
        click.echo(f"  Last analysis    : {_fmt_date(s['last_analyzed_at'])}  ({s['last_ticket']})")
    click.echo(f"  DB               : {_colour(config.state.db_path, DIM)}")

    if total == 0:
        click.echo()
        click.echo(_colour("  No tickets analyzed yet.", DIM))
        return

    # ── activity table ────────────────────────────────────────────────────────
    records = db.all_records() if show_all else db.recent(10)

    click.echo()
    click.echo(_colour(f"  {'Ticket':<12}  {'Status':<18}  {'Date':<16}  Comment", DIM))
    click.echo(_colour("  " + "─" * 62, DIM))

    for r in records:
        comment = r["comment_id"] or "—"
        line = (
            f"  {r['ticket_id']:<12}  "
            f"{_fmt_status(r['status']):<18}  "
            f"{_fmt_date(r['analyzed_at']):<16}  "
            f"{_colour(comment, DIM)}"
        )
        click.echo(line)

    if not show_all and total > 10:
        click.echo(_colour(f"\n  … {total - 10} older records hidden. Use --all to show everything.", DIM))

    click.echo()
