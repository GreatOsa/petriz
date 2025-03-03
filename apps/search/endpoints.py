from annotated_types import MaxLen, Le
import fastapi
import typing
from typing_extensions import Doc

from helpers.fastapi.dependencies.connections import DBSession, User
from helpers.fastapi.response import shortcuts as response
from helpers.fastapi.response.pagination import paginated_data
from helpers.fastapi.dependencies.access_control import staff_user_only, ActiveUser
from helpers.fastapi.requests.query import Limit, Offset
from helpers.fastapi.exceptions import capture
from api.dependencies.authentication import (
    authentication_required,
    authenticate_connection,
)
from api.dependencies.authorization import (
    internal_api_clients_only,
    permissions_required,
)
from api.dependencies.auditing import event
from .query import (
    Startswith,
    Verified,
    Topics,
    SearchQuery,
    TimestampGte,
    TimestampLte,
    Source,
)
from . import schemas, crud


router = fastapi.APIRouter()

TopicUID = typing.Annotated[str, fastapi.Path(description="Topic UID")]
TermUID = typing.Annotated[str, fastapi.Path(description="Term UID")]
TermSourceUID = typing.Annotated[str, fastapi.Path(description="Term Source UID")]


@router.get(
    "",
    dependencies=[
        event(
            "search",
            target="terms",
            description="Search terms in the glossary",
        ),
        permissions_required(
            "terms::*::list",
            "search_records::*::create",
        ),
        authenticate_connection,
    ],
    description="Search terms in the glossary.",
)
async def search_terms(
    request: fastapi.Request,
    session: DBSession,
    user: User,
    # Query parameters
    query: typing.Annotated[SearchQuery, MaxLen(100)] = None,
    topics: typing.Annotated[
        Topics,
        MaxLen(10),
        Doc("What topics should the search be constrained to?"),
    ] = None,
    startswith: Startswith = None,
    verified: Verified = True,
    source: Source = None,
    limit: typing.Annotated[Limit, Le(100)] = 20,
    offset: Offset = 0,
):
    account = user if user.is_authenticated else None
    client = getattr(request.state, "client", None)
    if topics:
        topics = await crud.retrieve_topics_by_name_or_uid(session, topics)
    if source:
        source = await crud.retrieve_term_source_by_name_or_uid(session, source)
        if not source:
            return response.bad_request("Invalid source provided")

    async with crud.record_search(
        session,
        query=query,
        topics=topics,
        account=account,
        client=client,
        metadata={
            "verified": verified,
            "startswith": startswith,
            "source": schemas.TermSourceSchema.model_validate(source).model_dump(
                mode="json"
            )
            if source
            else None,
            "limit": limit,
            "offset": offset,
        },
    ):
        result = await crud.search_terms(
            session,
            query=query,
            topics=topics,
            startswith=startswith,
            source=source,
            verified=verified,
            limit=limit,
            offset=offset,
        )
        response_data = [schemas.TermSchema.model_validate(term) for term in result]

    await session.commit()
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.post(
    "/terms",
    dependencies=[
        event(
            "term_create",
            target="terms",
            description="Create a new term in the glossary",
        ),
        internal_api_clients_only,
        permissions_required("terms::*::create"),
        authentication_required,
    ],
    description="Add a new term to the glossary",
)
async def create_term(
    user: ActiveUser,
    data: schemas.TermCreateSchema,
    session: DBSession,
):
    dumped_data = data.model_dump(mode="json")
    topics_data: typing.Optional[typing.List[str]] = dumped_data.pop("topics", None)
    source_data: typing.Optional[typing.Dict[str, typing.Any]] = dumped_data.pop(
        "source", None
    )
    if topics_data:
        topics = await crud.retrieve_topics_by_name_or_uid(session, topics_data)
        if not topics:
            return response.bad_request("Invalid topics provided")

    if source_data:
        with capture.capture(ValueError, code=400):
            source, created = await crud.get_or_create_term_source(
                session, **source_data
            )
            term_name = dumped_data["name"]
            if not created and await crud.check_term_exists_for_source(
                session,
                term_name=term_name,
                term_source=source,
            ):
                return response.bad_request(
                    f"A term with the name {term_name!r} already exists for the source {source.name!r}"
                )
            dumped_data["source"] = source

    term = await crud.create_term(
        session,
        **dumped_data,
        verified=user.is_staff,
        topics=set(topics or []),
    )

    await session.commit()
    await session.refresh(
        term,
        attribute_names=[
            "topics",
            "source",
            "relatives",
        ],
    )
    return response.created(
        f"{term.name} has been added to the glossary!",
        data=schemas.TermSchema.model_validate(term),
    )


