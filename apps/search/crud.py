from contextlib import asynccontextmanager
import select
import typing
import datetime
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from apps.accounts.models import Account
from helpers.fastapi.utils import timezone
from .models import (
    Term,
    generate_term_uid,
    SearchRecord,
    generate_search_record_uid,
)
from .schemas import AccountSearchMetricsSchema, GlobalSearchMetricsSchema


def _clean_topics(topics: typing.Optional[typing.List[str]]) -> typing.List[str]:
    """Clean up a list of topics by stripping and removing empty values."""
    if not topics:
        return []
    return [topic.strip().lower() for topic in topics if topic.strip()]


def _clean_query(query: typing.Optional[str]) -> typing.Optional[str]:
    """Clean up a query string by stripping and returning None if empty."""
    return (query or "").strip() or None


async def create_term(session: AsyncSession, **create_params) -> Term:
    """
    Create a term in the glossary.

    :param session: The database session
    :param create_params: The parameters to create the term with
    :return: The created term
    """
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
    """Retrieve a term by its UID."""
    result = await session.execute(sa.select(Term).where(Term.uid == uid))
    return result.scalar()


###### SEARCH TERMS ######


async def search_terms(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    topics: typing.Optional[typing.List[str]] = None,
    startswith: typing.Optional[typing.List[str]] = None,
    source_name: typing.Optional[str] = None,
    verified: typing.Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    exclude: typing.Optional[typing.List[str]] = None,
    ordering: typing.List[sa.UnaryExpression[Term]] = Term.DEFAULT_ORDERING,
) -> typing.List[Term]:
    """
    Search for terms in the glossary.

    :param session: The database session
    :param query: The search query
    :param topics: Terms that are tagged with the given topics will be returned
    :param startswith: Terms that start with the given letters will be returned
    :param source_name: Terms from the given source will be returned
    :param verified: Only return verified terms if True, unverified terms if False
    :param limit: The maximum number of terms to return
    :param offset: The number of terms to skip
    :param exclude: A list of term UIDs to exclude from the search results
    :param ordering: A list of SQLAlchemy ordering expressions to apply to the query
    """
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
            .where(sa.func.lower(sa.func.trim(sa.text("topic"))).in_(topics))
            .distinct(Term.id)
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
    if source_name:
        query_filters.append(Term.source_name.icontains(source_name))

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

    if exclude:
        query_filters.append(~Term.uid.in_(exclude))

    result = await session.execute(
        sa.select(Term)
        .where(*query_filters)
        .order_by(*ordering)
        .limit(limit)
        .offset(offset)
        .distinct()
    )
    return result.scalars().all()


###### SEARCH RECORDS ######


async def create_search_record(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    account: typing.Optional[Account] = None,
    topics: typing.Optional[typing.List[str]] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> SearchRecord:
    """
    Create a search record in the database.

    :param session: The database session
    :param query: The search query to record
    :param account: The account that made the search
    :param topics: The topics the search was constrained to
    :param metadata: Additional metadata to associate with the search
    :return: The created search record
    """
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
    """
    Async context manager to record a search in the database.

    :param session: The database session
    :param query: The search query to record
    :param account: The account that made the search
    :param topics: The topics the search was constrained to
    :param metadata: Additional metadata to associate with the search
    """
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
) -> typing.Sequence[SearchRecord]:
    """
    Retrieve the search history of an account.

    :param session: The database session
    :param account: The account to retrieve the search history for
    :param query: The search query to filter by
    :param topics: The topics to filter by
    :param timestamp_gte: Only include search records that were created after this timestamp
    :param timestamp_lte: Only include search records that were created before this timestamp
    :param limit: The maximum number of search records to return
    :param offset: The number of search records to skip
    :return: A sequence of search records that match the given filters
    """
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
            .where(sa.func.lower(sa.func.trim(sa.text("topic"))).in_(topics))
            .distinct(SearchRecord.id)
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


###### SEARCH METRICS ######


async def get_term_count(
    session: AsyncSession,
    query_filters: typing.List[sa.BinaryExpression[Term]],
) -> int:
    """
    Return the number of terms that match the given filters.

    :param session: The database session
    :param query_filters: A list of SQLAlchemy filters to apply to filter the terms
    :return: The number of terms that match the given filters
    """
    term_count_query = sa.select(sa.func.count(Term.id)).where(*query_filters)
    term_count = await session.execute(term_count_query)
    return term_count.scalar() or 0


