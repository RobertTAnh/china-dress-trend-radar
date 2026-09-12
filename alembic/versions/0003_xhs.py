"""xiaohongshu tables for local MediaCrawler ingest

Revision ID: 0003_xhs
Revises: 0002_products
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_xhs"
down_revision: Union[str, None] = "0002_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "xhs_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("vietnamese_meaning", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_results", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_xhs_keywords_keyword", "xhs_keywords", ["keyword"], unique=True)

    op.create_table(
        "xhs_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_post_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("cover_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("media_type", sa.String(length=32), nullable=False, server_default="note"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("raw_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_xhs_posts_external_post_id", "xhs_posts", ["external_post_id"], unique=True)

    op.create_table(
        "xhs_crawl_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("keyword_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_post_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("client_run_id", sa.String(length=128), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_xhs_crawl_runs_client_run_id", "xhs_crawl_runs", ["client_run_id"], unique=True)

    op.create_table(
        "xhs_post_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("xhs_posts.id"), nullable=False),
        sa.Column(
            "crawl_run_id",
            sa.Integer(),
            sa.ForeignKey("xhs_crawl_runs.id"),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("collect_count", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("share_count", sa.Integer(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("trend_score", sa.Float(), nullable=True),
        sa.Column("trend_label", sa.String(length=64), nullable=False, server_default=""),
        sa.UniqueConstraint("post_id", "crawl_run_id", name="uq_xhs_snapshot_post_run"),
    )
    op.create_index("ix_xhs_post_snapshots_post_id", "xhs_post_snapshots", ["post_id"])
    op.create_index("ix_xhs_post_snapshots_crawl_run_id", "xhs_post_snapshots", ["crawl_run_id"])
    op.create_index("ix_xhs_post_snapshots_captured_at", "xhs_post_snapshots", ["captured_at"])

    op.create_table(
        "xhs_keyword_links",
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("xhs_posts.id"), primary_key=True),
        sa.Column("keyword_id", sa.Integer(), sa.ForeignKey("xhs_keywords.id"), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("best_search_position", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("xhs_keyword_links")
    op.drop_index("ix_xhs_post_snapshots_captured_at", table_name="xhs_post_snapshots")
    op.drop_index("ix_xhs_post_snapshots_crawl_run_id", table_name="xhs_post_snapshots")
    op.drop_index("ix_xhs_post_snapshots_post_id", table_name="xhs_post_snapshots")
    op.drop_table("xhs_post_snapshots")
    op.drop_index("ix_xhs_crawl_runs_client_run_id", table_name="xhs_crawl_runs")
    op.drop_table("xhs_crawl_runs")
    op.drop_index("ix_xhs_posts_external_post_id", table_name="xhs_posts")
    op.drop_table("xhs_posts")
    op.drop_index("ix_xhs_keywords_keyword", table_name="xhs_keywords")
    op.drop_table("xhs_keywords")
