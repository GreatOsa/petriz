import fastapi
import typing
from starlette.requests import HTTPConnection

from helpers.fastapi.dependencies.access_control import access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.dependencies.connections import DBSession, _DBSession
from helpers.fastapi.dependencies import Dependency

from apps.clients.models import APIClient
from apps.clients.crud import retrieve_api_client
from ..permissions import resolve_permissions, check_permissions


API_SECRET_HEADER = "X-CLIENT-SECRET"
CLIENT_ID_HEADER = "X-CLIENT-ID"


async def check_client_credentials(connection: HTTPConnection, session: _DBSession):
    """
    Checks if the http connection was made by an authorized/valid API client,
    by validating the API secret and client ID in the connection headers.

    Attaches the client object to the connection state if the client is authorized.

    :param connection: The HTTP connection.
    :param session: The database session.
    :return: True if the connection was made by an authorized/valid API client, False otherwise.
    """
    client = getattr(connection.state, "client", None)
    if isinstance(client, APIClient):
        return True

    api_secret = connection.headers.get(API_SECRET_HEADER)
    client_id = connection.headers.get(CLIENT_ID_HEADER)

    if not (api_secret and client_id):
        return False

    async with get_async_session() as session:
        api_client = await retrieve_api_client(session, uid=client_id)
        if not api_client or api_client.disabled:
            return False

        api_secret_is_valid = (
            api_client.api_key
            and api_client.api_key.secret == api_secret
            and api_client.api_key.valid
        )
        if not api_secret_is_valid:
            return False

    connection.state.client = api_client
    return True


authorized_api_client_only = access_control(
    check_client_credentials,
    status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
    message="Unauthorized API client! Ensure you have provided a "
    "valid API secret and client ID in the connection headers.",
)
"""
Connection access control dependency. 

Checks if the connection was made by an authorized/valid API client.
Attaches the client object to the connection state if the client is authorized.

:raises HTTPException: If the connection was not made by an authorized/valid API client.
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

:raises HTTPException: If the connection was not made by an authorized/valid API client.
:return: The updated connection if the client is appropriately authorized.
"""


def _is_internal_client(connection: HTTPConnection, _):
    client = getattr(connection.state, "client", None)
    if not isinstance(client, APIClient):
        return False
    return client.client_type == APIClient.ClientType.INTERNAL


@Dependency
async def internal_api_clients_only(
    connection: AuthorizedAPIClient, session: DBSession
):
    """
    Connection access control dependency.

    Checks if the connection was made by an authorized/valid `INTERNAL` API client.

    :param connection: The HTTP connection.
    :param session: The database session.
    :raises HTTPException: If the connection was not made by an authorized/valid `INTERNAL` API client.
    :return: The updated connection if the client is appropriately authorized.
    """
    _depends = access_control(_is_internal_client)
    return await _depends.dependency(connection, session)


InternalAPIClient = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], internal_api_clients_only
]
"""
Annotated dependency type that checks if the connection was made 
by an authorized/valid `INTERNAL` API client.

Attaches the `INTERNAL` type client object to the connection state if the client is authorized.

:raises HTTPException: If the connection was not made by an authorized/valid `INTERNAL` API client.
"""


def permissions_required(*permissions: str):
    """
    Checks if the authorized API client has the required permissions.

    :param connection: The HTTP connection.
    :param permissions: The required permissions.
    :return: True if the client has the required permissions, False otherwise.
    """
    permission_set = resolve_permissions(*permissions)

    async def _check_client_permissions(connection: HTTPConnection, _):
        client = getattr(connection.state, "client", None)
        if not isinstance(client, APIClient):
            return False
        return check_permissions(client, *permission_set)

    return access_control(
        _check_client_permissions, message="Unauthorized resource access!"
    )


__all__ = [
    "authorized_api_client_only",
    "AuthorizedAPIClient",
    "internal_api_clients_only",
    "InternalAPIClient",
    "required_permissions",
]
