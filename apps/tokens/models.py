import datetime
import typing
import uuid
import sqlalchemy as sa
from sqlalchemy import orm
from annotated_types import MaxLen

from helpers.fastapi.models.totp import TimeBasedOTP
from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone
from helpers.fastapi.config import settings
from api.utils import generate_uid
from apps.accounts.models import Account


class IdentifierRelatedTOTP(TimeBasedOTP):
    """Identifier related Time Based OTP model"""

    __auto_tablename__ = True

    identifier: orm.Mapped[typing.Annotated[str, MaxLen(255)]] = orm.mapped_column(
        sa.String(255), nullable=False, index=True
    )


class AccountRelatedTOTP(TimeBasedOTP):
    """Account related Time Based OTP model"""

    __auto_tablename__ = True

    account_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner: orm.Mapped[Account] = orm.relationship(back_populates="totps")


def generate_auth_token_secret() -> str:
    return generate_uid(prefix="petriz_authtoken_")


class AuthToken(
    mixins.TimestampMixin,
    mixins.UUID7PrimaryKeyMixin,
    models.Model,
):
    """Model representing a account authentication token."""

    __auto_tablename__ = True

    account_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner: orm.Mapped[Account] = orm.relationship(
        back_populates="auth_token", single_parent=True
    )
    secret: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        index=True,
        nullable=False,
        default=generate_auth_token_secret,
    )
    is_active: orm.Mapped[bool] = orm.mapped_column(
        default=True, index=True, insert_default=True
    )
    valid_until: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        default=lambda: timezone.now() + settings.AUTH_TOKEN_VALIDITY_PERIOD,
        insert_default=None,
        index=True,
    )

    __table_args__ = (sa.UniqueConstraint("account_id", "secret"),)

    @property
    def is_valid(self):
        is_active = self.is_active
        if not self.valid_until:
            return is_active
        return is_active and timezone.now() < self.valid_until
