from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(Authorization['\"=\s:]*Bearer\s+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(TIKHUB_API_KEY['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(APIFY_TOKEN['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(XHS_INGEST_TOKEN['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(token['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
]


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def _redact_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_secrets(obj)
    if isinstance(obj, dict):
        return {k: _redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        items = [_redact_obj(item) for item in obj]
        return type(obj)(items)
    return obj


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = _redact_obj(record.args)
            else:
                record.args = tuple(_redact_obj(arg) for arg in record.args)
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)

    # Keep a local, persistent diagnostic trail without allowing one log file
    # to grow forever. On Railway this is useful for the current deployment;
    # locally it is written inside the project at logs/crawler.log.
    if not any(getattr(handler, "_crawler_file_handler", False) for handler in root.handlers):
        log_dir = Path(PROJECT_ROOT) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "crawler.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler._crawler_file_handler = True  # type: ignore[attr-defined]
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    for handler in root.handlers:
        handler.addFilter(RedactFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
