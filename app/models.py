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


class ProductKeyword(Base):
    __tablename__ = "product_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    vietnamese_meaning: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    products: Mapped[list["ProductKeywordLink"]] = relationship(back_populates="keyword")
    crawl_runs: Mapped[list["ProductCrawlRun"]] = relationship(back_populates="keyword")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("platform", "external_product_id", name="uq_product_platform_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), default="douyin", nullable=False)
    external_product_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    promotion_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    product_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    main_image_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    shop_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    shop_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    category_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    raw_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    snapshots: Mapped[list["ProductSnapshot"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    keywords: Mapped[list["ProductKeywordLink"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductCrawlRun(Base):
    __tablename__ = "product_crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_keywords.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requested_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normalized_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_product_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    apify_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    apify_dataset_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    keyword: Mapped[ProductKeyword | None] = relationship(back_populates="crawl_runs")
    snapshots: Mapped[list["ProductSnapshot"]] = relationship(back_populates="crawl_run")


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "crawl_run_id", name="uq_product_snapshot_product_run"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    crawl_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_crawl_runs.id"), nullable=True, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    price_cny: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lifetime_sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    good_review_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    shop_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    creator_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    search_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_growth_absolute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_growth_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    product: Mapped[Product] = relationship(back_populates="snapshots")
    crawl_run: Mapped[ProductCrawlRun | None] = relationship(back_populates="snapshots")


class ProductKeywordLink(Base):
    __tablename__ = "product_keyword_links"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("product_keywords.id"), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    best_search_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product: Mapped[Product] = relationship(back_populates="keywords")
    keyword: Mapped[ProductKeyword] = relationship(back_populates="products")


class XhsKeyword(Base):
    __tablename__ = "xhs_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    vietnamese_meaning: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    posts: Mapped[list["XhsKeywordLink"]] = relationship(back_populates="keyword")


class XhsPost(Base):
    __tablename__ = "xhs_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_post_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), default="note", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    raw_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    snapshots: Mapped[list["XhsPostSnapshot"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    keywords: Mapped[list["XhsKeywordLink"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class XhsCrawlRun(Base):
    __tablename__ = "xhs_crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    keyword_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_post_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    client_run_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshots: Mapped[list["XhsPostSnapshot"]] = relationship(back_populates="crawl_run")


class XhsPostSnapshot(Base):
    __tablename__ = "xhs_post_snapshots"
    __table_args__ = (
        UniqueConstraint("post_id", "crawl_run_id", name="uq_xhs_snapshot_post_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("xhs_posts.id"), nullable=False, index=True)
    crawl_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("xhs_crawl_runs.id"), nullable=True, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collect_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_label: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    post: Mapped[XhsPost] = relationship(back_populates="snapshots")
    crawl_run: Mapped[XhsCrawlRun | None] = relationship(back_populates="snapshots")


class XhsKeywordLink(Base):
    __tablename__ = "xhs_keyword_links"

    post_id: Mapped[int] = mapped_column(ForeignKey("xhs_posts.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("xhs_keywords.id"), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    best_search_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    post: Mapped[XhsPost] = relationship(back_populates="keywords")
    keyword: Mapped[XhsKeyword] = relationship(back_populates="posts")
