import datetime
import typing
import uuid
from annotated_types import Ge, MaxLen
import sqlalchemy as sa
from sqlalchemy import orm

from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone

from api.utils import generate_uid
from apps.accounts.models import Account


def generate_term_uid() -> str:
    return generate_uid(length=24, prefix="petriz_term_")


class Term(mixins.TimestampMixin, models.Model):
    """Model representing a petroleum term"""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50), unique=True, index=True, default=generate_term_uid
    )
    name: orm.Mapped[typing.Annotated[str, MaxLen(255)]] = orm.mapped_column(
        sa.String(255), index=True, doc="The name of the term"
    )
    definition: orm.Mapped[typing.Annotated[str, MaxLen(5000)]] = orm.mapped_column(
        sa.String(5000), doc="The definition of the term"
    )
    topics: orm.Mapped[
        typing.Optional[typing.List[typing.Annotated[str, MaxLen(50)]]]
    ] = orm.mapped_column(
        sa.ARRAY(sa.String(50), dimensions=1),
        nullable=True,
        default=list,
        doc="The topics the term belongs to",
    )
    grammatical_label: orm.Mapped[
        typing.Annotated[typing.Optional[str], MaxLen(50)]
    ] = orm.mapped_column(
        sa.String(50), nullable=True, doc="The part of speech of the term"
    )
    verified: orm.Mapped[bool] = sa.Column(
        nullable=False,
        default=False,
        doc="Whether the term an its definition have been vetted and verified to be correct",
    )
    source_name: orm.Mapped[typing.Annotated[typing.Optional[str], MaxLen(255)]] = (
        orm.mapped_column(
            sa.String(255),
            nullable=True,
            index=True,
            doc="The name of the source from which the term was obtained",
        )
    )
    source_url: orm.Mapped[typing.Annotated[typing.Optional[str], MaxLen(255)]] = (
        orm.mapped_column(
            sa.String(255),
            nullable=True,
            doc="The URL of the source from which the term was obtained",
        )
    )
    views: orm.Mapped[typing.Annotated[int, Ge(0)]] = orm.mapped_column(
        sa.CheckConstraint("views >= 0", name="term_views_ge_0"),
        default=0,
        insert_default=0,
        nullable=True,
        index=True,
        doc="The number of times the term has been viewed",
    )

    DEFAULT_ORDERING = (
        sa.asc(views),
        sa.asc(name),
        sa.asc(verified),
        sa.asc(source_name),
    )


def generate_search_record_uid() -> str:
    return generate_uid(length=24, prefix="petriz_search_")


class SearchRecord(mixins.UUIDPrimaryKeyMixin, models.Model):
    """Model representing a search record by a client or account"""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        unique=True,
        index=True,
        default=generate_search_record_uid,
    )
    query: orm.Mapped[typing.Annotated[str, MaxLen(255)]] = orm.mapped_column(
        sa.String(255), index=True, nullable=True
    )
    topics: orm.Mapped[
        typing.Optional[typing.List[typing.Annotated[str, MaxLen(50)]]]
    ] = orm.mapped_column(
        sa.ARRAY(sa.String(50), dimensions=1),
        nullable=True,
        default=list,
        doc="The topics the term belongs to",
    )
    account_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    extradata: orm.Mapped[typing.Optional[typing.Dict[str, typing.Any]]] = (
        orm.mapped_column(
            sa.JSON,
            nullable=True,
            insert_default=None,
            doc="Additional metadata about the search",
        )
    )
    timestamp: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        index=True,
        default=timezone.now,
        doc="The date and time the search was made",
    )

    ########### Relationships ############

    account: orm.Mapped[Account] = orm.relationship(
        back_populates="search_history", doc="The account that made the search"
    )


__all__ = [
    "GlossaryMetrics",
    "Term",
    "SearchRecord",
]
