import datetime
import typing
import uuid
from annotated_types import MaxLen
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import TSVECTOR

from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone

from api.utils import generate_uid
from apps.accounts.models import Account
from apps.clients.models import APIClient


def generate_term_uid() -> str:
    return generate_uid(prefix="petriz_term_")


def generate_topic_uid() -> str:
    return generate_uid(prefix="petriz_topic_")


def generate_term_source_uid() -> str:
    return generate_uid(prefix="petriz_term_source_")


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
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        index=True,
        server_default=sa.false(),
        doc="Whether the topic has been deleted",
    )
    deleted_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="The date and time the topic was deleted",
    )
    
    ############ Relationships ############
    deleted_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        foreign_keys=[deleted_by_id],
        doc="The account that deleted the topic",
    )
    terms: orm.Mapped[typing.List["Term"]] = orm.relationship(
        secondary=TermToTopicAssociation.__table__,  # type: ignore
        back_populates="topics",
        lazy="selectin",
        doc="The terms that belong to the topic",
    )

    DEFAULT_ORDERING = (sa.asc(name),)


class TermSource(mixins.TimestampMixin, models.Model):
    """Model representing a source from which a term was obtained"""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50), unique=True, index=True, default=generate_term_source_uid
    )
    name: orm.Mapped[typing.Annotated[str, MaxLen(255)]] = orm.mapped_column(
        sa.String(255),
        nullable=True,
        index=True,
        doc="The name of the source from which the term was obtained",
    )
    url: orm.Mapped[typing.Annotated[str, MaxLen(500)]] = orm.mapped_column(
        sa.String(255),
        nullable=True,
        doc="The URL of the source from which the term was obtained",
    )
    description: orm.Mapped[typing.Annotated[str, MaxLen(5000)]] = orm.mapped_column(
        sa.String(5000),
        doc="Description of the source",
        nullable=True,
    )
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
        index=True,
        doc="Whether the source has been deleted",
    )
    deleted_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="The date and time the source was deleted",
    )
    
    ############ Relationships ############
    deleted_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        foreign_keys=[deleted_by_id],
        doc="The account that deleted the source",
    )
    terms: orm.Mapped[typing.List["Term"]] = orm.relationship(
        back_populates="source",
        doc="The terms obtained from the source",
        single_parent=True,
        lazy="selectin",
    )

    DEFAULT_ORDERING = (sa.asc(name),)
    __table_args__ = (sa.UniqueConstraint("name", "url"),)


class RelatedTermAssociation(models.Model):
    __auto_tablename__ = True

    term_id: orm.Mapped[int] = orm.mapped_column(
        sa.ForeignKey("search__terms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    related_term_id: orm.Mapped[int] = orm.mapped_column(
        sa.ForeignKey("search__terms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    __table_args__ = (sa.UniqueConstraint("term_id", "related_term_id"),)


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
    search_tsvector = orm.mapped_column(
        TSVECTOR,
        nullable=True,
        doc="The search vector for the term",
    )
    topics: orm.Mapped[typing.Set[Topic]] = orm.relationship(
        secondary=TermToTopicAssociation.__table__,  # type: ignore
        back_populates="terms",
        lazy="selectin",
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
        doc="Whether the term and its definition have been vetted and verified to be correct",
    )
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        index=True,
        server_default=sa.false(),
        doc="Whether the term has been deleted",
    )
    deleted_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="The date and time the term was deleted",
    )
    source_id: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sa.ForeignKey("search__term_sources.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        doc="The source from which the term was obtained",
    )

    ############ Relationships ############
    deleted_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        foreign_keys=[deleted_by_id],
        doc="The account that deleted the term",
    )
    source: orm.Mapped[typing.Optional[TermSource]] = orm.relationship(
        doc="The source from which the term was obtained",
        back_populates="terms",
    )
    views: orm.Mapped[typing.List["TermView"]] = orm.relationship(
        back_populates="term",
        doc="The views of the term",
        lazy="dynamic",
    )
    relatives: orm.Mapped[typing.Set["Term"]] = orm.relationship(
        secondary=RelatedTermAssociation.__table__,  # type: ignore
        primaryjoin=lambda: RelatedTermAssociation.term_id == Term.id,
        secondaryjoin=lambda: RelatedTermAssociation.related_term_id == Term.id,
        back_populates="relatives",
        lazy="selectin",
        doc="The terms related to this term",
    )

    DEFAULT_ORDERING = (
        sa.asc(name),
        sa.asc(verified),
    )

    __table_args__ = (
        sa.Index("ix_terms_search_tsvector", search_tsvector, postgresql_using="gin"),
        sa.UniqueConstraint(
            "name", "source_id"
        ),  # Term names should be unique within a source
    )


class TermView(models.Model):
    """Model representing a view of a term by a client or account"""

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


class SearchRecord(mixins.UUID7PrimaryKeyMixin, models.Model):  # type: ignore
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
    query_tsvector = orm.mapped_column(
        TSVECTOR,
        nullable=True,
        doc="The search vector for the query",
    )
    topics: orm.Mapped[typing.Set[Topic]] = orm.relationship(
        secondary=SearchRecordToTopicAssociation.__table__,  # type: ignore
        doc="The topics that were searched for",
    )
    account_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    client_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("clients__api_clients.id", ondelete="SET NULL"),
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
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        nullable=False,
        default=False,
        index=True,
        server_default=sa.false(),
        doc="Whether the search record has been deleted",
    )
    deleted_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="The date and time the search record was deleted",
    )
    
    ############ Relationships ############
    deleted_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        foreign_keys=[deleted_by_id],
        doc="The account that deleted the search record",
    )
    account: orm.Mapped[Account] = orm.relationship(
        foreign_keys=[account_id],
        back_populates="search_history", doc="The account that made the search"
    )
    client: orm.Mapped[APIClient] = orm.relationship(
        doc="The client that made the search",
    )

    DEFAULT_ORDERING = (sa.desc(timestamp),)
    __table_args__ = (
        sa.Index(
            "ix_search_records_query_tsvector", query_tsvector, postgresql_using="gin"
        ),
    )

