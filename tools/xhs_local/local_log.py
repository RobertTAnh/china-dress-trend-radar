from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / "logs" / "xhs_local_crawl.log"


def get_logger() -> logging.Logger:
    logger = logging.getLogger("xhs_local")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.addHandler(stream)

    try:
        import sys

        sys.path.insert(0, str(PROJECT_ROOT))
        from app.logging_utils import RedactFilter

        handler.addFilter(RedactFilter())
        stream.addFilter(RedactFilter())
    except Exception:
        pass
    return logger
