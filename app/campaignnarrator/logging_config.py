"""Logging configuration for CampaignNarrator."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 3


def configure_logging(*, data_root: Path, console_logging: bool) -> None:
    """Configure the campaignnarrator logger.

    Always writes DEBUG+ to <data_root>/logs/campaignnarrator.log with rotation.
    Adds a WARNING+ StreamHandler to stderr when console_logging is True.
    Safe to call multiple times — clears existing handlers first.
    """
    log_dir = data_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "campaignnarrator.log"

    logger = logging.getLogger("campaignnarrator")
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(file_handler)

    if console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(console_handler)
