import fastapi
import typing
from helpers.fastapi.dependencies.access_control import request_access_control
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.dependencies.requests import _DBSession, RequestDBSession
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
    request: fastapi.Request, session: _DBSession
):
    client = getattr(request.state, "client", None)
    if not isinstance(client, APIClient):
        return False

    if client.client_type == APIClient.ClientType.USER:
        user = client.account

    else:
        session = session or next(get_async_session())
        auth_header = request.headers.get(AUTHENTICATION_HEADER)
        if not auth_header:
            return False

        if not auth_header.startswith(AUTH_TOKEN_PREFIX):
            return False

        auth_token = auth_header.split(" ")[-1]
        user = await _get_user_from_auth_token(auth_token, session)
        if not user:
            return False

    request.state.user = user
    return True


@Dependency
# Override the regular `request_access_control` dependency factory, such that
# the authentication credential check is only done on authorized clients
async def authentication_required(
    request: AuthorizedAPIClient, session: RequestDBSession
):
    """
    Request dependency.

    Checks if the request has valid authentication credentials.
    Attaches the user object to the request state if the credentials are valid.
    """
    _depends = request_access_control(
        check_authentication_credentials,
        status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
        message="Missing or invalid authentication credentials!",
    )
    return await _depends.dependency(request, session)


# Used Union[Any, fastapi.Request] to allow for the Annotated dependency type
# to be used in place of the regular request dependency, without fastapi complaining
AuthenticationRequired = typing.Annotated[
    typing.Union[typing.Any, fastapi.Request], authentication_required
]
"""Annotated dependency type that checks if the request has valid authentication credentials."""


__all__ = [
    "authentication_required",
    "AuthenticationRequired",
]
