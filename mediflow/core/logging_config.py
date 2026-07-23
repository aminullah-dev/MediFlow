"""Centralised logging configuration.

Logs rotate daily and are kept for two weeks. Nothing sensitive (passwords,
encryption keys, full patient records) is ever logged — only identifiers and
actions, which is also what the audit trail records at the domain level.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_CONFIGURED = False


def configure_logging(log_dir: Path, *, debug: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "mediflow.log", when="midnight", backupCount=14, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING if not debug else logging.DEBUG)
    root.addHandler(console)

    # SQLAlchemy engine echo is noisy; keep it at WARNING unless debugging.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if debug else logging.WARNING
    )

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mediflow.{name}")
