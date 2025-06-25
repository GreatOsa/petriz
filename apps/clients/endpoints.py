import typing
from annotated_types import Le
import fastapi
from sqlalchemy.exc import OperationalError

from helpers.fastapi.dependencies.connections import AsyncDBSession
from helpers.fastapi.dependencies.access_control import ActiveUser
from helpers.fastapi.response import shortcuts as response
from helpers.fastapi.response.pagination import paginated_data, PaginatedResponse
from helpers.fastapi.exceptions import capture
from helpers.fastapi.utils import timezone
from helpers.fastapi.requests.query import Offset, Limit, clean_params
from api.dependencies.authorization import (
    internal_api_clients_only,
    permissions_required,
)
from helpers.fastapi.auditing.dependencies import event
from api.dependencies.authentication import authentication_required
from apps.clients.models import ClientType, generate_api_key_secret
from apps.accounts.models import Account
from . import schemas, crud
from .query import APIClientOrdering
from .permissions import (
    ALLOWED_PERMISSIONS_SETS,
    PermissionCreateSchema,
    PermissionSchema,
    validate_permissions,
)


router = fastapi.APIRouter(
    dependencies=[
        event(
            "clients_access",
            description="Access clients endpoints.",
        ),
        internal_api_clients_only,
        permissions_required("api_clients::*::*"),
        authentication_required,
    ],
    tags=["api_clients"],
)


