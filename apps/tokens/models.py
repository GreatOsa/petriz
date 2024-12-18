import sqlalchemy as sa
from sqlalchemy.orm import relationship

from helpers.fastapi.models.totp import TimeBasedOTP
from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone
from api.utils import generate_uid


class IdentifierRelatedTOTP(TimeBasedOTP):
    """Identifier related Time Based OTP model"""

    __auto_tablename__ = True

    identifier = sa.Column(sa.String(255), nullable=False, index=True)


class AccountRelatedTOTP(TimeBasedOTP):
    """Account related Time Based OTP model"""

    __auto_tablename__ = True

    account_id = sa.Column(
        sa.ForeignKey("accounts__client_accounts.id"),
        nullable=False,
        index=True,
    )
    owner = relationship("Account", back_populates="totps", uselist=False)


def generate_auth_token_secret() -> str:
    return generate_uid(prefix="petriz_authtoken_", length=24)


class AuthToken(
    mixins.TimestampMixin,
    mixins.UUIDPrimaryKeyMixin,
    models.Model,
):
    """Model representing a account authentication token."""

    __auto_tablename__ = True

    account_id = sa.Column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id"),
        nullable=False,
        index=True,
    )
    owner = relationship("Account", back_populates="auth_token", uselist=False)
    secret = sa.Column(
        sa.String(50), index=True, nullable=False, default=generate_auth_token_secret
    )
    is_active = sa.Column(sa.Boolean, default=True, index=True)
    valid_until = sa.Column(sa.DateTime(timezone=True), nullable=True, default=None)

    __table_args__ = (sa.UniqueConstraint("account_id", "secret"),)

    @property
    def is_valid(self):
        is_active = self.is_active
        if not self.valid_until:
            return is_active
        return is_active and timezone.now() < self.valid_until

