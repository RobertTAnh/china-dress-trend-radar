"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("vietnamese_meaning", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_keywords_keyword", "keywords", ["keyword"], unique=True)

    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="douyin"),
        sa.Column("external_video_id", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("hashtags_json", sa.JSON(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("raw_data_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_videos_external_video_id", "videos", ["external_video_id"], unique=True)

    op.create_table(
        "snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("share_count", sa.Integer(), nullable=True),
        sa.Column("collect_count", sa.Integer(), nullable=True),
    )
    op.create_index("ix_snapshots_video_id", "snapshots", ["video_id"])
    op.create_index("ix_snapshots_captured_at", "snapshots", ["captured_at"])
    op.create_unique_constraint("uq_snapshot_video_captured", "snapshots", ["video_id", "captured_at"])

    op.create_table(
        "video_keywords",
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), primary_key=True),
        sa.Column("keyword_id", sa.Integer(), sa.ForeignKey("keywords.id"), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("crawl_runs")
    op.drop_table("video_keywords")
    op.drop_table("snapshots")
    op.drop_table("videos")
    op.drop_table("keywords")
