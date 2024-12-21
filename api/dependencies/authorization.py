import fastapi
import typing
from starlette.requests import HTTPConnection

from helpers.fastapi.dependencies.access_control import access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.dependencies.connections import _DBSession, DBSession
from helpers.fastapi.dependencies import Dependency

from apps.clients.models import APIClient
from apps.clients.crud import retrieve_api_client


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
        if not (api_client or api_client.disabled):
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
Connection dependency. 

Checks if the connection was made by an authorized/valid API client.
Attaches the client object to the connection state if the client is authorized.
"""

# Used Union[Any, HTTPConnection] to allow for the Annotated dependency type
# to be used in place of the regular connection dependency, without fastapi complaining
AuthorizedAPIClient = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], authorized_api_client_only
]
"""
Annotated dependency type that checks if the connection was 
made by an authorized/valid API client.
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
    Request dependency.

    Checks if the connection was made by an authorized/valid INTERNAL API client.
    """
    _depends = access_control(_is_internal_client)
    return await _depends.dependency(connection, session)


InternalAPIClient = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], internal_api_clients_only
]
"""
Annotated dependency type that checks if the connection was made 
by an authorized/valid INTERNAL API client.
"""


__all__ = [
    "authorized_api_client_only",
    "AuthorizedAPIClient",
    "internal_api_clients_only",
    "InternalAPIClient",
]
