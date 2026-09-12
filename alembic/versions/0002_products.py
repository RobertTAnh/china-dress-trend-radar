"""product tables for Apify Douyin Shop

Revision ID: 0002_products
Revises: 0001_initial
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_products"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("vietnamese_meaning", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_product_keywords_keyword", "product_keywords", ["keyword"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="douyin"),
        sa.Column("external_product_id", sa.String(length=128), nullable=False),
        sa.Column("promotion_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("product_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("main_image_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("shop_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("shop_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("category_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("platform", "external_product_id", name="uq_product_platform_external"),
    )
    op.create_index("ix_products_external_product_id", "products", ["external_product_id"])

    op.create_table(
        "product_crawl_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keyword_id", sa.Integer(), sa.ForeignKey("product_keywords.id"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("requested_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("normalized_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_product_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("apify_run_id", sa.String(length=128), nullable=True),
        sa.Column("apify_dataset_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_product_crawl_runs_keyword_id", "product_crawl_runs", ["keyword_id"])

    op.create_table(
        "product_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column(
            "crawl_run_id",
            sa.Integer(),
            sa.ForeignKey("product_crawl_runs.id"),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("price_cny", sa.Float(), nullable=True),
        sa.Column("monthly_sold", sa.Integer(), nullable=True),
        sa.Column("lifetime_sold", sa.Integer(), nullable=True),
        sa.Column("good_review_ratio", sa.Float(), nullable=True),
        sa.Column("shop_score", sa.Float(), nullable=True),
        sa.Column("creator_count", sa.Integer(), nullable=True),
        sa.Column("commission_rate", sa.Float(), nullable=True),
        sa.Column("search_position", sa.Integer(), nullable=True),
        sa.Column("sales_growth_absolute", sa.Integer(), nullable=True),
        sa.Column("sales_growth_percent", sa.Float(), nullable=True),
        sa.UniqueConstraint(
            "product_id", "crawl_run_id", name="uq_product_snapshot_product_run"
        ),
    )
    op.create_index("ix_product_snapshots_product_id", "product_snapshots", ["product_id"])
    op.create_index("ix_product_snapshots_crawl_run_id", "product_snapshots", ["crawl_run_id"])
    op.create_index("ix_product_snapshots_captured_at", "product_snapshots", ["captured_at"])

    op.create_table(
        "product_keyword_links",
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), primary_key=True),
        sa.Column(
            "keyword_id", sa.Integer(), sa.ForeignKey("product_keywords.id"), primary_key=True
        ),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("best_search_position", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("product_keyword_links")
    op.drop_index("ix_product_snapshots_captured_at", table_name="product_snapshots")
    op.drop_index("ix_product_snapshots_crawl_run_id", table_name="product_snapshots")
    op.drop_index("ix_product_snapshots_product_id", table_name="product_snapshots")
    op.drop_table("product_snapshots")
    op.drop_index("ix_product_crawl_runs_keyword_id", table_name="product_crawl_runs")
    op.drop_table("product_crawl_runs")
    op.drop_index("ix_products_external_product_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_product_keywords_keyword", table_name="product_keywords")
    op.drop_table("product_keywords")