async def get_search_count(
    session: AsyncSession,
    query_filters: typing.List[sa.BinaryExpression[SearchRecord]],
) -> int:
    """
    Return the number of searches that match the given filters.

    :param session: The database session
    :param query_filters: A list of SQLAlchemy filters to apply to filter the search records
    """
    search_count_query = sa.select(
        sa.func.count(SearchRecord.id).label("search_count")
    ).where(*query_filters)
    search_count = await session.execute(search_count_query)
    return search_count.scalar() or 0


async def get_most_searched_queries(
    session: AsyncSession,
    query_filters: typing.List[sa.BinaryExpression[SearchRecord]],
    limit: int = 5,
):
    """
    Returns a mapping of the most searched queries to the number of times they were searched,
    ranking them by the number of searches.

    :param session: The database session
    :param query_filters: A list of SQLAlchemy filters to apply to filter the search records
    :param limit: The maximum number of queries to return
    """
    most_searched_queries_query = (
        sa.select(
            sa.func.lower(sa.func.trim(SearchRecord.query)).label("query_lower"),
            sa.func.count(SearchRecord.id).label("query_count"),
        )
        .where(
            ~SearchRecord.query.is_(sa.null()),
            SearchRecord.query != "",
            *query_filters,
        )
        .order_by(sa.desc(sa.text("query_count")))
        .limit(limit)
        .group_by(sa.text("query_lower"))
    )
    most_searched_queries = await session.execute(most_searched_queries_query)
    return dict(most_searched_queries.all())


async def get_most_searched_topics(
    session: AsyncSession,
    query_filters: typing.List[sa.BinaryExpression[SearchRecord]],
    limit: int = 5,
):
    """
    Returns a mapping of the most searched topics to the number of times a search based on those topics was made,
    ranking them by the number of searches.

    :param session: The database session
    :param query_filters: A list of SQLAlchemy filters to apply to filter the search records
    :param limit: The maximum number of topics to return
    """
    most_searched_topics_query = (
        sa.select(
            sa.func.lower(sa.func.trim(sa.func.unnest(SearchRecord.topics))).label(
                "topic_lower"
            ),
            sa.func.count(SearchRecord.id).label("topic_count"),
        )
        .where(
            ~SearchRecord.topics.is_(sa.null()),
            sa.func.cardinality(SearchRecord.topics) > 0,
            *query_filters,
        )
        .order_by(sa.desc(sa.text("topic_count")))
        .limit(limit)
        .group_by(sa.text("topic_lower"))
    )
    most_searched_topics = await session.execute(most_searched_topics_query)
    return dict(most_searched_topics.all())


async def get_most_searched_words(
    session: AsyncSession,
    query_filters: typing.List[sa.BinaryExpression[SearchRecord]],
    limit: int = 5,
):
    """
    Returns a mapping of the most searched words to the number of times they appeared in search queries,
    ranking them by the number of searches.

    :param session: The database session to use
    :param query_filters: A list of SQLAlchemy filters to apply to filter the search records
    :param limit: The maximum number of words to return
    """
    most_searched_words_query = (
        sa.select(
            sa.func.lower(
                sa.func.trim(
                    sa.func.unnest(sa.func.string_to_array(SearchRecord.query, r"\s+"))
                )
            ).label("word_lower"),
            sa.func.count(SearchRecord.id).label("word_count"),
        )
        .where(
            ~SearchRecord.query.is_(sa.null()),
            SearchRecord.query != "",
            *query_filters,
        )
        .order_by(sa.desc(sa.text("word_count")))
        .limit(limit)
        .group_by(sa.text("word_lower"))
    )
    most_searched_words = await session.execute(most_searched_words_query)
    return dict(most_searched_words.all())


