from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime

from .analyzer import Analyzer
from .config import OctobotConfig
from .state import StateDB
from .youtrack import YouTrackClient, YTIssue

logger = logging.getLogger("octobot.scheduler")


class Scheduler:
    def __init__(self, config: OctobotConfig):
        self.config = config
        self.yt = YouTrackClient(config.youtrack.base_url, config.youtrack.token, config.youtrack.ssl_verify)
        self.analyzer = Analyzer(config)
        self.state = StateDB(config.state.db_path)
        self.queue: deque[YTIssue] = deque()

    def run(self):
        logger.info("Octobot scheduler started.")
        while True:
            if self._is_active_hours():
                self._poll_and_process()
                interval = self.config.scheduler.poll_interval_minutes * 60
                logger.info(f"Sleeping {self.config.scheduler.poll_interval_minutes}m until next poll.")
                time.sleep(interval)
            else:
                sleep_secs = self._seconds_until_active()
                wake_at = datetime.now().replace(
                    hour=self.config.scheduler.start_hour, minute=0, second=0
                )
                logger.info(f"Outside active hours. Sleeping until {wake_at.strftime('%H:%M')}.")
                time.sleep(sleep_secs)

    def _is_active_hours(self) -> bool:
        now = datetime.now()
        return self.config.scheduler.start_hour <= now.hour < self.config.scheduler.end_hour

    def _seconds_until_active(self) -> int:
        now = datetime.now()
        start = now.replace(
            hour=self.config.scheduler.start_hour, minute=0, second=0, microsecond=0
        )
        if now >= start:
            # already past today's start, wait until tomorrow
            from datetime import timedelta
            start = start + timedelta(days=1)
        return max(int((start - now).total_seconds()), 60)

    def _poll_and_process(self):
        logger.info("Polling YouTrack for new bug tickets...")
        try:
            issues = self.yt.get_new_bugs(
                project=self.config.youtrack.project,
                bug_tag=self.config.youtrack.bug_tag,
                ignore_tag=self.config.youtrack.ignore_tag,
                cutoff_date=self.config.youtrack.cutoff_date,
            )
        except Exception as e:
            logger.error(f"Failed to poll YouTrack: {e}")
            return

        new_tickets = [i for i in issues if not self._already_handled(i)]
        logger.info(f"Found {len(issues)} bug tickets, {len(new_tickets)} not yet analyzed.")

        for issue in new_tickets:
            self.queue.append(issue)

        self._drain_queue()

    def _drain_queue(self):
        while self.queue:
            if not self._is_active_hours():
                logger.info("Left active hours mid-queue. Stopping.")
                break
            issue = self.queue.popleft()
            self._process_ticket(issue)

    def _already_handled(self, issue: YTIssue) -> bool:
        """Return True if the ticket was already analyzed (SQLite or YouTrack)."""
        if self.state.is_analyzed(issue.readable_id):
            return True
        # Fallback: check YouTrack directly (covers DB loss / reinstall)
        try:
            yt_comment = self.yt.get_bot_comment(issue.id, self.config.youtrack.bot_login)
            if yt_comment:
                self.state.save(issue.readable_id, yt_comment.id)
                return True
        except Exception as e:
            logger.warning(f"Could not check YouTrack comments for {issue.readable_id}: {e}")
        return False

    def _process_ticket(self, issue: YTIssue):
        logger.info(f"Analyzing {issue.readable_id}: {issue.summary}")
        try:
            analysis = self.analyzer.analyze(issue)
            comment_id = self.yt.add_comment(issue.id, analysis)
            self.state.save(issue.readable_id, comment_id)
            logger.info(f"{issue.readable_id} — analysis posted (comment {comment_id}).")
        except Exception as e:
            logger.error(f"{issue.readable_id} — analysis failed: {e}")
            self.state.mark_error(issue.readable_id)
