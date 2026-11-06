"""
Desktop Timer - Naplózási és konfigurációs modul.
Rotáló fájlkezelővel és strukturált kivételekkel.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ConfigError(Exception):
    """Konfigurációs vagy elérési út hiba."""
    pass


class StorageLockError(Exception):
    """CSV fájl zárolási hiba (pl. nyitva van Excelben)."""
    pass


def setup_logger(project_name: str = "desktop_timer") -> logging.Logger:
    """
    Error log beállítása rotáló fájlkezelővel.
    A logfájl a projekt saját mappájában jön létre (error.log),
    1 MB méretkorláttal, 3 rotációs mentéssel és delay=True opcióval.
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

