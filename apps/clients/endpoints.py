from os import name
import typing
from annotated_types import Le
import fastapi

from helpers.fastapi.utils import timezone

from . import schemas
from . import crud
from helpers.fastapi.dependencies.connections import DBSession
from helpers.fastapi.dependencies.access_control import ActiveUser
from api.dependencies.authorization import (
    internal_api_clients_only,
    permissions_required,
)
from api.dependencies.authentication import authentication_required
from helpers.fastapi.response import shortcuts as response
from helpers.fastapi.response.pagination import paginated_data
from apps.clients.models import APIClient
from helpers.fastapi.requests.query import Offset, Limit
from .permissions import (
    DEFAULT_PERMISSIONS_SETS,
    PermissionCreateSchema,
    PermissionSchema,
)


router = fastapi.APIRouter(
    dependencies=[
        internal_api_clients_only,
        permissions_required("api_clients::*::*"),
        authentication_required,
    ]
)


@router.post(
    "",
    description="Create a new API client.",
    dependencies=[
        permissions_required("api_clients::*::create"),
    ],
)
async def create_client(
    data: schemas.APIClientCreateSchema,
    session: DBSession,
    account: ActiveUser,
):
    is_user_client = data.client_type == APIClient.ClientType.USER
    if is_user_client:
        can_create_more_clients = await crud.check_account_can_create_more_clients(
            session, account
        )
        if not can_create_more_clients:
            return response.bad_request("Maximum number of API clients reached!")
    else:
        if not account.is_admin:
            return response.forbidden(
                "You are not allowed to create this type of client!"
            )

    async with session.begin_nested():
        permissions = DEFAULT_PERMISSIONS_SETS.get(data.client_type.lower(), [])
        if is_user_client:
            api_client = await crud.create_api_client(
                session,
                account=account,
                created_by=account,
                **data.model_dump(),
                permissions=permissions,
            )
        else:
            api_client = await crud.create_api_client(
                session,
                created_by=account,
                **data.model_dump(),
                permissions=permissions,
            )
        await session.flush()
        await crud.create_api_key(session, client=api_client)

    await session.commit()
    await session.refresh(api_client, attribute_names=["api_key"])
    return response.created(
        "API client created successfully!",
        data=schemas.APIClientSchema.model_validate(api_client),
    )


@router.get(
    "",
    description="Retrieve all API clients associated with the authenticated account.",
    dependencies=[
        permissions_required("api_clients::*::list"),
    ],
)
async def retrieve_clients(
    request: fastapi.Request,
    session: DBSession,
    account: ActiveUser,
    client_type: typing.Annotated[
        typing.Optional[APIClient.ClientType],
        fastapi.Query(description="API client type"),
    ] = None,
    limit: typing.Annotated[Limit, Le(100)] = 100,
    offset: Offset = 0,
):
    filters = {"limit": limit, "offset": offset}
    client_type = client_type or APIClient.ClientType.USER

    if client_type == APIClient.ClientType.USER:
        filters["account_id"] = account.id
    else:
        if not account.is_admin:
            return response.forbidden(
                "You are not allowed to access this type of client!"
            )
    filters["client_type"] = client_type

    api_clients = await crud.retrieve_api_clients(session, **filters)
    response_data = [
        schemas.APIClientSchema.model_validate(client) for client in api_clients
    ]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{client_uid}",
    description="Retrieve a single API client by UID.",
    dependencies=[
        permissions_required("api_clients::*::view"),
    ],
)
async def retrieve_client(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    # If the user is not an admin, they can only view their own clients
    if not account.is_admin:
        filters = {
            "account_id": account.id,
            "client_type": APIClient.ClientType.USER,
        }

    api_client = await crud.retrieve_api_client(session, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")
    return response.success(data=schemas.APIClientSchema.model_validate(api_client))


@router.patch(
    "/{client_uid}",
    description="Update an API client by UID.",
    dependencies=[
        permissions_required("api_clients::*::update"),
    ],
)
async def update_client(
    data: schemas.APIClientUpdateSchema,
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    if not account.is_admin:
        filters = {
            "account_id": account.id,
            "client_type": APIClient.ClientType.USER,
        }
    api_client = await crud.retrieve_api_client(session, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    changed_data = data.model_dump(exclude_unset=True)
    if not changed_data:
        return response.bad_request("No data provided to update the client with!")

    if "name" in changed_data and not changed_data["name"]:
        changed_data.pop("name")

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
    "/bulk-delete",
    description="Bulk delete API clients by UID.",
    dependencies=[
        permissions_required("api_clients::*::delete"),
    ],
)
async def bulk_delete_clients(
    data: schemas.APIClientBulkDeleteSchema,
    session: DBSession,
    account: ActiveUser,
):
    filters = {"uids": data.client_uids}
    if not account.is_admin:
        filters = {
            "account_id": account.id,
            "client_type": APIClient.ClientType.USER,
        }
    api_clients = await crud.retrieve_api_clients_by_uid(session, **filters)
    if not api_clients:
        return response.notfound("Clients matching the given query do not exist")

    for api_client in api_clients:
        await crud.delete_api_client(session, api_client)

    await session.commit()
    return response.success(
        f"{len(api_clients)} API clients deleted successfully!",
    )


@router.delete(
    "/{client_uid}",
    description="Delete an API client by UID.",
    dependencies=[
        permissions_required("api_clients::*::delete"),
    ],
)
async def delete_client(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    if not account.is_admin:
        filters = {
            "account_id": account.id,
            "client_type": APIClient.ClientType.USER,
        }
    api_client = await crud.retrieve_api_client(session, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    await crud.delete_api_client(session, api_client)
    await session.commit()
    return response.success("API client deleted successfully!")


@router.post(
    "/{client_uid}/refresh-api-secret",
    description="Refresh the API secret for a client.",
    dependencies=[
        permissions_required("api_keys::*::update"),
    ],
)
async def refresh_client_api_secret(
    session: DBSession,
    account: ActiveUser,
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    if not account.is_admin:
        filters = {
            "account_id": account.id,
            "client_type": APIClient.ClientType.USER,
        }
    api_client = await crud.retrieve_api_client(session, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    api_key = await crud.refresh_api_key_secret(session, api_client.api_key)
    await session.commit()
    return response.success(
        "API secret refreshed successfully! Make sure to save it as this invalidates the old secret.",
        data=schemas.APIKeySchema.model_validate(api_key),
    )


@router.put(
    "/{client_uid}/update-permissions",
    description="Update API client permissions.",
    dependencies=[
        permissions_required("api_clients::*::permissions_update"),
    ],
)
async def update_client_permissions(
    session: DBSession,
    account: ActiveUser,
    data: typing.List[PermissionCreateSchema],
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    if not account.is_admin:
        filters = {
            "account_id": account.id,
            "client_type": APIClient.ClientType.USER,
        }

    api_client = await crud.retrieve_api_client(session, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    api_client.permissions = [str(schema) for schema in data]
    api_client.permissions_modified_at = timezone.now()
    session.add(api_client)
    await session.commit()
    permissions_data = [
        PermissionSchema.from_string(perm) for perm in api_client.permissions
    ]
    return response.success(
        "API client permissions updated successfully!", data=permissions_data
    )
