import typing
import enum
import uuid
from annotated_types import MaxLen, LowerCase
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import relationship

from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone
from api.utils import generate_uid
from apps.accounts.models import Account


def generate_api_client_uid() -> str:
    return generate_uid(length=16, prefix="petriz_client_")


class APIClient(
    mixins.UUIDPrimaryKeyMixin,
    mixins.TimestampMixin,
    models.Model,
):
    """Model representing a registered API client"""

    __auto_tablename__ = True

    class ClientType(enum.StrEnum):
        INTERNAL = "internal"
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
    client_type: orm.Mapped[ClientType] = orm.mapped_column(
        sa.Enum(ClientType, use_native=False), nullable=False
    )
    disabled: orm.Mapped[bool] = orm.mapped_column(
        default=False, index=True, insert_default=False
    )

    ######### Relationships #############

    account: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        back_populates="clients"
    )
    api_key: orm.Mapped["APIKey"] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )

    __table_args__ = (sa.UniqueConstraint("account_id", "name"),)
    # Client names should be unique for account


def generate_api_key_uid() -> str:
    return generate_uid(length=24, prefix="petriz_apikey_")


def generate_api_key_secret() -> str:
    return generate_uid(length=24, prefix="petriz_apisecret_")


class APIKey(
    mixins.TimestampMixin,
    mixins.UUIDPrimaryKeyMixin,
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
    active = sa.Column(sa.Boolean, default=True, index=True, insert_default=True)
    valid_until = sa.Column(sa.DateTime(timezone=True), nullable=True, default=None)

    ########## Relationships ############

    client: orm.Mapped[APIClient] = relationship(
        back_populates="api_key", single_parent=True
    )

    __table_args__ = (sa.UniqueConstraint("client_id", "secret"),)

    @property
    def _active(self):
        return self.active and not self.client.disabled

    @property
    def valid(self):
        is_active = self._active
        if not self.valid_until:
            return is_active
        return is_active and timezone.now() < self.valid_until


__all__ = [
    "APIClient",
    "APIKey",
]
