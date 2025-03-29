import pydantic
import fastapi
import typing
from starlette.requests import HTTPConnection
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security.http import HTTPAuthorizationCredentials

from helpers.fastapi.dependencies.access_control import access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.security.token import HTTPToken

from apps.tokens import auth_tokens
from apps.clients.models import APIClient
from .authorization import AuthorizedAPIClient


authtoken = HTTPToken(
    name="authtoken",
    scheme_name="AuthToken",
    tokenFormat="AuthToken <token>",
    auto_error=False,
)


class AuthenticationCredentials(pydantic.BaseModel):
    connection: typing.Any
    scheme: str
    token: str


def get_authentication_credentials(
    connection: AuthorizedAPIClient,
    token_credentials: typing.Annotated[
        typing.Optional[HTTPAuthorizationCredentials],
        fastapi.Depends(authtoken),
    ],
) -> AuthenticationCredentials:
    if not token_credentials:
        return AuthenticationCredentials(
            connection=connection,
            scheme="",
            token="",
        )
    return AuthenticationCredentials(
        connection=connection,
        scheme=token_credentials.scheme,
        token=token_credentials.credentials,
    )


async def get_user_from_auth_token(secret: str, session: AsyncSession):
    token = await auth_tokens.get_auth_token_by_secret(session, secret)
    if token and token.is_valid:
        return token.owner
    return None


async def check_authentication_credentials(
    credentials: AuthenticationCredentials,
    session: typing.Optional[AsyncSession] = None,
):
    """
    Checks if the given authentication credentials are valid.

    Attaches the authenticated user to the connection state if the credentials are valid.

    :param credentials:
    :param session: The database session.
    :return: True if the authentication credentials are valid, False otherwise.
    """
    client = getattr(credentials.connection.state, "client", None)
    if not isinstance(client, APIClient):
        return False

    if client.client_type.lower() == APIClient.ClientType.USER:
        user = client.account

    else:
        if not credentials.token:
            return False

        if session:
            user = await get_user_from_auth_token(credentials.token, session)
        else:
            async with get_async_session() as session:
                user = await get_user_from_auth_token(credentials.token, session)
        if not user:
            return False

    credentials.connection.state.user = user
    return True


authenticate_connection = access_control(
    get_authentication_credentials,
    check_authentication_credentials,
    raise_access_denied=False,
)
"""
Connection access control dependency.

Checks if the connection has valid authentication credentials.

Attaches the authenticated user to the connection state if the credentials are valid.
Connection state is left as is if the credentials are invalid.

:param connection: The HTTP connection.
:param session: The connection's database session.
:return: The updated connection if the credentials are valid.
"""


authentication_required = access_control(
    get_authentication_credentials,
    check_authentication_credentials,
    status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
    message="Missing or invalid authentication credentials!",
)
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
