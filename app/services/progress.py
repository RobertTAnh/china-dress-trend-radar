from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class CrawlProgress:
    running: bool = False
    status: str = "idle"
    run_id: int | None = None
    current_keyword: str | None = None
    request_count: int = 0
    result_count: int = 0
    new_video_count: int = 0
    last_error: str | None = None
    warning: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    mock_mode: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


class ProgressStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._progress = CrawlProgress()

    def get(self) -> CrawlProgress:
        with self._lock:
            return CrawlProgress(**asdict(self._progress))

    def update(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._progress, key, value)

    def reset_for_run(self, run_id: int, mock_mode: bool) -> None:
        with self._lock:
            self._progress = CrawlProgress(
                running=True,
                status="running",
                run_id=run_id,
                mock_mode=mock_mode,
                started_at=datetime.utcnow().isoformat(timespec="seconds"),
            )


progress_store = ProgressStore()
