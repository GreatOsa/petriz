import typing
import fastapi

from . import schemas
from . import crud
from helpers.fastapi.dependencies.connections import DBSession
from helpers.fastapi.dependencies.access_control import ActiveUser
from api.dependencies.authorization import internal_api_clients_only
from api.dependencies.authentication import authentication_required
from helpers.fastapi.response import shortcuts as response


router = fastapi.APIRouter(
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ]
)


@router.post(
    "",
    description="Create a new API client.",
)
async def create_client(
    data: schemas.APIClientCreateSchema,
    session: DBSession,
    account: ActiveUser,
):
    can_create_client = await crud.check_account_can_create_more_clients(
        session, account
    )
    if not can_create_client:
        return response.bad_request("Maximum number of API clients reached!")

    async with session.begin_nested():
        api_client = await crud.create_api_client(
            session, account_id=account.id, **data.model_dump()
        )
        await session.flush()
        api_key = await crud.create_api_key(session, client=api_client)

    await session.commit()
    api_client.api_key = api_key
    return response.created(
        "API client created successfully!",
        data=schemas.APIClientSchema.model_validate(api_client),
    )


@router.get(
    "",
    description="Retrieve all API clients associated with the authenticated account.",
)
async def retrieve_clients(
    session: DBSession,
    account: ActiveUser,
    limit: typing.Annotated[int, fastapi.Query(le=100, ge=1)] = 100,
    offset: typing.Annotated[int, fastapi.Query(ge=0)] = 0,
):
    api_clients = await crud.retrieve_api_clients(
        session, account_id=account.id, limit=limit, offset=offset
    )
    response_data = [
        schemas.APIClientSchema.model_validate(client) for client in api_clients
    ]
    return response.success(data=response_data)


@router.get(
    "/{client_uid}",
    description="Retrieve a single API client by UID.",
)
async def retrieve_client(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    api_client = await crud.retrieve_api_client(
        session, uid=client_uid, account_id=account.id
    )
    if not api_client:
        return response.notfound("Client matching the given query does not exist")
    return response.success(data=schemas.APIClientSchema.model_validate(api_client))


@router.patch(
    "/{client_uid}",
    description="Update an API client by UID.",
)
async def update_client(
    data: schemas.APIClientUpdateSchema,
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    api_client = await crud.retrieve_api_client(
        session, uid=client_uid, account_id=account.id
    )
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    changed_data = data.model_dump(exclude_unset=True)
    if not changed_data:
        return response.bad_request("No data provided to update the client with!")

    for key, value in changed_data.items():
        setattr(api_client, key, value)

    session.add(api_client)
    await session.commit()
    await session.refresh(api_client)
    return response.success(
        "API client updated successfully!",
        data=schemas.APIClientSchema.model_validate(api_client),
    )


@router.delete(
    "/{client_uid}",
    description="Delete an API client by UID.",
)
async def delete_client(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    api_client = await crud.retrieve_api_client(
        session, uid=client_uid, account_id=account.id
    )
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    await crud.delete_api_client(session, api_client)
    await session.commit()
    return response.no_content("API client deleted successfully!")


@router.delete(
    "/bulk-delete",
    description="Bulk delete API clients by UID.",
)
async def bulk_delete_clients(
    data: schemas.APIClientBulkDeleteSchema,
    session: DBSession,
    account: ActiveUser,
):
    api_clients = await crud.retrieve_api_clients_by_uid(
        session, uids=data.client_uids, account_id=account.id
    )
    if not api_clients:
        return response.notfound("Clients matching the given query do not exist")

    for api_client in api_clients:
        await crud.delete_api_client(session, api_client)

    await session.commit()
    return response.no_content(
        f"{len(api_clients)} API clients deleted successfully!",
    )


@router.get(
    "/{client_uid}/api-key",
    description="Retrieve the API key for a client.",
)
async def retrieve_client_api_key(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    api_client = await crud.retrieve_api_client(
        session, uid=client_uid, account_id=account.id
    )
    if not api_client:
        return response.notfound("Client matching the given query does not exist")
    
    if not api_client.api_key:
        await crud.create_api_key(session, client=api_client)
        await session.commit()

    await session.refresh(api_client, attribute_names=["api_key"])
    return response.success(
        data=schemas.APIKeySchema.model_validate(api_client.api_key)
    )


@router.patch(
    "/{client_uid}/api-key",
    description="Update the API key for a client.",
)
async def update_client_api_key(
    data: schemas.APIKeyUpdateSchema,
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    api_client = await crud.retrieve_api_client(
        session, uid=client_uid, account_id=account.id
    )

    api_key = api_client.api_key
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return response.bad_request("No data provided to update the API key with!")

    for key, value in update_data.items():
        setattr(api_key, key, value)

    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return response.success(
        "API key updated successfully!",
        data=schemas.APIKeySchema.model_validate(api_key),
    )


@router.post(
    "/{client_uid}/api-key/refresh-secret",
    description="Refresh the API secret for a client.",
)
async def refresh_client_api_secret(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    api_client = await crud.retrieve_api_client(
        session, uid=client_uid, account_id=account.id
    )
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    api_key = await crud.refresh_api_key_secret(session, api_client.api_key)
    await session.commit()
    return response.success(
        "API secret refreshed successfully! Make sure to save it as this invalidates the old secret.",
        data=schemas.APIKeySchema.model_validate(api_key),
    )
