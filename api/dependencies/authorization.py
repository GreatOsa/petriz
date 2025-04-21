import typing
import fastapi
import pydantic
from starlette.requests import HTTPConnection
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from helpers.fastapi.dependencies.access_control import access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from apps.clients.models import APIClient, ClientType
from apps.clients.crud import retrieve_api_client
from apps.clients.permissions import resolve_permissions, check_permissions


class ClientCredentials(pydantic.BaseModel):
    connection: typing.Any
    client_id: str
    client_secret: str


CLIENT_SECRET_HEADER = "X-CLIENT-SECRET"
CLIENT_ID_HEADER = "X-CLIENT-ID"

x_client_id = APIKeyHeader(
    name=CLIENT_ID_HEADER,
    scheme_name="X-CLIENT-ID",
    auto_error=False,
    description="API client ID",
)
x_client_secret = APIKeyHeader(
    name=CLIENT_SECRET_HEADER,
    scheme_name="X-CLIENT-SECRET",
    auto_error=False,
    description="API client secret",
)


async def get_client_credentials(
    connection: HTTPConnection,
    client_id: typing.Annotated[typing.Optional[str], fastapi.Depends(x_client_id)],
    client_secret: typing.Annotated[
        typing.Optional[str], fastapi.Depends(x_client_secret)
    ],
) -> ClientCredentials:
    if not (client_id and client_secret):
        return ClientCredentials(
            connection=connection,
            client_id="",
            client_secret="",
        )
    return ClientCredentials(
        connection=connection,
        client_id=client_id,
        client_secret=client_secret,
    )


async def check_client_credentials(
    credentials: ClientCredentials,
    session: typing.Optional[AsyncSession],
) -> bool:
    """
    Checks if the http connection was made by an authorized/valid API client,
    by validating the API secret and client ID in the connection headers.

    Attaches the client object to the connection state if the client is authorized.

    :param credentials:
    :param session: The database session.
    :return: True if the connection was made by an authorized/valid API client, False otherwise.
    """
    if not session:
        raise ValueError("Database session is required for credentials check")

    client = getattr(credentials.connection.state, "client", None)
    if isinstance(client, APIClient):
        return True

    client_secret = credentials.client_secret
    client_id = credentials.client_id

    if not (client_secret and client_id):
        return False

    api_client = await retrieve_api_client(session, uid=client_id)
    if not api_client or api_client.is_disabled:
        return False

    api_secret_is_valid = (
        api_client.api_key
        and api_client.api_key.secret == client_secret
        and api_client.api_key.valid
    )
    if not api_secret_is_valid:
        return False

    # Update the connection state with the API client
    credentials.connection.state.client = api_client
    return True


authorized_api_client_only = access_control(
    get_client_credentials,
    check_client_credentials,
    status_code=fastapi.status.HTTP_403_FORBIDDEN,
    message="Unauthorized API client! Ensure you have provided a \
    valid API secret and client ID in the connection headers.",
)
"""
Connection access control dependency. 

Checks if the connection was made by an authorized/valid API client.
Attaches the client object to the connection state if the client is authorized.

:raises HTTPException/WebSocketDisconnect: If the connection was not made by an authorized/valid API client.
:return: The updated connection if the client is appropriately authorized.
"""

# Used Union[Any, HTTPConnection] to allow for the Annotated dependency type
# to be used in place of the regular connection dependency, without fastapi complaining
# about the type mismatch

AuthorizedAPIClient = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], authorized_api_client_only
]
"""
Annotated connection access control dependency type that checks if the connection was 
made by an authorized/valid API client.

Attaches the client object to the connection state if the client is authorized.

:raises HTTPException/WebSocketDisconnect: If the connection was not made by an authorized/valid API client.
:return: The updated connection if the client is appropriately authorized.
"""


async def is_internal_client(
    credentials: typing.Optional[ClientCredentials],
    session: typing.Optional[AsyncSession],
) -> bool:
    if not credentials or not await check_client_credentials(credentials, session):
        return False

    client: APIClient = credentials.connection.state.client
    return client.client_type.lower() == ClientType.INTERNAL


internal_api_clients_only = access_control(
    get_client_credentials,
    is_internal_client,
    status_code=fastapi.status.HTTP_403_FORBIDDEN,
    message="Unauthorized API client!",
)
"""
Connection access control dependency.

Checks if the connection was made by an authorized/valid `INTERNAL` API client.

:param connection: The HTTP connection.
:param session: The database session.
:raises HTTPException/WebSocketDisconnect: If the connection was not made by an authorized/valid `INTERNAL` API client.
:return: The updated connection if the client is appropriately authorized.
"""


InternalAPIClient = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], internal_api_clients_only
]
"""
Annotated dependency type that checks if the connection was made 
by an authorized/valid `INTERNAL` API client.

Attaches the `INTERNAL` type client object to the connection state if the client is authorized.

:raises HTTPException/WebSocketDisconnect: If the connection was not made by an authorized/valid `INTERNAL` API client.
"""


def permissions_required(*permissions: str):
    """
    Checks if the authorized API client has the required permissions.

    :param connection: The HTTP connection.
    :param permissions: The required permissions.
    :return: True if the client has the required permissions, False otherwise.
    """
    permission_set = resolve_permissions(*permissions)

    async def check_client_permissions(connection: HTTPConnection, _) -> bool:
        client = getattr(connection.state, "client", None)
        if not isinstance(client, APIClient):
            return False
        return check_permissions(client, *permission_set)

    return access_control(
        HTTPConnection,
        check_client_permissions,
        message="Unauthorized resource access!",
    )


__all__ = [
    "authorized_api_client_only",
    "AuthorizedAPIClient",
    "internal_api_clients_only",
    "InternalAPIClient",
    "permissions_required",
]
