from contextlib import asynccontextmanager
import typing
import datetime
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from apps.accounts.models import Account
from .models import (
    Term,
    generate_term_uid,
    SearchRecord,
    generate_search_record_uid,
)


def _clean_topics(topics: typing.Optional[typing.List[str]]) -> typing.List[str]:
    """Clean up a list of topics by stripping and removing empty values."""
    if not topics:
        return []
    return [topic.strip().lower() for topic in topics if topic.strip()]


def _clean_query(query: typing.Optional[str]) -> typing.Optional[str]:
    """Clean up a query string by stripping and returning None if empty."""
    return (query or "").strip() or None


async def create_term(session: AsyncSession, **create_params) -> Term:
    while True:
        uid = generate_term_uid()
        exists = await session.execute(sa.select(sa.exists().where(Term.uid == uid)))
        if not exists.scalar():
            break

    term = Term(uid=uid, **create_params)
    session.add(term)
    return term


async def retrieve_term_by_uid(
    session: AsyncSession, uid: str
) -> typing.Optional[Term]:
    result = await session.execute(sa.select(Term).where(Term.uid == uid))
    return result.scalar()


async def search_terms(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    topics: typing.Optional[typing.List[str]] = None,
    startswith: typing.Optional[typing.List[str]] = None,
    verified: typing.Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> typing.List[Term]:
    query = _clean_query(query)
    topics = _clean_topics(topics)

    if not query and not topics:
        return []

    query_filters = []
    """A list of SQLAlchemy filters to apply to the query"""

    if topics:
        topic_subquery = (
            sa.select(Term.id)
            .select_from(sa.func.unnest(Term.topics).alias("topic"))
            .where(sa.func.lower(sa.text("topic")).in_(topics))
        )
        query_filters.append(Term.id.in_(topic_subquery))

    if query:
        query = rf"%{query}%"
        query_filters.append(
            sa.or_(
                Term.name.icontains(query),
                Term.definition.icontains(query),
            )
        )

    if verified is not None:
        query_filters.append(Term.verified == verified)

    if startswith:
        startletter_filters = []
        for letter in startswith:
            startletter_filters.append(
                sa.or_(
                    Term.name.startswith(letter.lower()),
                    Term.name.startswith(letter.upper()),
                )
            )
        query_filters.append(sa.or_(*startletter_filters))

    result = await session.execute(
        sa.select(Term)
        .where(*query_filters)
        .order_by(
            Term.name.asc(),
            Term.created_at.desc(),
            Term.source_name.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def create_search_record(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    account: typing.Optional[Account] = None,
    topics: typing.Optional[typing.List[str]] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> SearchRecord:
    while True:
        uid = generate_search_record_uid()
        exists = await session.execute(
            sa.select(sa.exists().where(SearchRecord.uid == uid))
        )
        if not exists.scalar():
            break

    query = _clean_query(query)
    topics = _clean_topics(topics)
    search_record = SearchRecord(
        uid=uid,
        account_id=account.id if account else None,
        query=query,
        topics=topics,
        extradata=metadata or {},
    )
    session.add(search_record)
    return search_record


@asynccontextmanager
async def record_search(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    account: typing.Optional[Account] = None,
    topics: typing.Optional[typing.List[str]] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
):
    query = _clean_query(query)
    topics = _clean_topics(topics)

    try:
        yield
        await create_search_record(
            session,
            query=query,
            account=account,
            topics=topics,
            metadata=metadata,
        )
        await session.flush()
    finally:
        pass


async def retrieve_account_search_history(
    session: AsyncSession,
    account: Account,
    *,
    query: typing.Optional[str] = None,
    topics: typing.Optional[typing.List[str]] = None,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
    limit: int = 100,
    offset: int = 0,
):
    query = _clean_query(query)
    topics = _clean_topics(topics)

    query_filters = [
        SearchRecord.account_id == account.id,
    ]
    if query:
        query_filters.append(SearchRecord.query.icontains(rf"%{query}%"))

    if topics:
        topic_subquery = (
            sa.select(SearchRecord.id)
            .select_from(sa.func.unnest(SearchRecord.topics).alias("topic"))
            .where(sa.func.lower(sa.text("topic")).in_(topics))
        )
        query_filters.append(SearchRecord.id.in_(topic_subquery))

    if timestamp_gte:
        query_filters.append(SearchRecord.timestamp >= timestamp_gte)
    if timestamp_lte:
        query_filters.append(SearchRecord.timestamp <= timestamp_lte)

    result = await session.execute(
        sa.select(SearchRecord)
        .where(*query_filters)
        .order_by(SearchRecord.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