@router.get(
    "/terms/{term_uid}",
    dependencies=[
        event(
            "term_retrieve",
            target="terms",
            target_id=fastapi.Path(alias="term_uid"),
            description="Retrieve a term from the glossary",
        ),
        permissions_required("terms::*::view"),
        authenticate_connection,
    ],
    description="Retrieve a glossary term by its UID",
)
async def retrieve_term(
    session: DBSession,
    user: User,
    term_uid: TermUID,
):
    term = await crud.retrieve_term_by_uid(session, uid=term_uid)
    if not term:
        return response.notfound("Term matching the given query does not exist")

    if not term.relatives:
        await crud.update_related_terms(session, term=term)

    await crud.create_term_view(session, term=term, viewed_by=user)
    await session.commit()
    response_data = schemas.TermSchema.model_validate(term)
    return response.success(data=response_data)


@router.patch(
    "/terms/{term_uid}",
    dependencies=[
        event(
            "term_update",
            target="terms",
            target_id=fastapi.Path(alias="term_uid"),
            description="Update a term in the glossary",
        ),
        internal_api_clients_only,
        permissions_required("terms::*::update"),
        authentication_required,
        staff_user_only,
    ],
    description="Update a term by its UID",
)
async def update_term(
    session: DBSession,
    term_uid: TermUID,
    data: schemas.TermUpdateSchema,
):
    term = await crud.retrieve_term_by_uid(session, uid=term_uid)
    if not term:
        return response.notfound("Term matching the given query does not exist")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return response.bad_request("No update data provided")

    topics_data: typing.Optional[typing.Set[str]] = update_data.pop("topics", None)
    source_data: typing.Optional[typing.Dict[str, typing.Any]] = update_data.pop(
        "source", None
    )
    if topics_data:
        topics = await crud.retrieve_topics_by_name_or_uid(session, topics_data)
        if not topics:
            return response.bad_request("Invalid topics provided")

    if source_data:
        name = source_data.get("name")
        uid = source_data.get("uid")
        if term.source and (name == term.source.name or uid == term.source.uid):
            pass
        else:
            with capture.capture(ValueError, code=400):
                source, created = await crud.get_or_create_term_source(
                    session, **source_data
                )
                term_name = update_data.get("name", term.name)
                if not created and await crud.check_term_exists_for_source(
                    session,
                    term_name=term_name,
                    term_source=source,
                ):
                    return response.bad_request(
                        f"A term with the name {term_name!r} already exists for the source {source.name!r}"
                    )
                update_data["source"] = source

    for attr, value in update_data.items():
        setattr(term, attr, value)

    if topics_data:
        if data.replace_topics:
            term.topics.clear()
        term.topics |= set(topics)

    session.add(term)
    await session.commit()
    return response.success(data=schemas.TermSchema.model_validate(term))


@router.delete(
    "/terms/{term_uid}",
    dependencies=[
        event(
            "term_delete",
            target="terms",
            target_id=fastapi.Path(alias="term_uid"),
            description="Delete a term from the glossary",
        ),
        internal_api_clients_only,
        permissions_required("terms::*::delete"),
        authentication_required,
        staff_user_only,
    ],
    description="Delete a term by its UID",
)
async def delete_term(
    session: DBSession,
    term_uid: TermUID,
):
    term = await crud.retrieve_term_by_uid(session, uid=term_uid)
    if not term:
        return response.notfound("Term matching the given query does not exist")

    term.is_deleted = True
    session.add(term)
    await session.commit()
    return response.success(f"{term.name} has been deleted")


@router.get(
    "/topics",
    description="Retrieve a list of available topics",
    dependencies=[
        event(
            "topics_list",
            target="topics",
            description="Retrieve a list of available topics",
        ),
        permissions_required("topics::*::list"),
    ],
)
async def retrieve_topics(
    request: fastapi.Request,
    session: DBSession,
    limit: typing.Annotated[Limit, Le(50)] = 20,
    offset: Offset = 0,
):
    topics = await crud.retrieve_topics(session, limit=limit, offset=offset)
    response_data = [schemas.TopicSchema.model_validate(topic) for topic in topics]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.post(
    "/topics",
    description="Create a new topic",
    dependencies=[
        event(
            "topic_create",
            target="topics",
            description="Create a new topic",
        ),
        internal_api_clients_only,
        permissions_required("topics::*::create"),
        authentication_required,
        staff_user_only,
    ],
)
async def create_topic(
    session: DBSession,
    data: schemas.TopicCreateSchema,
):
    if await crud.retrieve_topics_by_name_or_uid(session, [data.name]):
        return response.bad_request("A topic with the same name already exists")

    topic = await crud.create_topic(session, **data.model_dump())
    await session.commit()
    return response.success(data=schemas.TopicSchema.model_validate(topic))


