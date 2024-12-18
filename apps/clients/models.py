import enum
import sqlalchemy as sa
from sqlalchemy.orm import relationship

from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone
from api.utils import generate_uid


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

    uid = sa.Column(
        sa.String(50), index=True, unique=True, default=generate_api_client_uid
    )
    name = sa.Column(sa.Unicode(50))
    description = sa.Column(sa.String(500), nullable=True)
    account_id = sa.Column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    disabled = sa.Column(sa.Boolean, default=False, index=True, insert_default=True)
    account = relationship("Account", back_populates="clients", uselist=False)
    api_key = relationship(
        "APIKey",
        back_populates="client",
        uselist=False,
        cascade="all, delete-orphan",
    )
    client_type = sa.Column(sa.Enum(ClientType, use_native=False), nullable=False)

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

    uid = sa.Column(
        sa.String(50), index=True, unique=True, default=generate_api_key_uid
    )
    secret = sa.Column(
        sa.String(100), nullable=False, index=True, default=generate_api_key_secret
    )
    client_id = sa.Column(
        sa.UUID,
        sa.ForeignKey("clients__api_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client = relationship("APIClient", back_populates="api_key", uselist=False)
    active = sa.Column(sa.Boolean, default=True, index=True, insert_default=True)
    valid_until = sa.Column(sa.DateTime(timezone=True), nullable=True, default=None)

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
