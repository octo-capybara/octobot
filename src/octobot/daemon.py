"""Daemon entry point (importable for the console script)."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import load_config, OctobotConfig
from .scheduler import Scheduler


def _setup_logging(config: OctobotConfig):
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # stdout (also captured by journald when running as a systemd service)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    # rotating file
    log_path = Path(config.state.log_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=config.state.log_max_bytes,
            backupCount=config.state.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except PermissionError:
        logging.warning(
            f"Cannot write to {log_path} — file logging disabled. "
            "Run as root or adjust log_file in config."
        )


def main():
    config = load_config()
    _setup_logging(config)
    logger = logging.getLogger("octobot.daemon")
    logger.info("Octobot starting up.")
    Scheduler(config).run()
