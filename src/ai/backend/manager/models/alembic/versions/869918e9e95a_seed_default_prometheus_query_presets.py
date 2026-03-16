"""seed_default_prometheus_query_presets

Revision ID: 869918e9e95a
Revises: 0e0723286a7a
Create Date: 2026-03-15 00:00:00.000000

"""

import json
import textwrap
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "869918e9e95a"
down_revision = "0e0723286a7a"
branch_labels = None
depends_on = None

FILTER_LABELS = [
    "container_metric_name",
    "kernel_id",
    "session_id",
    "agent_id",
    "user_id",
    "project_id",
    "value_type",
]

GROUP_LABELS = [
    "kernel_id",
    "session_id",
    "agent_id",
    "user_id",
    "project_id",
    "value_type",
]

PRESETS: list[dict[str, Any]] = [
    {
        "name": "container_gauge",
        "metric_name": "backendai_container_utilization",
        "query_template": "sum by ({group_by})(backendai_container_utilization{{{labels}}})",
        "time_window": None,
        "options": json.dumps({"filter_labels": FILTER_LABELS, "group_labels": GROUP_LABELS}),
    },
    {
        "name": "container_rate",
        "metric_name": "backendai_container_utilization",
        "query_template": (
            "sum by ({group_by})(rate(backendai_container_utilization{{{labels}}}[{window}])) / 5.0"
        ),
        "time_window": "5m",
        "options": json.dumps({"filter_labels": FILTER_LABELS, "group_labels": GROUP_LABELS}),
    },
    {
        "name": "container_diff",
        "metric_name": "backendai_container_utilization",
        "query_template": (
            "sum by ({group_by})(rate(backendai_container_utilization{{{labels}}}[{window}]))"
        ),
        "time_window": "5m",
        "options": json.dumps({"filter_labels": FILTER_LABELS, "group_labels": GROUP_LABELS}),
    },
]


def upgrade() -> None:
    # Add unique constraint on name to support ON CONFLICT (name) DO NOTHING
    op.drop_index(
        op.f("ix_prometheus_query_presets_name"),
        table_name="prometheus_query_presets",
        if_exists=True,
    )
    op.create_index(
        op.f("ix_prometheus_query_presets_name"),
        "prometheus_query_presets",
        ["name"],
        unique=True,
    )

    conn = op.get_bind()
    for preset in PRESETS:
        conn.execute(
            sa.text(
                textwrap.dedent("""\
                    INSERT INTO prometheus_query_presets
                        (name, metric_name, query_template, time_window, options)
                    VALUES
                        (:name, :metric_name, :query_template, :time_window, :options::jsonb)
                    ON CONFLICT (name) DO NOTHING
                """)
            ),
            parameters=preset,
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            textwrap.dedent("""\
                DELETE FROM prometheus_query_presets
                WHERE name IN ('container_gauge', 'container_rate', 'container_diff')
            """)
        )
    )

    # Revert unique index back to non-unique
    op.drop_index(
        op.f("ix_prometheus_query_presets_name"),
        table_name="prometheus_query_presets",
        if_exists=True,
    )
    op.create_index(
        op.f("ix_prometheus_query_presets_name"),
        "prometheus_query_presets",
        ["name"],
    )
