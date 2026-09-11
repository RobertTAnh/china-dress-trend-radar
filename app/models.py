from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    vietnamese_meaning: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    videos: Mapped[list["VideoKeyword"]] = relationship(back_populates="keyword")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), default="douyin", nullable=False)
    external_video_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cover_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hashtags_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    raw_data_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    snapshots: Mapped[list["Snapshot"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    keywords: Mapped[list["VideoKeyword"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("video_id", "captured_at", name="uq_snapshot_video_captured"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collect_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    video: Mapped[Video] = relationship(back_populates="snapshots")


class VideoKeyword(Base):
    __tablename__ = "video_keywords"

    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    video: Mapped[Video] = relationship(back_populates="keywords")
    keyword: Mapped[Keyword] = relationship(back_populates="videos")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