@router.get(
    "/topics/{topic_uid}",
    description="Retrieve a topic by its UID",
    dependencies=[
        event(
            "topic_retrieve",
            target="topics",
            target_id=fastapi.Path(alias="topic_uid"),
            description="Retrieve a topic by its UID",
        ),
        permissions_required("topics::*::view"),
    ],
)
async def retrieve_topic(session: DBSession, topic_uid: TopicUID):
    topic = await crud.retrieve_topic_by_uid(session, uid=topic_uid)
    if not topic:
        return response.notfound("Topic matching the given query does not exist")

    return response.success(data=schemas.TopicSchema.model_validate(topic))


@router.patch(
    "/topics/{topic_uid}",
    dependencies=[
        event(
            "topic_update",
            target="topics",
            target_id=fastapi.Path(alias="topic_uid"),
            description="Update a topic by its UID",
        ),
        internal_api_clients_only,
        permissions_required("topics::*::update"),
        authentication_required,
        staff_user_only,
    ],
    description="Update a topic by its UID",
)
async def update_topic(
    session: DBSession,
    topic_uid: TopicUID,
    data: schemas.TopicUpdateSchema,
):
    topic = await crud.retrieve_topic_by_uid(session, uid=topic_uid)
    if not topic:
        return response.notfound("Topic matching the given query does not exist")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return response.bad_request("No update data provided")

    for attr, value in update_data.items():
        setattr(topic, attr, value)

    session.add(topic)
    await session.commit()
    return response.success(data=schemas.TopicSchema.model_validate(topic))


@router.delete(
    "/topics/{topic_uid}",
    dependencies=[
        event(
            "topic_delete",
            target="topics",
            target_id=fastapi.Path(alias="topic_uid"),
            description="Delete a topic by its UID",
        ),
        internal_api_clients_only,
        permissions_required("topics::*::delete"),
        authentication_required,
        staff_user_only,
    ],
    description="Delete a topic by its UID",
)
async def delete_topic(session: DBSession, topic_uid: TopicUID):
    topic = await crud.retrieve_topic_by_uid(session, uid=topic_uid)
    if not topic:
        return response.notfound("Topic matching the given query does not exist")

    topic.is_deleted = True
    session.add(topic)
    await session.commit()
    return response.success(f"{topic.name} has been deleted")


@router.get(
    "/topics/{topic_uid}/terms",
    description="Retrieve a list of available terms associated with this topic",
    dependencies=[
        event(
            "topic_terms_list",
            target="terms",
            target_id=fastapi.Path(alias="topic_uid"),
            description="Retrieve a list of available terms associated with this topic",
        ),
        permissions_required(
            "topics::*::view",
            "terms::*::list",
        ),
    ],
)
async def retrieve_topic_terms(
    request: fastapi.Request,
    session: DBSession,
    topic_uid: TopicUID,
    startswith: Startswith = None,
    verified: Verified = True,
    source: Source = None,
    limit: typing.Annotated[Limit, Le(100)] = 20,
    offset: Offset = 0,
):
    topic = await crud.retrieve_topic_by_uid(session, uid=topic_uid)
    if not topic:
        return response.notfound("Topic matching the given query does not exist")
    if source:
        source = await crud.retrieve_term_source_by_name_or_uid(session, source)
        if not source:
            return response.bad_request("Invalid source provided")

    terms = await crud.retrieve_topic_terms(
        session,
        topic=topic,
        startswith=startswith,
        verified=verified,
        source=source,
        limit=limit,
        offset=offset,
    )
    response_data = [schemas.TermSchema.model_validate(term) for term in terms]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/sources",
    description="Retrieve a list of available term sources",
    dependencies=[
        event(
            "term_sources_list",
            target="term_sources",
            description="Retrieve a list of available term sources",
        ),
        permissions_required("term_sources::*::list"),
    ],
)
async def retrieve_term_sources(
    request: fastapi.Request,
    session: DBSession,
    limit: typing.Annotated[Limit, Le(50)] = 20,
    offset: Offset = 0,
):
    term_sources = await crud.retrieve_term_sources(session, limit=limit, offset=offset)
    response_data = [
        schemas.TermSourceSchema.model_validate(term_source)
        for term_source in term_sources
    ]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.post(
    "/sources",
    description="Create a new term source",
    dependencies=[
        event(
            "term_source_create",
            target="term_sources",
            description="Create a new term source",
        ),
        internal_api_clients_only,
        permissions_required("term_sources::*::create"),
        authentication_required,
        staff_user_only,
    ],
)
async def create_term_source(
    session: DBSession,
    data: schemas.TermSourceCreateSchema,
):
    term_source = await crud.create_term_source(session, **data.model_dump())
    await session.commit()
    return response.success(data=schemas.TermSourceSchema.model_validate(term_source))


