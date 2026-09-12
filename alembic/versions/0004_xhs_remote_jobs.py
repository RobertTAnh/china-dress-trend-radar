"""remote RedNote crawl command queue

Revision ID: 0004_xhs_remote_jobs
Revises: 0003_xhs
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_xhs_remote_jobs"
down_revision: Union[str, None] = "0003_xhs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "xhs_remote_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("state_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_xhs_remote_jobs_job_id", "xhs_remote_jobs", ["job_id"], unique=True)
    op.create_index("ix_xhs_remote_jobs_status", "xhs_remote_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_xhs_remote_jobs_status", table_name="xhs_remote_jobs")
    op.drop_index("ix_xhs_remote_jobs_job_id", table_name="xhs_remote_jobs")
    op.drop_table("xhs_remote_jobs")