async def get_verified_and_unverified_term_count(
    session: AsyncSession,
    query_filters: typing.Optional[typing.List[sa.BinaryExpression[Term]]] = None,
):
    """
    Returns a tuple of the number of verified and unverified terms in the glossary.

    :param session: The database session to use
    :param query_filters: A list of SQLAlchemy filters to apply to filter the terms
    """
    term_count_query = sa.select(
        sa.func.count(sa.case((sa.func.bool(Term.verified).is_(True), 1))).label(
            "verified_term_count"
        ),
        sa.func.count(sa.case(((sa.func.bool(Term.verified).is_(False), 1)))).label(
            "unverified_term_count"
        ),
    ).where(*query_filters or [])
    term_count = await session.execute(term_count_query)
    return term_count.one()


async def get_terms_sources(
    session: AsyncSession,
    query_filters: typing.Optional[typing.List[sa.BinaryExpression[Term]]] = None,
):
    """
    Returns a mapping of the sources of terms in the glossary to the number of terms from each source.

    :param session: The database session to use
    :param query_filters: A list of SQLAlchemy filters to apply to filter the terms
    """
    sources_query = (
        sa.select(
            sa.func.trim(sa.func.lower(Term.source_name)).label("source_name_lower"),
            sa.func.count(Term.id).label("source_count"),
        )
        .where(
            *query_filters or [],
            Term.source_name != "",
            ~Term.source_name.is_(sa.null()),
        )
        .group_by(sa.text("source_name_lower"))
    )
    sources = await session.execute(sources_query)
    return dict(sources.all())


async def generate_account_search_metrics(
    session: AsyncSession,
    account: Account,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
) -> AccountSearchMetricsSchema:
    """
    Generate search metrics for an account over a period of time.

    :param session: The database session to use
    :param account: The account to generate metrics for
    :param timestamp_gte: Only include search records that were created after this timestamp
    :param timestamp_lte: Only include search records that were created before this timestamp
    :return: An instance of AccountSearchMetricsSchema with the generated metrics
    """
    timestamp_lte = timestamp_lte or timezone.now()
    account_search_metrics = AccountSearchMetricsSchema(
        account_id=account.uid,
        period_start=timestamp_gte,
        period_end=timestamp_lte,
    )
    date_filters = [SearchRecord.timestamp <= timestamp_lte]
    if timestamp_gte:
        date_filters.append(SearchRecord.timestamp >= timestamp_gte)

    query_filters = [SearchRecord.account_id == account.id, *date_filters]

    account_search_metrics.search_count = await get_search_count(session, query_filters)
    account_search_metrics.most_searched_queries = await get_most_searched_queries(
        session, query_filters=query_filters, limit=10
    )
    account_search_metrics.most_searched_topics = await get_most_searched_topics(
        session, query_filters=query_filters, limit=5
    )
    account_search_metrics.most_searched_words = await get_most_searched_words(
        session, query_filters=query_filters, limit=5
    )
    return account_search_metrics


async def generate_global_search_metrics(
    session: AsyncSession,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
) -> GlobalSearchMetricsSchema:
    """
    Generate global search metrics for the glossary over a period of time.

    :param session: The database session to use
    :param timestamp_gte: Only include search records that were created after this timestamp
    :param timestamp_lte: Only include search records that were created before this timestamp
    :return: An instance of GlobalSearchMetricsSchema with the generated metrics
    """
    timestamp_lte = timestamp_lte or timezone.now()
    global_search_metrics = GlobalSearchMetricsSchema(
        period_start=timestamp_gte,
        period_end=timestamp_lte,
    )
    date_filters = [SearchRecord.timestamp <= timestamp_lte]
    if timestamp_gte:
        date_filters.append(SearchRecord.timestamp >= timestamp_gte)

    query_filters = [*date_filters]

    global_search_metrics.search_count = await get_search_count(session, query_filters)
    global_search_metrics.most_searched_queries = await get_most_searched_queries(
        session, query_filters=query_filters, limit=10
    )
    global_search_metrics.most_searched_topics = await get_most_searched_topics(
        session, query_filters=query_filters, limit=5
    )
    global_search_metrics.most_searched_words = await get_most_searched_words(
        session, query_filters=query_filters, limit=5
    )
    global_search_metrics.sources = await get_terms_sources(session)
    (
        verified_term_count,
        unverified_term_count,
    ) = await get_verified_and_unverified_term_count(session)
    global_search_metrics.verified_term_count = verified_term_count
    global_search_metrics.unverified_term_count = unverified_term_count
    return global_search_metrics
