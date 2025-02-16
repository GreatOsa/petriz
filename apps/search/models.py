import datetime
import typing
import uuid
from annotated_types import MaxLen
import sqlalchemy as sa
from sqlalchemy import orm

from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone

from api.utils import generate_uid
from apps.accounts.models import Account


def generate_term_uid() -> str:
    return generate_uid(prefix="petriz_term_")


def generate_topic_uid() -> str:
    return generate_uid(prefix="petriz_topic_")


def generate_search_record_uid() -> str:
    return generate_uid(prefix="petriz_search_")


class TermToTopicAssociation(models.Model):
    __auto_tablename__ = True

    term_id: orm.Mapped[int] = orm.mapped_column(
        sa.ForeignKey("search__terms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    topic_id: orm.Mapped[int] = orm.mapped_column(
        sa.ForeignKey("search__topics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    __table_args__ = (sa.UniqueConstraint("term_id", "topic_id"),)


class Topic(mixins.TimestampMixin, models.Model):
    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50), unique=True, index=True, default=generate_topic_uid
    )
    name: orm.Mapped[typing.Annotated[str, MaxLen(1000)]] = orm.mapped_column(
        sa.String(1000),
        sa.CheckConstraint("length(name) > 0", name="topic_name_gt_0"),
        index=True,
        doc="The name of the topic",
        nullable=False,
        unique=True,
    )
    description: orm.Mapped[typing.Annotated[str, MaxLen(5000)]] = orm.mapped_column(
        sa.String(5000),
        doc="What aspects does the topic cover?",
        nullable=True,
        insert_default=None,
    )

    terms: orm.Mapped[typing.List["Term"]] = orm.relationship(
        secondary=TermToTopicAssociation.__table__,
        back_populates="topics",
        doc="The terms that belong to the topic",
    )

    DEFAULT_ORDERING = (sa.asc(name),)


class Term(mixins.TimestampMixin, models.Model):
    """Model representing a petroleum term"""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50), unique=True, index=True, default=generate_term_uid
    )
    name: orm.Mapped[typing.Annotated[str, MaxLen(255)]] = orm.mapped_column(
        sa.String(500), index=True, doc="The name of the term"
    )
    definition: orm.Mapped[typing.Annotated[str, MaxLen(5000)]] = orm.mapped_column(
        sa.String(5000), doc="The definition of the term"
    )
    topics: orm.Mapped[typing.Set[Topic]] = orm.relationship(
        secondary=TermToTopicAssociation.__table__,
        back_populates="terms",
        doc="The topics the term belongs to",
    )
    grammatical_label: orm.Mapped[
        typing.Annotated[typing.Optional[str], MaxLen(50)]
    ] = orm.mapped_column(
        sa.String(50),
        nullable=True,
        doc="The part of speech of the term",
    )
    verified: orm.Mapped[bool] = orm.mapped_column(
        nullable=False,
        default=False,
        index=True,
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
    views: orm.Mapped[typing.List["TermView"]] = orm.relationship(
        back_populates="term",
        doc="The views of the term",
    )

    DEFAULT_ORDERING = (
        sa.asc(name),
        sa.asc(verified),
        sa.asc(source_name),
    )


class TermView(models.Model):
    __auto_tablename__ = True

    term_id: orm.Mapped[int] = orm.mapped_column(
        sa.ForeignKey("search__terms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    viewed_by_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    timestamp: orm.Mapped[datetime.datetime] = orm.mapped_column(
        sa.DateTime(timezone=True),
        index=True,
        default=timezone.now,
        doc="The date and time the term was viewed",
    )

    term: orm.Mapped[Term] = orm.relationship(
        doc="The term that was viewed",
        back_populates="views",
    )
    viewed_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        doc="The account that viewed the term",
    )


class SearchRecordToTopicAssociation(models.Model):
    __auto_tablename__ = True

    search_record_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.ForeignKey("search__search_records.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    topic_id: orm.Mapped[int] = orm.mapped_column(
        sa.ForeignKey("search__topics.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


class SearchRecord(mixins.UUID7PrimaryKeyMixin, models.Model):
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
    topics: orm.Mapped[typing.Set[Topic]] = orm.relationship(
        secondary=SearchRecordToTopicAssociation.__table__,
        doc="The topics that were searched for",
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


__all__ = ["Topic", "Term", "SearchRecord"]
