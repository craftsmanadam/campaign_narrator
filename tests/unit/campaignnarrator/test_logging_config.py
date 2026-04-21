"""Unit tests for logging_config."""

from __future__ import annotations

import logging
from pathlib import Path

from campaignnarrator.logging_config import configure_logging


def test_configure_logging_creates_log_file(tmp_path: Path) -> None:
    """Log file must be created under data_root/logs/."""
    configure_logging(data_root=tmp_path, console_logging=False)
    log_path = tmp_path / "logs" / "campaignnarrator.log"
    assert log_path.exists()


def test_configure_logging_writes_to_file(tmp_path: Path) -> None:
    """Messages at WARNING+ must appear in the log file."""
    configure_logging(data_root=tmp_path, console_logging=False)
    logger = logging.getLogger("campaignnarrator")
    logger.warning("test-warning-message")
    log_path = tmp_path / "logs" / "campaignnarrator.log"
    assert "test-warning-message" in log_path.read_text()


def test_configure_logging_debug_written_to_file(tmp_path: Path) -> None:
    """DEBUG messages must appear in the log file."""
    configure_logging(data_root=tmp_path, console_logging=False)
    logger = logging.getLogger("campaignnarrator")
    logger.debug("test-debug-message")
    log_path = tmp_path / "logs" / "campaignnarrator.log"
    assert "test-debug-message" in log_path.read_text()


def test_configure_logging_no_console_handler_when_disabled(tmp_path: Path) -> None:
    """When console_logging=False, no StreamHandler must be attached."""
    configure_logging(data_root=tmp_path, console_logging=False)
    root_logger = logging.getLogger("campaignnarrator")
    stream_handlers = [
        h
        for h in root_logger.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    assert stream_handlers == []


def test_configure_logging_console_handler_when_enabled(tmp_path: Path) -> None:
    """When console_logging=True, a StreamHandler at WARNING must be attached."""
    configure_logging(data_root=tmp_path, console_logging=True)
    root_logger = logging.getLogger("campaignnarrator")
    stream_handlers = [
        h
        for h in root_logger.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    assert len(stream_handlers) >= 1
    assert stream_handlers[0].level == logging.WARNING


def test_configure_logging_console_handler_respects_log_level(tmp_path: Path) -> None:
    """log_level parameter controls the console handler's minimum level."""
    configure_logging(data_root=tmp_path, console_logging=True, log_level="INFO")
    root_logger = logging.getLogger("campaignnarrator")
    stream_handlers = [
        h
        for h in root_logger.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    assert len(stream_handlers) >= 1
    assert stream_handlers[0].level == logging.INFO
