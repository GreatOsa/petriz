from contextlib import asynccontextmanager
import typing
import re
import datetime
import sqlalchemy as sa
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from apps.accounts.models import Account
from apps.clients.models import APIClient
from helpers.fastapi.utils import timezone
from helpers.fastapi.sqlalchemy.utils import text_to_tsvector, text_to_tsquery
from .models import (
    Term,
    SearchRecord,
    TermSource,
    Topic,
    TermView,
    SearchRecordToTopicAssociation,
)
from .schemas import AccountSearchMetricsSchema, GlobalSearchMetricsSchema


def _clean_strings(strings: typing.Optional[typing.Iterable[str]]) -> typing.List[str]:
    """Clean up a list of strings by stripping and removing empty values."""
    if not strings:
        return []
    return [s.strip().lower() for s in strings if s.strip()]


async def create_term(session: AsyncSession, **create_params) -> Term:
    """
    Create a term in the glossary.

    :param session: The database session
    :param create_params: The parameters to create the term with
    :return: The created term
    """
    term = Term(**create_params)
    session.add(term)
    return term


async def retrieve_term_by_uid(
    session: AsyncSession, uid: str
) -> typing.Optional[Term]:
    """Retrieve a term by its UID."""
    result = await session.execute(
        sa.select(Term)
        .where(
            Term.uid == uid,
            ~Term.is_deleted,
        )
        .options(
            selectinload(Term.topics.and_(~Topic.is_deleted)),
            selectinload(Term.relatives.and_(~Term.is_deleted)),
            joinedload(Term.source.and_(~TermSource.is_deleted)),
        )
    )
    return result.scalar()


async def retrieve_terms_by_name_or_uid(
    session: AsyncSession, names_or_uids: typing.Iterable[str]
) -> typing.List[Term]:
    """
    Retrieve terms by their names or UIDs.

    Does a case-insensitive search for terms with names that match the given names.
    :param session: The database session
    :param names_or_uids: The names or UIDs of the terms to retrieve
    :return: A list of terms that match the given names or UIDs
    """
    result = await session.execute(
        sa.select(Term).where(
            ~Term.is_deleted,
            sa.or_(
                text_to_tsvector(Term.name).op("@@")(
                    text_to_tsquery(" | ".join(names_or_uids))
                ),
                Term.uid.in_(names_or_uids),
            ),
        )
    )
    return list(result.scalars().all())


async def retrieve_topics_by_name_or_uid(
    session: AsyncSession, names_or_uids: typing.Iterable[str]
) -> typing.List[Topic]:
    """
    Retrieve topics by their names or UIDs.

    Does a case-insensitive search for topics with names that match the given names.
    :param session: The database session
    :param names_or_uids: The names or UIDs of the topics to retrieve
    :return: A list of topics that match the given names or UIDs
    """
    result = await session.execute(
        sa.select(Topic).where(
            ~Topic.is_deleted,
            sa.or_(
                text_to_tsvector(Topic.name).op("@@")(
                    text_to_tsquery(" | ".join(names_or_uids))
                ),
                Topic.uid.in_(names_or_uids),
            ),
        )
    )
    return list(result.scalars().all())


async def create_topic(
    session: AsyncSession, name: str, description: typing.Optional[str] = None
) -> Topic:
    """
    Create a topic in the glossary.

    :param session: The database session
    :param name: The name of the topic
    :param description: A description of the topic
    :return: The created topic
    """
    topic = Topic(name=name, description=description)  # type: ignore
    session.add(topic)
    return topic


