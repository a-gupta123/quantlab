"""custom rule-based strategies built by the strategy chatbot

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02 18:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_strategies",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_strategies")),
    )
    op.create_index("ix_custom_strategies_updated_at", "custom_strategies", ["updated_at"])

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fidelity", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("assumptions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_strategy_versions_version")),
        sa.CheckConstraint(
            "fidelity >= 0 AND fidelity <= 100", name=op.f("ck_strategy_versions_fidelity")
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["custom_strategies.id"],
            name=op.f("fk_strategy_versions_strategy_id_custom_strategies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_versions")),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_versions_strategy_version"),
    )

    op.create_table(
        "strategy_messages",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("version_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_strategy_messages_role")),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('built', 'invalid', 'error')",
            name=op.f("ck_strategy_messages_outcome"),
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 1 AND 8000", name=op.f("ck_strategy_messages_len")
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["custom_strategies.id"],
            name=op.f("fk_strategy_messages_strategy_id_custom_strategies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["strategy_versions.id"],
            name=op.f("fk_strategy_messages_version_id_strategy_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_messages")),
    )
    op.create_index("ix_strategy_messages_strategy_id", "strategy_messages", ["strategy_id", "id"])

    # strategy_configs: a config is either an MA crossover (windows) or a rules version.
    op.drop_constraint("ck_strategy_configs_strategy", "strategy_configs", type_="check")
    op.drop_constraint("ck_strategy_configs_windows", "strategy_configs", type_="check")
    op.alter_column("strategy_configs", "short_window", nullable=True)
    op.alter_column("strategy_configs", "long_window", nullable=True)
    op.add_column(
        "strategy_configs", sa.Column("strategy_version_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_strategy_configs_strategy_version_id_strategy_versions",
        "strategy_configs",
        "strategy_versions",
        ["strategy_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_strategy_configs_strategy", "strategy_configs", "strategy IN ('ma_crossover', 'rules')"
    )
    op.create_check_constraint(
        "ck_strategy_configs_kind",
        "strategy_configs",
        "(strategy = 'ma_crossover' AND strategy_version_id IS NULL AND short_window >= 1 "
        "AND short_window < long_window AND long_window <= 400) OR "
        "(strategy = 'rules' AND strategy_version_id IS NOT NULL AND short_window IS NULL "
        "AND long_window IS NULL)",
    )
    op.create_index(
        "uq_strategy_configs_rules",
        "strategy_configs",
        ["strategy_version_id", "fee_bps", "slippage_bps", "allow_fractional"],
        unique=True,
        postgresql_where=sa.text("strategy = 'rules'"),
    )

    op.drop_constraint("ck_trades_side", "trades", type_="check")
    op.alter_column("trades", "side", type_=sa.String(length=8))
    op.create_check_constraint(
        "ck_trades_side", "trades", "side IN ('buy', 'sell', 'short', 'cover')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM trades WHERE side IN ('short', 'cover')")
    op.drop_constraint("ck_trades_side", "trades", type_="check")
    op.alter_column("trades", "side", type_=sa.String(length=4))
    op.create_check_constraint("ck_trades_side", "trades", "side IN ('buy', 'sell')")

    op.drop_index("uq_strategy_configs_rules", table_name="strategy_configs")
    op.drop_constraint("ck_strategy_configs_kind", "strategy_configs", type_="check")
    op.drop_constraint("ck_strategy_configs_strategy", "strategy_configs", type_="check")
    op.drop_constraint(
        "fk_strategy_configs_strategy_version_id_strategy_versions",
        "strategy_configs",
        type_="foreignkey",
    )
    op.drop_column("strategy_configs", "strategy_version_id")
    op.alter_column("strategy_configs", "short_window", nullable=False)
    op.alter_column("strategy_configs", "long_window", nullable=False)
    op.create_check_constraint(
        "ck_strategy_configs_windows",
        "strategy_configs",
        "short_window >= 1 AND short_window < long_window AND long_window <= 400",
    )
    op.create_check_constraint(
        "ck_strategy_configs_strategy", "strategy_configs", "strategy = 'ma_crossover'"
    )

    op.drop_index("ix_strategy_messages_strategy_id", table_name="strategy_messages")
    op.drop_table("strategy_messages")
    op.drop_table("strategy_versions")
    op.drop_index("ix_custom_strategies_updated_at", table_name="custom_strategies")
    op.drop_table("custom_strategies")
