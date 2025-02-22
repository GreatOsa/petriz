from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "38b5e43fe9bf"
down_revision: Union[str, None] = "2afb25eee260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the column as nullable first
    op.add_column(
        "accounts__client_accounts",
        sa.Column("is_deleted", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "clients__api_clients", sa.Column("is_deleted", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "search__search_records", sa.Column("is_deleted", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "search__term_sources", sa.Column("is_deleted", sa.Boolean(), nullable=True)
    )
    op.add_column("search__terms", sa.Column("is_deleted", sa.Boolean(), nullable=True))
    op.add_column(
        "search__topics", sa.Column("is_deleted", sa.Boolean(), nullable=True)
    )

    # Set default value for existing rows
    op.execute(
        "UPDATE accounts__client_accounts SET is_deleted = FALSE WHERE is_deleted IS NULL"
    )
    op.execute(
        "UPDATE clients__api_clients SET is_deleted = FALSE WHERE is_deleted IS NULL"
    )
    op.execute(
        "UPDATE search__search_records SET is_deleted = FALSE WHERE is_deleted IS NULL"
    )
    op.execute(
        "UPDATE search__term_sources SET is_deleted = FALSE WHERE is_deleted IS NULL"
    )
    op.execute("UPDATE search__terms SET is_deleted = FALSE WHERE is_deleted IS NULL")
    op.execute("UPDATE search__topics SET is_deleted = FALSE WHERE is_deleted IS NULL")

    # Alter the column to be not nullable
    op.alter_column("accounts__client_accounts", "is_deleted", nullable=False)
    op.alter_column("clients__api_clients", "is_deleted", nullable=False)
    op.alter_column("search__search_records", "is_deleted", nullable=False)
    op.alter_column("search__term_sources", "is_deleted", nullable=False)
    op.alter_column("search__terms", "is_deleted", nullable=False)
    op.alter_column("search__topics", "is_deleted", nullable=False)

    # Create indexes
    op.create_index(
        op.f("ix_accounts__client_accounts_is_deleted"),
        "accounts__client_accounts",
        ["is_deleted"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clients__api_clients_is_deleted"),
        "clients__api_clients",
        ["is_deleted"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search__search_records_is_deleted"),
        "search__search_records",
        ["is_deleted"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search__terms_is_deleted"),
        "search__terms",
        ["is_deleted"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search__topics_is_deleted"),
        "search__topics",
        ["is_deleted"],
        unique=False,
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index(op.f("ix_search__topics_is_deleted"), table_name="search__topics")
    op.drop_index(op.f("ix_search__terms_is_deleted"), table_name="search__terms")
    op.drop_index(
        op.f("ix_search__search_records_is_deleted"),
        table_name="search__search_records",
    )
    op.drop_index(
        op.f("ix_clients__api_clients_is_deleted"), table_name="clients__api_clients"
    )
    op.drop_index(
        op.f("ix_accounts__client_accounts_is_deleted"),
        table_name="accounts__client_accounts",
    )

    # Drop columns
    op.drop_column("search__topics", "is_deleted")
    op.drop_column("search__terms", "is_deleted")
    op.drop_column("search__term_sources", "is_deleted")
    op.drop_column("search__search_records", "is_deleted")
    op.drop_column("clients__api_clients", "is_deleted")
    op.drop_column("accounts__client_accounts", "is_deleted")
