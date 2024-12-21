import fastapi
import typing
from starlette.requests import HTTPConnection

from helpers.fastapi.dependencies.access_control import access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.dependencies.connections import _DBSession, DBSession
from helpers.fastapi.dependencies import Dependency

from apps.tokens import auth_tokens
from apps.clients.models import APIClient
from .authorization import AuthorizedAPIClient


async def _get_user_from_auth_token(auth_token: str, session: _DBSession):
    token = await auth_tokens.get_auth_token_by_secret(session, auth_token)
    if token and token.is_valid:
        return token.owner
    return None


AUTHENTICATION_HEADER = "Authorization"
AUTH_TOKEN_PREFIX = "AuthToken "


async def check_authentication_credentials(
    connection: HTTPConnection, session: _DBSession
):
    """
    Checks if the http connection has valid authentication credentials.

    Attaches the authenticated user to the connection state if the credentials are valid.

    :param connection: The HTTP connection.
    :param session: The database session.
    :return: True if the connection has valid authentication credentials, False otherwise.
    """
    client = getattr(connection.state, "client", None)
    if not isinstance(client, APIClient):
        return False

    if client.client_type == APIClient.ClientType.USER:
        user = client.account

    else:
        async with get_async_session() as session:
            auth_header = connection.headers.get(AUTHENTICATION_HEADER)
            if not auth_header:
                return False

            if not auth_header.startswith(AUTH_TOKEN_PREFIX):
                return False

            auth_token = auth_header.split(" ")[-1]
            user = await _get_user_from_auth_token(auth_token, session)
        if not user:
            return False

    connection.state.user = user
    return True


@Dependency
# Override the regular `access_control` dependency factory, such that
# the authentication credential check is only done on authorized clients
async def authentication_required(
    connection: AuthorizedAPIClient, session: DBSession
):
    """
    Request dependency.

    Checks if the connection has valid authentication credentials.
    Attaches the authenticated user to the connection state if the credentials are valid.
    """
    _depends = access_control(
        check_authentication_credentials,
        status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
        message="Missing or invalid authentication credentials!",
    )
    return await _depends.dependency(connection, session)


# Used Union[Any, HTTPConnection] to allow for the Annotated dependency type
# to be used in place of the regular connection dependency, without fastapi complaining
AuthenticationRequired = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], authentication_required
]
"""Annotated dependency type that checks if the connection has valid authentication credentials."""


__all__ = [
    "authentication_required",
    "AuthenticationRequired",
]