@router.get(
    "/sources/{term_source_uid}",
    description="Retrieve a term source by its UID",
    dependencies=[
        event(
            "term_source_retrieve",
            target="term_sources",
            target_id=fastapi.Path(alias="term_source_uid"),
            description="Retrieve a term source by its UID",
        ),
        permissions_required("term_sources::*::view"),
    ],
)
async def retrieve_term_source(
    session: DBSession,
    term_source_uid: TermSourceUID,
):
    term_source = await crud.retrieve_term_source_by_uid(session, uid=term_source_uid)
    if not term_source:
        return response.notfound("Term source matching the given query does not exist")

    return response.success(data=schemas.TermSourceSchema.model_validate(term_source))


@router.get(
    "/sources/{term_source_uid}/terms",
    description="Retrieve a list of available terms associated with this source",
    dependencies=[
        event(
            "term_source_terms_list",
            target="terms",
            target_id=fastapi.Path(alias="term_source_uid"),
            description="Retrieve a list of available terms associated with this source",
        ),
        permissions_required(
            "term_sources::*::view",
            "terms::*::list",
        ),
    ],
)
async def retrieve_source_terms(
    request: fastapi.Request,
    session: DBSession,
    term_source_uid: TermSourceUID,
    startswith: Startswith = None,
    verified: Verified = True,
    topics: typing.Annotated[
        Topics,
        MaxLen(10),
        Doc("What topics should the terms fetched be related to?"),
    ] = None,
    limit: typing.Annotated[Limit, Le(100)] = 20,
    offset: Offset = 0,
):
    term_source = await crud.retrieve_term_source_by_uid(session, uid=term_source_uid)
    if not term_source:
        return response.notfound("Term source matching the given query does not exist")
    if topics:
        topics = await crud.retrieve_topics_by_name_or_uid(session, topics)

    terms = await crud.retrieve_term_source_terms(
        session,
        term_source=term_source,
        startswith=startswith,
        verified=verified,
        topics=topics,
        limit=limit,
        offset=offset,
    )
    response_data = [schemas.TermSchema.model_validate(term) for term in terms]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.patch(
    "/sources/{term_source_uid}",
    dependencies=[
        event(
            "term_source_update",
            target="term_sources",
            target_id=fastapi.Path(alias="term_source_uid"),
            description="Update a term source by its UID",
        ),
        internal_api_clients_only,
        permissions_required("term_sources::*::update"),
        authentication_required,
        staff_user_only,
    ],
    description="Update a term source by its UID",
)
async def update_term_source(
    session: DBSession,
    term_source_uid: TermSourceUID,
    data: schemas.TermSourceUpdateSchema,
):
    term_source = await crud.retrieve_term_source_by_uid(session, uid=term_source_uid)
    if not term_source:
        return response.notfound("Term source matching the given query does not exist")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return response.bad_request("No update data provided")

    for attr, value in update_data.items():
        setattr(term_source, attr, value)

    session.add(term_source)
    await session.commit()
    return response.success(data=schemas.TermSourceSchema.model_validate(term_source))


@router.delete(
    "/sources/{term_source_uid}",
    dependencies=[
        event(
            "term_source_delete",
            target="term_sources",
            target_id=fastapi.Path(alias="term_source_uid"),
            description="Delete a term source by its UID",
        ),
        internal_api_clients_only,
        permissions_required("term_sources::*::delete"),
        authentication_required,
        staff_user_only,
    ],
    description="Delete a term source by its UID",
)
async def delete_term_source(
    session: DBSession,
    term_source_uid: TermSourceUID,
):
    term_source = await crud.retrieve_term_source_by_uid(session, uid=term_source_uid)
    if not term_source:
        return response.notfound("Term source matching the given query does not exist")

    term_source.is_deleted = True
    await session.add(term_source)
    await session.commit()
    return response.success(f"{term_source.name} has been deleted")


