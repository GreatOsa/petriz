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


async def _get_user_from_auth_token(secret: str, session: _DBSession):
    token = await auth_tokens.get_auth_token_by_secret(session, secret)
    if token and token.is_valid:
        return token.owner
    return None


AUTHENTICATION_HEADER = "Authorization"
CREDENTIAL_SCHEME = "AuthToken"


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

    if client.client_type.lower() == APIClient.ClientType.USER:
        user = client.account

    else:
        async with get_async_session() as session:
            auth_header = connection.headers.get(AUTHENTICATION_HEADER)
            if not auth_header:
                return False

            scheme, _, credential = auth_header.partition(" ")
            if scheme.lower() != CREDENTIAL_SCHEME.lower():
                return False

            user = await _get_user_from_auth_token(credential, session)
        if not user:
            return False

    connection.state.user = user
    return True


@Dependency
# Override the regular `access_control` dependency factory, such that
# the authentication credential check is only done on authorized clients
# and the connection state is updated with the authenticated user if the credentials are valid
# else the connection state is left as is and returned
async def authenticate_connection(connection: AuthorizedAPIClient, session: DBSession):
    """
    Connection access control dependency.

    Checks if the connection has valid authentication credentials.

    Attaches the authenticated user to the connection state if the credentials are valid.
    Connection state is left as is if the credentials are invalid.

    :param connection: The HTTP connection.
    :param session: The connection's database session.
    :return: The updated connection if the credentials are valid.
    """
    _depends = access_control(
        check_authentication_credentials,
        raise_access_denied=False,
    )
    return await _depends.dependency(connection, session)


@Dependency
# Override the regular `access_control` dependency factory, such that
# the authentication credential check is only done on authorized clients
# and the connection state is updated with the authenticated user if the credentials are valid
# else an HTTP 401 Unauthorized error is raised
async def authentication_required(connection: AuthorizedAPIClient, session: DBSession):
    """
    Connection access control dependency.

    Checks if the connection has valid authentication credentials.
    Attaches the authenticated user to the connection state if the credentials are valid.
    Raises an HTTP 401 Unauthorized error if the credentials are invalid.

    :param connection: The HTTP connection.
    :param session: The connection's database session.
    :raises HTTPException: If the connection does not have valid authentication credentials.
    :return: The updated connection if the credentials are valid.
    """
    _depends = access_control(
        check_authentication_credentials,
        status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
        message="Missing or invalid authentication credentials!",
    )
    return await _depends.dependency(connection, session)


# Used Union[Any, HTTPConnection] to allow for the Annotated dependency type
# to be used in place of the regular connection dependency, without fastapi complaining
# about the type mismatch

AuthenticateConnection = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], authenticate_connection
]
"""
Annotated dependency type that checks if the connection has valid authentication credentials.

The authenticated user is attached to the connection state if the credentials are valid.
Else, the connection state is left as is and returned.

:raises HTTPException: If the connection does not have valid authentication credentials.
:return: The updated connection if the credentials are valid.
"""


AuthenticationRequired = typing.Annotated[
    typing.Union[typing.Any, HTTPConnection], authentication_required
]
"""
Annotated dependency type that checks if the connection has valid authentication credentials.

The authenticated user is attached to the connection state if the credentials are valid.
Else, an HTTP 401 Unauthorized error is raised.

:raises HTTPException: If the connection does not have valid authentication credentials.
:return: The updated connection if the credentials are valid.
"""


__all__ = [
    "authenticate_connection",
    "authentication_required",
    "AuthenticateConnection",
    "AuthenticationRequired",
]
