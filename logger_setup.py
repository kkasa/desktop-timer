"""
Desktop Timer - Logging and configuration module.
Provides rotating file logging and structured exceptions.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ConfigError(Exception):
    """Configuration or file path error."""
    pass


class StorageLockError(Exception):
    """CSV file lock error (e.g. open in Excel)."""
    pass


def setup_logger(project_name: str = "desktop_timer") -> logging.Logger:
    """
    Configures error logging with a rotating file handler.
    The log file is created in the project root directory (error.log),
    with a 1 MB size limit, 3 backup rotations, and delay=True.
    """
    logger = logging.getLogger(project_name)
    logger.setLevel(logging.WARNING)

    log_dir = Path(__file__).resolve().parent
    log_file = log_dir / "error.log"

    if not logger.handlers:
        fh = RotatingFileHandler(
            log_file,
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        fh.setLevel(logging.WARNING)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
