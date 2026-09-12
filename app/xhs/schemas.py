from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class XhsIngestItem(BaseModel):
    model_config = {"extra": "allow"}

    note_id: str | None = None
    post_id: str | None = None
    id: str | int | None = None
    title: str | None = None
    note_title: str | None = None
    desc: str | None = None
    description: str | None = None
    content: str | None = None


class XhsIngestKeywordBatch(BaseModel):
    keyword: str
    items: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("keyword")
    @classmethod
    def keyword_not_empty(cls, value: str) -> str:
        word = (value or "").strip()
        if not word:
            raise ValueError("keyword trống")
        return word


class XhsIngestPayload(BaseModel):
    client_run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    source_filename: str = ""
    keywords: list[XhsIngestKeywordBatch] = Field(default_factory=list)

    @field_validator("client_run_id")
    @classmethod
    def client_run_id_not_empty(cls, value: str) -> str:
        run_id = (value or "").strip()
        if not run_id:
            raise ValueError("client_run_id trống")
        return run_id
