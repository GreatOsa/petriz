import sqlalchemy as sa
import sqlalchemy_utils as sa_utils
from sqlalchemy.orm import relationship

from helpers.fastapi.sqlalchemy import mixins
from helpers.fastapi.models.users import AbstractUser
from helpers.generics.utils.validators import min_length_validator, email_validator
from api.utils import generate_uid


def generate_account_uid() -> str:
    """Generates a unique account UID"""
    return generate_uid(prefix="petriz_account_", length=16)


class Account(mixins.UUIDPrimaryKeyMixin, AbstractUser):
    """Model representing a user account."""

    __tablename__ = "accounts__client_accounts"

    # Just to override the default username field from AbstractUser
    username = None  # type: ignore

    uid = sa.Column(
        sa.String(50),
        index=True,
        unique=True,
        default=generate_account_uid,
        doc="Unique identifier for the account",
    )
    name = sa.Column(sa.Unicode(50), doc="Account name")
    email = sa.Column(
        sa_utils.EmailType, index=True, unique=True, nullable=False, doc="Account email"
    )

    auth_token = relationship(
        "AuthToken",
        back_populates="owner",
        uselist=False,
        doc="Account authentication token",
        cascade="all, delete-orphan",
    )
    totps = relationship(
        "AccountRelatedTOTP",
        back_populates="owner",
        doc="Time-based one-time passwords",
        cascade="all, delete-orphan",
        uselist=True,
    )
    clients = relationship(
        "APIClient",
        back_populates="account",
        cascade="all, delete-orphan",
        uselist=True,
    )
    search_history = relationship(
        "SearchRecord",
        back_populates="account",
        uselist=True,
    )

    USERNAME_FIELD = "name"
    REQUIRED_FIELDS = {
        "email": [email_validator],
        "name": [min_length_validator(min_length=1)],
    }

    MAX_CLIENT_COUNT = 5


__all__ = ["Account"]