@router.get(
    "/history",
    dependencies=[
        event(
            "search_records_list",
            target="search_records",
            description="Retrieve search history",
        ),
        permissions_required("search_records::*::list"),
        authentication_required,
    ],
    description="Retrieve the search history of the authenticated user/account",
)
async def retrieve_account_search_history(
    request: fastapi.Request,
    session: DBSession,
    account: ActiveUser,
    query: typing.Annotated[SearchQuery, MaxLen(100)] = None,
    topics: typing.Annotated[
        Topics,
        MaxLen(10),
        Doc("What topics should the search history retrieval be constrained to?"),
    ] = None,
    timestamp_gte: typing.Annotated[
        TimestampGte,
        Doc("Only include search records that were created after this timestamp"),
    ] = None,
    timestamp_lte: typing.Annotated[
        TimestampLte,
        Doc("Only include search records that were created before this timestamp"),
    ] = None,
    limit: typing.Annotated[Limit, Le(100)] = 50,
    offset: Offset = 0,
):
    if topics:
        topics = await crud.retrieve_topics_by_name_or_uid(session, topics)

    search_history = await crud.retrieve_account_search_history(
        session,
        account=account,
        query=query,
        topics=topics,
        timestamp_gte=timestamp_gte,
        timestamp_lte=timestamp_lte,
        limit=limit,
        offset=offset,
    )

    response_data = [
        schemas.SearchRecordSchema.model_validate(search_record)
        for search_record in search_history
    ]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.delete(
    "/history",
    dependencies=[
        event(
            "search_records_delete",
            target="search_records",
            description="Delete search history",
        ),
        permissions_required("search_records::*::delete"),
        authentication_required,
    ],
    description="Delete the search history of the authenticated user/account",
)
async def delete_account_search_history(
    session: DBSession,
    account: ActiveUser,
    # Query parameters
    query: typing.Annotated[SearchQuery, MaxLen(100)] = None,
    topics: typing.Annotated[
        Topics,
        MaxLen(10),
        Doc("What topics should the search history retrieval be constrained to?"),
    ] = None,
    timestamp_gte: typing.Annotated[
        TimestampGte,
        Doc("Only include search records that were created after this timestamp"),
    ] = None,
    timestamp_lte: typing.Annotated[
        TimestampLte,
        Doc("Only include search records that were created before this timestamp"),
    ] = None,
):
    if topics:
        topics = await crud.retrieve_topics_by_name_or_uid(session, topics)

    deleted_records_count = await crud.delete_account_search_history(
        session,
        account=account,
        query=query,
        topics=topics,
        timestamp_gte=timestamp_gte,
        timestamp_lte=timestamp_lte,
    )

    await session.commit()
    return response.success(f"{deleted_records_count} search records have been deleted")


@router.get(
    "/metrics",
    dependencies=[
        event(
            "account_search_metrics_retrieve",
            target="search_records",
            description="Retrieve account search metrics",
        ),
        permissions_required("search_records::*::list"),
        authentication_required,
    ],
    description="Retrieve search metrics of the authenticated user/account",
)
async def account_search_metrics(
    request: fastapi.Request,
    session: DBSession,
    account: ActiveUser,
    timestamp_gte: typing.Annotated[
        TimestampGte,
        Doc("Only include search records that were created after this timestamp"),
    ],
    timestamp_lte: typing.Annotated[
        TimestampLte,
        Doc("Only include search records that were created before this timestamp"),
    ],
):
    client = getattr(request.state, "client", None)
    search_metrics = await crud.generate_account_search_metrics(
        session,
        account=account,
        client=client,
        timestamp_gte=timestamp_gte,
        timestamp_lte=timestamp_lte,
    )
    return response.success(data=search_metrics)


@router.get(
    "/metrics/global",
    description="Retrieve global search metrics",
    dependencies=[
        event(
            "global_search_metrics_retrieve",
            target="search_records",
            description="Retrieve global search metrics",
        ),
        internal_api_clients_only,
        permissions_required("search_records::*::list"),
    ],
)
async def global_search_metrics(
    session: DBSession,
    timestamp_gte: typing.Annotated[
        TimestampGte,
        Doc("Only include search records that were created after this timestamp"),
    ],
    timestamp_lte: typing.Annotated[
        TimestampLte,
        Doc("Only include search records that were created before this timestamp"),
    ],
):
    search_metrics = await crud.generate_global_search_metrics(
        session,
        timestamp_gte=timestamp_gte,
        timestamp_lte=timestamp_lte,
    )
    return response.success(data=search_metrics)
