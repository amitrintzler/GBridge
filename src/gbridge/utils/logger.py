"""Rotating file logger for GBridge."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_CONFIGURED = False

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3


def _get_log_dir() -> Path:
    # Import here to avoid circular dependency
    from gbridge.config.settings import get_data_dir

    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a logger with rotating file + console handlers.

    The root gbridge logger is configured once; child loggers inherit.
    """
    global _CONFIGURED  # noqa: PLW0603

    logger = logging.getLogger(name)

    if not _CONFIGURED:
        root = logging.getLogger("gbridge")
        root.setLevel(level)

        # Console handler — INFO and above
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        root.addHandler(console)

        # File handler — rotating, DEBUG and above for diagnostics
        try:
            log_file = _get_log_dir() / "gbridge.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=MAX_LOG_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
            root.addHandler(file_handler)
        except OSError as exc:
            root.warning("Could not create log file handler: %s", exc)

        _CONFIGURED = True

    return logger