async def retrieve_topics(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> typing.List[Topic]:
    """Retrieve all topics in the glossary."""
    result = await session.execute(
        sa.select(Topic).where(~Topic.is_deleted).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def retrieve_topic_by_uid(
    session: AsyncSession, uid: str
) -> typing.Optional[Topic]:
    """Retrieve a topic by its UID."""
    result = await session.execute(
        sa.select(Topic).where(
            Topic.uid == uid,
            ~Topic.is_deleted,
        )
    )
    return result.scalar()


async def retrieve_term_source_by_uid(
    session: AsyncSession, uid: str
) -> typing.Optional[TermSource]:
    """Retrieve a term source by its UID."""
    result = await session.execute(
        sa.select(TermSource).where(
            TermSource.uid == uid,
            ~TermSource.is_deleted,
        )
    )
    return result.scalar()


async def retrieve_term_source_by_name_or_uid(
    session: AsyncSession, name_or_uid: str
) -> typing.Optional[TermSource]:
    """Retrieve a term source by its name or UID."""
    result = await session.execute(
        sa.select(TermSource).where(
            ~TermSource.is_deleted,
            sa.or_(
                sa.func.lower(TermSource.name) == name_or_uid.lower(),
                TermSource.uid == name_or_uid,
            ),
        )
    )
    return result.scalar()


async def create_term_source(session: AsyncSession, **create_params) -> TermSource:
    """
    Create a term source in the glossary.

    :param session: The database session
    :param create_params: The parameters to create the term source with
    :return: The created term source
    """
    term_source = TermSource(**create_params)
    session.add(term_source)
    return term_source


async def get_or_create_term_source(
    session: AsyncSession,
    *,
    uid: typing.Optional[str] = None,
    name: typing.Optional[str] = None,
    **create_params,
) -> typing.Tuple[TermSource, bool]:
    """
    Get or create a term source by name.

    :param session: The database session
    :param uid: The UID of the term source
    :param name: The name of the term source
    :param create_params: Additional parameters to create the term source with
    :return: A tuple containing the term source and a boolean indicating whether it was created
    """
    if not (name or uid):
        raise ValueError("Either name or uid must be provided")

    created = False
    term_source = await retrieve_term_source_by_name_or_uid(session, (uid or name))  # type: ignore
    if term_source:
        return term_source, created

    term_source = await create_term_source(session, name=name, **create_params)
    created = True
    return term_source, created


async def retrieve_term_sources(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> typing.List[TermSource]:
    """Retrieve all term sources in the glossary."""
    result = await session.execute(
        sa.select(TermSource)
        .where(
            ~TermSource.is_deleted,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def retrieve_term_source_terms(
    session: AsyncSession,
    term_source: TermSource,
    topics: typing.Optional[typing.List[Topic]] = None,
    startswith: typing.Optional[typing.List[str]] = None,
    verified: typing.Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    **kwargs,
) -> typing.List[Term]:
    """
    Retrieve terms from a given term source.

    :param session: The database session
    :param term_source: The term source to retrieve terms for
    :param verified: Only return verified terms if True, unverified terms if False
    :param limit: The maximum number of terms to return
    :param offset: The number of terms to skip
    :return: A list of terms from the given term source
    """
    return await search_terms(
        session,
        source=term_source,
        topics=topics,
        startswith=startswith,
        verified=verified,
        limit=limit,
        offset=offset,
        **kwargs,
    )


async def create_term_view(
    session: AsyncSession,
    term: Term,
    viewed_by: typing.Optional[Account],
) -> TermView:
    """
    Create a term view record in the database.

    :param term: The term that was viewed
    :param viewed_by: The user/account that viewed the term
    :param session: The database session
    :return: The created term view record
    """
    term_view = TermView(
        term_id=term.id,  # type: ignore
        viewed_by_id=viewed_by.id if viewed_by else None,  # type: ignore
    )
    session.add(term_view)
    return term_view


async def check_term_exists_for_source(
    session: AsyncSession,
    term_name: str,
    term_source: TermSource,
) -> bool:
    """
    Check if a term with the given name exists for the given source.

    :param session: The database session
    :param term_name: The name of the term to check for
    :param term_source: The source to check for the term in
    :return: True if the term exists, False otherwise
    """
    result = await session.execute(
        sa.select(
            sa.exists().where(
                Term.name.ilike(term_name),
                Term.source_id == term_source.id,
            )
        )
    )
    return result.scalar_one()


async def retrieve_topic_terms(
    session: AsyncSession,
    topic: Topic,
    verified: typing.Optional[bool] = None,
    startswith: typing.Optional[typing.List[str]] = None,
    source: typing.Optional[TermSource] = None,
    limit: int = 100,
    offset: int = 0,
    **kwargs,
) -> typing.List[Term]:
    """
    Retrieve terms that are tagged with the given topic.

    :param session: The database session
    :param topic: The topic to retrieve terms for
    :param verified: Only return verified terms if True, unverified terms if False
    :param startswith: Only return terms that start with the given letters
    :param source: Only return terms from the given source
    :param limit: The maximum number of terms to return
    :param offset: The number of terms to skip
    :return: A list of terms that match the given filters
    """
    kwargs.pop("topics", None)
    return await search_terms(
        session,
        topics=[topic],
        verified=verified,
        startswith=startswith,
        source=source,
        limit=limit,
        offset=offset,
        **kwargs,
    )


def split_text_into_words(text: str) -> typing.List[str]:
    """Split text into words, removing punctuation and whitespace."""
    return re.findall(r"\w+", text)


async def get_related_terms(
    session: AsyncSession,
    term: Term,
    limit: int = 10,
    exclude: typing.Optional[typing.List[typing.Union[int, str]]] = None,
) -> typing.List[Term]:
    """
    Get related terms for a given term.

    Related terms are terms that share topics with the given term or
    have words in common with the definition of the term.
    """
    excluded_ids = set(exclude or [])
    excluded_ids.add(term.id)
    related_terms_query = (
        sa.select(Term)
        .where(
            ~Term.is_deleted,
            Term.verified.is_(True),
            ~Term.id.in_(excluded_ids),
            ~Term.uid.in_(excluded_ids),
            sa.or_(
                text_to_tsvector(term.definition).op("@@")(text_to_tsquery(Term.name))
                if term.search_tsvector
                else text_to_tsvector(term.definition).op("@@")(
                    text_to_tsquery(Term.name)
                ),
                sa.case(
                    (
                        Term.search_tsvector.isnot(None)
                        & Term.search_tsvector.op("@@")(text_to_tsquery(term.name)),
                        True,
                    ),
                    else_=text_to_tsvector(Term.definition).op("@@")(
                        text_to_tsquery(term.name)
                    ),
                ),
            ),
        )
        .limit(limit)
        # .options(
        #     selectinload(Term.topics.and_(~Topic.is_deleted)),
        #     selectinload(Term.relatives.and_(~Term.is_deleted)),
        #     joinedload(Term.source.and_(~TermSource.is_deleted)),
        # )
        .order_by(sa.func.random())
    )
    related_terms = await session.execute(related_terms_query)
    return list(related_terms.scalars().all())


async def update_related_terms(
    session: AsyncSession,
    term: Term,
    limit: int = 10,
) -> Term:
    await session.refresh(term, attribute_names=["topics", "relatives", "source"])
    related_terms = await get_related_terms(
        session,
        term,
        limit=limit,
        exclude=list({related_term.id for related_term in term.relatives}),
    )
    term.relatives |= set(related_terms)
    session.add(term)
    return term


###### SEARCH TERMS ######


async def search_terms(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    topics: typing.Optional[typing.Iterable[Topic]] = None,
    startswith: typing.Optional[typing.List[str]] = None,
    source: typing.Optional[TermSource] = None,
    verified: typing.Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    exclude: typing.Optional[typing.List[typing.Union[str, int]]] = None,
    ordering: typing.Sequence[sa.UnaryExpression] = Term.DEFAULT_ORDERING,
    **filters,
) -> typing.List[Term]:
    """
    Search for terms in the glossary.

    :param session: The database session
    :param query: The search query
    :param topics: Terms that are tagged with the given topics will be returned
    :param startswith: Terms that start with the given letters will be returned
    :param source: Terms from the given source will be returned
    :param verified: Only return verified terms if True, unverified terms if False
    :param limit: The maximum number of terms to return
    :param offset: The number of terms to skip
    :param exclude: A list of term UIDs to exclude from the search results
    :param ordering: A list of SQLAlchemy ordering expressions to apply to the query
    :param filters: Additional filters to apply to the query
    """
    if not (query or topics or filters):
        return []

    query_filters = [~Term.is_deleted]
    if topics:
        query_filters.append(Term.topics.any(Topic.id.in_([t.id for t in topics])))

    if query:
        tsquery = text_to_tsquery(query)
        query_filters.append(
            Term.search_tsvector.op("@@")(tsquery),
        )
        # Update ordering to rank by relevance
        ordering = (
            sa.desc(sa.func.ts_rank_cd(Term.search_tsvector, tsquery)),
            *ordering,
        )

    if source:
        query_filters.append(Term.source_id == source.id)

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
        query_filters.append(sa.and_(~Term.uid.in_(exclude), ~Term.id.in_(exclude)))

    result = await session.execute(
        sa.select(Term)
        .where(*query_filters)
        .filter_by(**filters)
        .limit(limit)
        .offset(offset)
        .options(
            selectinload(Term.topics.and_(~Topic.is_deleted)),
            selectinload(Term.relatives.and_(~Term.is_deleted)),
            joinedload(Term.source.and_(~TermSource.is_deleted)),
        )
        .order_by(*ordering)
    )
    return list(result.scalars().all())


###### SEARCH RECORDS ######


async def create_search_record(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    account: typing.Optional[Account] = None,
    client: typing.Optional[APIClient] = None,
    topics: typing.Optional[typing.Iterable[Topic]] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> SearchRecord:
    """
    Create a search record in the database.

    :param session: The database session
    :param query: The search query to record
    :param account: The account that made the search
    :param client: The API client that was used to make the search
    :param topics: The topics the search was constrained to
    :param metadata: Additional metadata to associate with the search
    :return: The created search record
    """
    search_record = SearchRecord(
        account_id=account.id if account else None,  # type: ignore
        client_id=client.id if client else None,  # type: ignore
        query=query,  # type: ignore
        extradata=metadata or {},  # type: ignore
    )
    if topics:
        search_record.topics |= set(topics)
    session.add(search_record)
    return search_record


@asynccontextmanager
async def record_search(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    account: typing.Optional[Account] = None,
    client: typing.Optional[APIClient] = None,
    topics: typing.Optional[typing.Iterable[Topic]] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
):
    """
    Async context manager to record a search in the database.

    :param session: The database session
    :param query: The search query to record
    :param account: The account that made the search
    :param client: The API client that was used to make the search
    :param topics: The topics the search was constrained to
    :param metadata: Additional metadata to associate with the search
    """
    try:
        yield
        await create_search_record(
            session,
            query=query,
            account=account,
            client=client,
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
    topics: typing.Optional[typing.List[Topic]] = None,
    client: typing.Optional[APIClient] = None,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
    limit: int = 100,
    offset: int = 0,
    ordering: typing.Sequence[sa.UnaryExpression] = SearchRecord.DEFAULT_ORDERING,
) -> typing.List[SearchRecord]:
    """
    Retrieve the search history of an account.

    :param session: The database session
    :param account: The account to retrieve the search history for
    :param query: The search query to filter by
    :param topics: The topics to filter by
    :param client: Only include search records made by the given API client
    :param timestamp_gte: Only include search records that were created after this timestamp
    :param timestamp_lte: Only include search records that were created before this timestamp
    :param limit: The maximum number of search records to return
    :param offset: The number of search records to skip
    :return: A sequence of search records that match the given filters
    """
    query_filters = [
        SearchRecord.account_id == account.id,
    ]
    if query:
        tsquery = text_to_tsquery(query)
        query_filters.append(SearchRecord.query_tsvector.op("@@")(tsquery))
        # Update ordering to rank by relevance
        ordering = (
            sa.desc(sa.func.ts_rank_cd(SearchRecord.query_tsvector, tsquery)),
            *ordering,
        )
    if topics:
        query_filters.append(
            SearchRecord.topics.any(Topic.id.in_([t.id for t in topics]))
        )
    if client:
        query_filters.append(
            SearchRecord.client_id == client.id,
        )

    if timestamp_gte:
        query_filters.append(SearchRecord.timestamp >= timestamp_gte)
    if timestamp_lte:
        query_filters.append(SearchRecord.timestamp <= timestamp_lte)

    result = await session.execute(
        sa.select(SearchRecord)
        .where(
            ~SearchRecord.is_deleted,
            *query_filters,
        )
        .limit(limit)
        .offset(offset)
        .options(
            selectinload(SearchRecord.topics.and_(~Topic.is_deleted)),
            joinedload(SearchRecord.client.and_(~APIClient.is_deleted)),
            joinedload(SearchRecord.account.and_(~Account.is_deleted)),
        )
        .order_by(*ordering)
    )
    return list(result.scalars().all())


async def delete_account_search_history(
    session: AsyncSession,
    account: Account,
    *,
    query: typing.Optional[str] = None,
    topics: typing.Optional[typing.List[Topic]] = None,
    client: typing.Optional[APIClient] = None,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
) -> int:
    """
    Delete the search history of an account.

    :param session: The database session
    :param account: The account to delete the search history for
    :param query: The search query to filter by
    :param topics: The topics to filter by
    :param client: Only delete search records made by the given API client
    :param timestamp_gte: Only delete search records that were created after this timestamp
    :param timestamp_lte: Only delete search records that were created before this timestamp
    :return: The number of search records that were deleted
    """
    query_filters = [
        SearchRecord.account_id == account.id,
    ]
    if query:
        tsquery = text_to_tsquery(query)
        query_filters.append(SearchRecord.query_tsvector.op("@@")(tsquery))

    if topics:
        query_filters.append(
            SearchRecord.topics.any(Topic.id.in_([t.id for t in topics]))
        )
    if client:
        query_filters.append(
            SearchRecord.client_id == client.id,
        )

    if timestamp_gte:
        query_filters.append(SearchRecord.timestamp >= timestamp_gte)
    if timestamp_lte:
        query_filters.append(SearchRecord.timestamp <= timestamp_lte)

    result = await session.execute(
        sa.update(SearchRecord)
        .where(
            ~SearchRecord.is_deleted,
            *query_filters,
        )
        .values(is_deleted=True)
        .returning(SearchRecord.id)
    )
    return len(result.scalars().all())


###### SEARCH METRICS ######


async def get_term_count(
    session: AsyncSession,
    query_filters: typing.List[sa.ColumnExpressionArgument[bool]],
) -> int:
    """
    Return the number of terms that match the given filters.

    :param session: The database session
    :param query_filters: A list of SQLAlchemy filters to apply to filter the terms
    :return: The number of terms that match the given filters
    """
    term_count_query = sa.select(sa.func.count(Term.id)).where(
        ~Term.is_deleted,
        *query_filters,
    )
    term_count = await session.execute(term_count_query)
    return term_count.scalar() or 0


async def get_search_count(
    session: AsyncSession,
    query_filters: typing.List[sa.ColumnExpressionArgument[bool]],
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
    query_filters: typing.List[sa.ColumnExpressionArgument[bool]],
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
    return dict(most_searched_queries.all())  # type: ignore


async def get_most_searched_topics(
    session: AsyncSession,
    query_filters: typing.List[sa.ColumnExpressionArgument[bool]],
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
            Topic.name,
            sa.func.count(SearchRecord.id).label("topic_count"),
        )
        .join(
            SearchRecordToTopicAssociation,
            SearchRecordToTopicAssociation.topic_id == Topic.id,
            isouter=True,
        )
        .join(
            SearchRecord,
            SearchRecordToTopicAssociation.search_record_id == SearchRecord.id,
            isouter=True,
        )
        .where(
            ~Topic.is_deleted,
            *query_filters,
        )
        .group_by(Topic.id)
        .order_by(sa.desc(sa.text("topic_count")))
        .limit(limit)
    )
    most_searched_topics = await session.execute(most_searched_topics_query)
    return dict(most_searched_topics.all())  # type: ignore


async def get_most_searched_words(
    session: AsyncSession,
    query_filters: typing.List[sa.ColumnExpressionArgument[bool]],
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
                    sa.func.unnest(
                        sa.func.regexp_split_to_array(SearchRecord.query, r"\s+")
                    )
                )
            ).label("word_lower"),
            sa.func.count(SearchRecord.id).label("word_count"),
        )
        .where(
            ~SearchRecord.query.is_(sa.null()),
            SearchRecord.query != "",
            *query_filters,
        )
        .limit(limit)
        .order_by(sa.desc(sa.text("word_count")))
        .group_by(sa.text("word_lower"))
    )
    most_searched_words = await session.execute(most_searched_words_query)
    return dict(most_searched_words.all())  # type: ignore


async def get_verified_and_unverified_term_count(
    session: AsyncSession,
    query_filters: typing.Optional[
        typing.List[sa.ColumnExpressionArgument[bool]]
    ] = None,
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
    ).where(
        ~Term.is_deleted,
        *(query_filters or []),
    )
    term_count = await session.execute(term_count_query)
    return term_count.one()


async def get_terms_sources(
    session: AsyncSession,
    query_filters: typing.Optional[
        typing.List[sa.ColumnExpressionArgument[bool]]
    ] = None,
):
    """
    Returns a mapping of the sources of terms in the glossary to the number of terms from each source.

    :param session: The database session to use
    :param query_filters: A list of SQLAlchemy filters to apply to filter the terms
    """
    sources_query = (
        sa.select(
            TermSource.name,
            sa.func.count(Term.id).label("term_count"),
        )
        .join(TermSource, Term.source_id == TermSource.id)
        .where(
            *query_filters or [],
            ~Term.source_id.is_(None),
            ~TermSource.is_deleted,
        )
        .group_by(TermSource.id)
    )
    sources = await session.execute(sources_query)
    return dict(sources.all())  # type: ignore


async def generate_account_search_metrics(
    session: AsyncSession,
    account: Account,
    client: typing.Optional[APIClient] = None,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
) -> AccountSearchMetricsSchema:
    """
    Generate search metrics for an account over a period of time.

    :param session: The database session to use
    :param account: The account to generate metrics for
    :param client: Only consider search records made by the given API client
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
    if client:
        query_filters.append(SearchRecord.client_id == client.id)

    # NOTE: Currently, deleted search records still contribute to the account search metrics.
    # To exclude deleted search records, add `~SearchRecord.is_deleted` to the query_filters
    account_search_metrics.search_count = await get_search_count(session, query_filters)  # type: ignore
    account_search_metrics.most_searched_queries = await get_most_searched_queries(
        session,
        query_filters=query_filters,
        limit=10,  # type: ignore
    )
    account_search_metrics.most_searched_topics = await get_most_searched_topics(
        session,
        query_filters=query_filters,
        limit=5,  # type: ignore
    )
    account_search_metrics.most_searched_words = await get_most_searched_words(
        session,
        query_filters=query_filters,
        limit=5,  # type: ignore
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
    # NOTE: Deleted search records always contribute to the global search metrics.
    global_search_metrics.search_count = await get_search_count(session, query_filters)  # type: ignore
    global_search_metrics.most_searched_queries = await get_most_searched_queries(
        session,
        query_filters=query_filters,
        limit=10,  # type: ignore
    )
    global_search_metrics.most_searched_topics = await get_most_searched_topics(
        session,
        query_filters=query_filters,
        limit=5,  # type: ignore
    )
    global_search_metrics.most_searched_words = await get_most_searched_words(
        session,
        query_filters=query_filters,
        limit=5,  # type: ignore
    )
    global_search_metrics.sources = await get_terms_sources(session)  # type: ignore
    (
        verified_term_count,
        unverified_term_count,
    ) = await get_verified_and_unverified_term_count(session)
    global_search_metrics.verified_term_count = verified_term_count
    global_search_metrics.unverified_term_count = unverified_term_count
    return global_search_metrics
