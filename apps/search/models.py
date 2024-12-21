import sqlalchemy as sa
from sqlalchemy.orm import relationship
from helpers.fastapi.sqlalchemy import models, mixins
from helpers.fastapi.utils import timezone

from api.utils import generate_uid


def generate_term_uid() -> str:
    return generate_uid(length=24, prefix="petriz_term_")


class Term(mixins.TimestampMixin, models.Model):
    """Model representing a petroleum term"""

    __auto_tablename__ = True

    uid = sa.Column(sa.String(50), unique=True, index=True, default=generate_term_uid)
    name = sa.Column(sa.String(255), index=True, doc="The name of the term")
    definition = sa.Column(sa.String(5000), doc="The definition of the term")
    topics = sa.Column(
        sa.ARRAY(sa.String(50), dimensions=1),
        nullable=True,
        default=list,
        doc="The topics the term belongs to",
    )
    grammatical_label = sa.Column(
        sa.String(50), nullable=True, doc="The part of speech of the term"
    )
    verified = sa.Column(
        sa.Boolean,
        nullable=False,
        default=False,
        doc="Whether the term an its definition have been vetted and verified to be correct",
    )
    source_name = sa.Column(
        sa.String(255),
        nullable=True,
        doc="The name of the source from which the term was obtained",
    )
    source_url = sa.Column(
        sa.String(255),
        nullable=True,
        doc="The URL of the source from which the term was obtained",
    )


def generate_search_record_uid() -> str:
    return generate_uid(length=24, prefix="petriz_search_")


class SearchRecord(mixins.UUIDPrimaryKeyMixin, models.Model):
    __auto_tablename__ = True

    uid = sa.Column(
        sa.String(50),
        unique=True,
        index=True,
        default=generate_search_record_uid,
    )
    query = sa.Column(sa.String(255), index=True, nullable=True)
    topics = sa.Column(
        sa.ARRAY(sa.String(50), dimensions=1),
        nullable=True,
        default=list,
        doc="The topics the term belongs to",
    )  
    account_id = sa.Column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    account = relationship("Account", back_populates="search_history", uselist=False)
    extradata = sa.Column(
        sa.JSON,
        nullable=True,
        insert_default=None,
        doc="Additional metadata about the search",
    )
    timestamp = sa.Column(
        sa.DateTime(timezone=True),
        index=True,
        default=timezone.now,
        doc="The date and time the search was made",
    )


__all__ = ["Term", "SearchRecord"]
