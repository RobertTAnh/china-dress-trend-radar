from __future__ import annotations

import logging
import re
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(Authorization['\"=\s:]*Bearer\s+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(TIKHUB_API_KEY['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"=\s:]+)([^\s'\"\\]+)", re.IGNORECASE),
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
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        root.addHandler(handler)
    for handler in root.handlers:
        handler.addFilter(RedactFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
