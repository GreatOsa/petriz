import typing
from annotated_types import MaxLen
import sqlalchemy as sa
from sqlalchemy import orm
import sqlalchemy_utils as sa_utils

from helpers.fastapi.sqlalchemy import mixins
from helpers.fastapi.models.users import AbstractUser
from helpers.generics.utils.validators import min_length_validator, email_validator
from api.utils import generate_uid


def generate_account_uid() -> str:
    """Generates a unique account UID"""
    return generate_uid(prefix="petriz_account_")


class Account(mixins.UUID7PrimaryKeyMixin, AbstractUser):
    """Model representing a user account."""

    __tablename__ = "accounts__client_accounts"

    # Just to override the default username field from AbstractUser
    username = None  # type: ignore

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        index=True,
        unique=True,
        default=generate_account_uid,
        doc="Unique identifier for the account",
    )
    name: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.Unicode(50),
        doc="Account name",
        nullable=False,
        unique=True,
    )
    email: orm.Mapped[str] = orm.mapped_column(
        sa_utils.EmailType,
        index=True,
        unique=True,
        nullable=False,
        doc="Account email",
    )

    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        index=True,
        nullable=False,
        default=False,
        insert_default=False,
        doc="Flag indicating if the account has been deleted",
    )

    ######### Relationships #############

    auth_token = orm.relationship(
        "AuthToken",
        back_populates="owner",
        uselist=False,
        doc="Account authentication token owned by the account",
        cascade="all, delete-orphan",
    )
    totps = orm.relationship(
        "AccountRelatedTOTP",
        back_populates="owner",
        cascade="all, delete-orphan",
        uselist=True,
        doc="Time-based one-time passwords owned by the account",
    )
    clients = orm.relationship(
        "APIClient",
        back_populates="account",
        foreign_keys="APIClient.account_id",
        cascade="all, delete-orphan",
        uselist=True,
        doc="API clients associated with the account",
    )
    search_history = orm.relationship(
        "SearchRecord",
        back_populates="account",
        uselist=True,
        doc="Search history of the account",
    )

    USERNAME_FIELD = "name"
    REQUIRED_FIELDS = {
        "email": [email_validator],
        "name": [min_length_validator(min_length=1)],
    }

    MAX_CLIENT_COUNT = 5


__all__ = ["Account"]
