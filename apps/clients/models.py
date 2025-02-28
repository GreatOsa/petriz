import datetime
import typing
import enum
import uuid
from annotated_types import MaxLen, LowerCase
import sqlalchemy as sa
from sqlalchemy import orm

from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone
from api.utils import generate_uid
from apps.accounts.models import Account


def generate_api_client_uid() -> str:
    return generate_uid(prefix="petriz_client_")


def generate_api_key_uid() -> str:
    return generate_uid(prefix="petriz_apikey_")


def generate_api_key_secret() -> str:
    return generate_uid(prefix="petriz_apisecret_")


def generate_permission_uid() -> str:
    return generate_uid(prefix="petriz_permission_")


class APIClient(
    mixins.UUID7PrimaryKeyMixin,
    mixins.TimestampMixin,
    models.Model,
):
    """Model representing a registered API client"""

    __auto_tablename__ = True

    class ClientType(enum.StrEnum):
        INTERNAL = "internal"
        PUBLIC = "public"
        PARTNER = "partner"
        USER = "user"

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        index=True,
        unique=True,
        default=generate_api_client_uid,
    )
    name: orm.Mapped[typing.Annotated[str, LowerCase, MaxLen(50)]] = orm.mapped_column(
        sa.Unicode(50)
    )
    description: orm.Mapped[typing.Annotated[str, MaxLen(500)]] = sa.Column(
        sa.String(500), nullable=True
    )
    account_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_type: orm.Mapped[str] = orm.mapped_column(
        sa.String(50), nullable=False, index=True
    )
    disabled: orm.Mapped[bool] = orm.mapped_column(
        default=False, index=True, insert_default=False
    )
    permissions: orm.Mapped[typing.List[str]] = orm.mapped_column(
        sa.ARRAY(sa.String, dimensions=1), nullable=True
    )
    permissions_modified_at: orm.Mapped[typing.Optional[datetime.datetime]] = sa.Column(
        sa.DateTime(timezone=True), nullable=True, index=True
    )
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        default=False, index=True, insert_default=False
    )
    created_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    ######### Relationships #############

    account: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        back_populates="clients", foreign_keys=[account_id]
    )
    api_key: orm.Mapped["APIKey"] = orm.relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )
    created_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        foreign_keys=[created_by_id]
    )


class APIKey(
    mixins.TimestampMixin,
    mixins.UUID7PrimaryKeyMixin,
    models.Model,
):
    """Model representing an client api key."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        index=True,
        unique=True,
        default=generate_api_key_uid,
    )
    secret: orm.Mapped[typing.Annotated[str, MaxLen(100)]] = orm.mapped_column(
        sa.String(100),
        nullable=False,
        index=True,
        default=generate_api_key_secret,
    )
    client_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("clients__api_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    valid_until = sa.Column(sa.DateTime(timezone=True), nullable=True, default=None)

    ########## Relationships ############

    client: orm.Mapped[APIClient] = orm.relationship(
        back_populates="api_key", single_parent=True
    )

    __table_args__ = (sa.UniqueConstraint("client_id", "secret"),)

    @property
    def active(self) -> bool:
        """Check if the api key is active. Depends on the client status"""
        return not self.client.disabled

    @property
    def valid(self) -> bool:
        """Check if the api key is valid. Depends on the client status and the valid_until field"""
        if not self.valid_until:
            return self.active
        return self.active and timezone.now() < self.valid_until


__all__ = [
    "APIClient",
    "APIKey",
]