@router.post(
    "",
    description="Create a new API client.",
    dependencies=[
        event(
            "api_client_create",
            target="api_clients",
            description="Create a new API client.",
        ),
        permissions_required("api_clients::*::create"),
    ],
    response_model=response.DataSchema[schemas.APIClientSchema],
    status_code=201,
    operation_id="create_api_client",
)
async def create_api_client(
    data: schemas.APIClientCreateSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    is_user_client = data.client_type == ClientType.USER
    if is_user_client:
        can_create_more_clients = await crud.check_account_can_create_more_clients(
            session, account_id=user.id
        )
        if not can_create_more_clients:
            return response.bad_request("Maximum number of API clients reached!")
    else:
        if not user.is_admin:
            return response.forbidden(
                "You are not allowed to create this type of client!"
            )

    async with session.begin_nested():
        permissions = ALLOWED_PERMISSIONS_SETS.get(data.client_type.value, set())
        if is_user_client:
            api_client = await crud.create_api_client(
                session,
                account_id=user.id,
                created_by_id=user.id,
                **data.model_dump(),
                permissions=permissions,
            )
        else:
            api_client = await crud.create_api_client(
                session,
                created_by_id=user.id,
                **data.model_dump(),
                permissions=permissions,
            )
        await session.flush()
        await crud.create_api_key(session, client_id=api_client.id)

    await session.commit()
    await session.refresh(api_client, attribute_names=["api_key"])
    return response.created(
        "API client created successfully!",
        data=schemas.APIClientSchema.model_validate(api_client),
    )


@router.get(
    "",
    description="Retrieve all API clients associated with the authenticated user.",
    dependencies=[
        event(
            "api_client_list",
            target="api_clients",
            description="Retrieve all API clients associated with the authenticated user.",
        ),
        permissions_required("api_clients::*::list"),
    ],
    response_model=PaginatedResponse[schemas.APIClientSchema],  # type: ignore
    status_code=200,
    operation_id="retrieve_api_clients",
)
async def retrieve_api_clients(
    request: fastapi.Request,
    session: AsyncDBSession,
    user: ActiveUser[Account],
    ordering: APIClientOrdering,
    client_type: typing.Annotated[
        typing.Optional[ClientType],
        fastapi.Query(description="API client type"),
    ] = None,
    limit: typing.Annotated[Limit, Le(100)] = 100,
    offset: Offset = 0,
):
    filters: typing.Dict[str, typing.Any] = {"limit": limit, "offset": offset}
    client_type = client_type or ClientType.USER

    if client_type == ClientType.USER:
        filters["account_id"] = user.id
    else:
        if not user.is_admin:
            return response.forbidden(
                "You are not allowed to access this type of client!"
            )
    filters["client_type"] = client_type

    params = clean_params(ordering=ordering)
    api_clients = await crud.retrieve_api_clients(session, **params, **filters)
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
        event(
            "api_client_retrieve",
            target="api_clients",
            target_uid=fastapi.Path(alias="client_uid", alias_priority=1),
            description="Retrieve a single API client by UID.",
        ),
        permissions_required("api_clients::*::view"),
    ],
    response_model=response.DataSchema[schemas.APIClientSchema],
    status_code=200,
    operation_id="retrieve_api_client",
)
async def retrieve_api_client(
    session: AsyncDBSession,
    user: ActiveUser[Account],
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters: typing.Dict[str, typing.Any] = {"uid": client_uid}
    # If the user is not an admin, they can only view their own clients
    if not user.is_admin:
        filters = {
            **filters,
            "account_id": user.id,
            "client_type": ClientType.USER,
        }

    api_client = await crud.retrieve_api_client(session, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")
    return response.success(data=schemas.APIClientSchema.model_validate(api_client))


@router.patch(
    "/{client_uid}",
    description="Update an API client by UID.",
    dependencies=[
        event(
            "api_client_update",
            target="api_clients",
            target_uid=fastapi.Path(alias="client_uid", alias_priority=1),
            description="Update an API client by UID.",
        ),
        permissions_required("api_clients::*::update"),
    ],
    response_model=response.DataSchema[schemas.APIClientSchema],
    status_code=200,
    operation_id="update_api_client",
)
async def update_api_client(
    data: schemas.APIClientUpdateSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    if not user.is_admin:
        filters = {
            **filters,
            "account_id": user.id,
            "client_type": ClientType.USER,
        }

    async with capture.capture(
        OperationalError,
        code=409,
        content="Can not update client due to conflict",
    ):
        api_client = await crud.retrieve_api_client(session, for_update=True, **filters)
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
        event(
            "api_client_bulk_delete",
            target="api_clients",
            description="Bulk delete API clients by UID.",
        ),
        permissions_required("api_clients::*::delete"),
    ],
    response_model=response.DataSchema[None],
    status_code=200,
    operation_id="bulk_delete_api_clients",
)
async def bulk_delete_api_clients(
    data: schemas.APIClientBulkDeleteSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    filters = {
        "uids": data.client_uids,
        "deleted_by_id": user.id,
    }
    if not user.is_admin:
        filters = {
            **filters,
            "account_id": user.id,
            "client_type": ClientType.USER,
        }
    deleted_clients_count = await crud.bulk_delete_api_clients_by_uid(
        session, **filters
    )
    if not deleted_clients_count:
        return response.notfound("Clients matching the given query do not exist")

    await session.commit()
    return response.success(
        f"{deleted_clients_count} API clients deleted successfully!",
    )


@router.delete(
    "/{client_uid}",
    description="Delete an API client by UID.",
    dependencies=[
        event(
            "api_client_delete",
            target="api_clients",
            target_uid=fastapi.Path(alias="client_uid", alias_priority=1),
            description="Delete an API client by UID.",
        ),
        permissions_required("api_clients::*::delete"),
    ],
    response_model=response.DataSchema[None],
    status_code=200,
    operation_id="delete_api_client",
)
async def delete_api_client(
    session: AsyncDBSession,
    user: ActiveUser[Account],
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid, "deleted_by_id": user.id}
    if not user.is_admin:
        filters = {
            **filters,
            "account_id": user.id,
            "client_type": ClientType.USER,
        }

    deleted_client = await crud.delete_api_client(session, **filters)
    if not deleted_client:
        return response.notfound("Client matching the given query does not exist")

    await session.commit()
    return response.success("API client deleted successfully!")


@router.post(
    "/{client_uid}/refresh-api-secret",
    description="Refresh the API secret for a client.",
    dependencies=[
        event(
            "api_client_secret_refresh",
            target="api_clients",
            target_uid=fastapi.Path(alias="client_uid", alias_priority=1),
            description="Refresh the API secret for a client.",
        ),
        permissions_required("api_keys::*::update"),
    ],
    response_model=response.DataSchema[schemas.APIKeySchema],
    status_code=200,
    operation_id="refresh_client_api_secret",
)
async def refresh_client_api_secret(
    session: AsyncDBSession,
    user: ActiveUser[Account],
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters = {"uid": client_uid}
    if not user.is_admin:
        filters = {
            **filters,
            "account_id": user.id,
            "client_type": ClientType.USER,
        }

    async with capture.capture(
        OperationalError, code=409, content="Can not update client due to conflict"
    ):
        api_client = await crud.retrieve_api_client(session, for_update=True, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    api_key = api_client.api_key
    api_key.secret = generate_api_key_secret()
    session.add(api_key)
    await session.commit()
    return response.success(
        "API secret refreshed successfully! Make sure to save it as this invalidates the old secret.",
        data=schemas.APIKeySchema.model_validate(api_key),
    )


@router.put(
    "/{client_uid}/update-permissions",
    description="Update API client permissions.",
    dependencies=[
        event(
            "api_client_permissions_update",
            target="api_clients",
            target_uid=fastapi.Path(alias="client_uid", alias_priority=1),
            description="Update API client permissions.",
        ),
        permissions_required("api_clients::*::permissions_update"),
    ],
    response_model=response.DataSchema[typing.List[PermissionSchema]],
    status_code=200,
    operation_id="update_api_client_permissions",
)
async def update_api_client_permissions(
    session: AsyncDBSession,
    user: ActiveUser[Account],
    data: typing.List[PermissionCreateSchema],
    client_uid: str = fastapi.Path(description="API client UID"),
):
    filters: typing.Dict[str, typing.Any] = {"uid": client_uid}
    if not user.is_admin:
        filters = {
            **filters,
            "account_id": user.id,
            "client_type": ClientType.USER,
        }

    async with capture.capture(
        OperationalError, code=409, content="Can not update client due to conflict"
    ):
        api_client = await crud.retrieve_api_client(session, for_update=True, **filters)
    if not api_client:
        return response.notfound("Client matching the given query does not exist")

    async with capture.capture(ValueError, code=400):
        validate_permissions(api_client, *data)

    api_client.permissions = [str(perm_schema) for perm_schema in data]
    api_client.permissions_modified_at = timezone.now()
    session.add(api_client)
    await session.commit()
    permissions_data = [
        PermissionSchema.from_string(perm) for perm in api_client.permissions
    ]
    return response.success(
        "API client permissions updated successfully!", data=permissions_data
    )
