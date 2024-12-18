import fastapi
import typing
from helpers.fastapi.dependencies.access_control import request_access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.dependencies.requests import _DBSession, RequestDBSession
from helpers.fastapi.dependencies import Dependency

from apps.clients.models import APIClient
from apps.clients.crud import retrieve_api_client


API_SECRET_HEADER = "X-CLIENT-SECRET"
CLIENT_ID_HEADER = "X-CLIENT-ID"


async def check_client_credentials(request: fastapi.Request, session: _DBSession):
    """
    Checks if the request was made by an registered/authorized API client,
    by validating the API secret and client ID in the request headers.
    """
    client = getattr(request.state, "client", None)
    if isinstance(client, APIClient):
        return True

    session = session or next(get_async_session())
    api_secret = request.headers.get(API_SECRET_HEADER)
    client_id = request.headers.get(CLIENT_ID_HEADER)

    if not (api_secret and client_id):
        return False

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

    request.state.client = api_client
    return True


authorized_api_client_only = request_access_control(
    check_client_credentials,
    status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
    message="Unauthorized API client! Ensure you have provided a "
    "valid API secret and client ID in the request headers.",
)
"""
Request dependency. 

Checks if the request was made by an authorized API client.
Attaches the client object to the request state if the client is authorized.
"""

# Used Union[Any, fastapi.Request] to allow for the Annotated dependency type
# to be used in place of the regular request dependency, without fastapi complaining
AuthorizedAPIClient = typing.Annotated[
    typing.Union[typing.Any, fastapi.Request], authorized_api_client_only
]
"""Annotated dependency type that checks if the request was made by an authorized API client."""


def _is_internal_client(request: fastapi.Request, _):
    client = getattr(request.state, "client", None)
    if not isinstance(client, APIClient):
        return False
    return client.client_type == APIClient.ClientType.INTERNAL


@Dependency
async def internal_api_clients_only(
    request: AuthorizedAPIClient, session: RequestDBSession
):
    """
    Request dependency.

    Checks if the request was made by an authorized INTERNAL API client.
    """
    _depends = request_access_control(_is_internal_client)
    return await _depends.dependency(request, session)


InternalAPIClient = typing.Annotated[
    typing.Union[typing.Any, fastapi.Request], internal_api_clients_only
]
"""Annotated dependency type that checks if the request was made by an authorized INTERNAL API client."""


__all__ = [
    "authorized_api_client_only",
    "AuthorizedAPIClient",
    "internal_api_clients_only",
    "InternalAPIClient",
]
