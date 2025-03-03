import typing
import enum
import uuid
from annotated_types import MaxLen
import sqlalchemy as sa
import sqlalchemy_utils as sa_utils
from sqlalchemy import orm, event

from helpers.fastapi.sqlalchemy import models, mixins
from api.utils import generate_uid


def generate_audit_log_uid() -> str:
    return generate_uid(prefix="petriz_audit_logentry_")


class ActionStatus(enum.StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class AuditLogEntry(
    mixins.UUID7PrimaryKeyMixin,
    mixins.TimestampMixin,
    models.Model,
):
    """Model representing an audit log entry."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        index=True,
        unique=True,
        default=generate_audit_log_uid,
    )
    event: orm.Mapped[str] = orm.mapped_column(
        sa.String(255),
        index=True,
        doc="The event or action that occurred. E.g. user_login, user_logout, GET, POST, etc.",
    )
    source: orm.Mapped[str] = orm.mapped_column(
        sa.String(255),
        index=True,
        doc="The source of the event, User Agent + IP Address.",
    )
    actor_id: orm.Mapped[str] = orm.mapped_column(
        sa.String(50),
        index=True,
        nullable=True,
        doc="Unique ID of the actor who performed the action. Can be API client ID, User ID etc.",
    )
    actor_type: orm.Mapped[str] = orm.mapped_column(
        sa.String(50),
        index=True,
        nullable=True,
        doc="The type of the actor who performed the action. Can be API client, user, etc.",
    )
    account_email: orm.Mapped[str] = orm.mapped_column(
        sa_utils.EmailType(255),
        index=True,
        nullable=True,
        doc="Email of the account associated with the action.",
    )
    account_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        nullable=True,
        index=True,
        doc="Unique ID of account associated with the action.",
    )
    target: orm.Mapped[str] = orm.mapped_column(
        sa.String(255),
        index=True,
        nullable=True,
        doc="A name for the target of the action. Can be a resource URL, etc.",
    )
    target_id: orm.Mapped[str] = orm.mapped_column(
        sa.String(50), index=True, nullable=True, doc="Unique ID of the target, if any."
    )
    description: orm.Mapped[str] = orm.mapped_column(
        sa.String(500), nullable=True, doc="A short description of the action."
    )
    status: orm.Mapped[ActionStatus] = orm.mapped_column(
        sa.Enum(ActionStatus, native=False),
        nullable=False,
        index=True,
        doc="Status of the action. Whether the action was successful or not",
    )
    data: orm.Mapped[typing.Any] = orm.mapped_column(sa.JSON, nullable=True)

    __table_args__ = (
        sa.Index("ix_audit_logentry_created_at", "created_at"),
        sa.Index("ix_audit_logentry_updated_at", "updated_at"),
    )


def raise_not_updatable(*args, **kwargs):
    raise ValueError("AuditLogEntry is not updatable.")


event.listen(AuditLogEntry, "before_update", raise_not_updatable)
