from annotated_types import MaxLen, Le
import fastapi
import typing
from typing_extensions import Doc

from helpers.fastapi.dependencies.requests import RequestDBSession, RequestUser
from helpers.fastapi.dependencies.access_control import ActiveUser
from helpers.fastapi.response import shortcuts as response
from helpers.fastapi.response.pagination import paginated_data
from api.dependencies.authentication import authentication_required
from api.dependencies.authorization import (
    authorized_api_client_only,
    internal_api_clients_only,
)
from helpers.fastapi.requests.query import Limit, Offset
from .query import Startswith, Verified, Topics, SearchQuery, TimestampGte, TimestampLte
from . import schemas, crud


router = fastapi.APIRouter(
    dependencies=[
        authorized_api_client_only,
    ]
)


@router.get(
    "",
    dependencies=[authentication_required],
    description="Search the glossary for petroleum related terms",
)
async def search_glossary_for_terms(
    request: fastapi.Request,
    session: RequestDBSession,
    request_user: RequestUser,
    # Query parameters
    query: typing.Annotated[SearchQuery, MaxLen(100)] = None,
    topics: typing.Annotated[
        Topics,
        MaxLen(10),
        Doc("What topics should the search be constrained to?"),
    ] = None,
    startswith: Startswith = None,
    verified: Verified = None,
    limit: typing.Annotated[Limit, Le(50)] = 20,
    offset: Offset = 0,
):
    account = request_user if request_user.is_authenticated else None
    async with crud.record_search(
        session,
        query=query,
        topics=topics,
        account=account,
        metadata={
            "verified": verified,
            "startswith": startswith,
            "limit": limit,
            "offset": offset,
        },
    ):
        search_result = await crud.search_terms(
            session,
            query=query,
            topics=topics,
            startswith=startswith,
            verified=verified,
            limit=limit,
            offset=offset,
        )
        response_data = [
            schemas.TermSchema.model_validate(term) for term in search_result
        ]

    await session.commit()
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/term/{term_id}",
    description="Retrieve a glossary term by its UID",
)
async def retrieve_term_by_id(
    session: RequestDBSession,
    term_id: str = fastapi.Path(description="Glossary term UID"),
):
    term = await crud.retrieve_term_by_uid(session, uid=term_id)
    if not term:
        response.notfound("Term matching the given query does not exist")
    return response.success(data=schemas.TermSchema.model_validate(term))


@router.get(
    "/history",
    dependencies=[
        authentication_required,
    ],
    description="Retrieve the search history of the authenticated user/account",
)
async def retrieve_account_search_history(
    request: fastapi.Request,
    session: RequestDBSession,
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
    limit: typing.Annotated[Limit, Le(100)] = 50,
    offset: Offset = 0,
):
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


@router.post(
    "/term/contribute",
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ],
    description="Contribute a term to the glossary",
)
async def contribute_term_to_glossary(
    data: schemas.TermCreateSchema,
    session: RequestDBSession,
):
    term = await crud.create_term(session, **data.model_dump(), verified=False)
    await session.commit()
    await session.refresh(term)
    return response.created(
        f"{term.name} has been added to the glossary. Thanks for your contribution!",
        data=schemas.TermSchema.model_validate(term),
    )
