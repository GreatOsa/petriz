import functools
import typing
from starlette.requests import HTTPConnection

from helpers.fastapi.requests.throttling import NoLimit, throttle
from apps.clients.models import APIClient


async def client_identifier(connection: HTTPConnection):
    client: typing.Optional[APIClient] = getattr(connection.state, "client", None)
    if not client:
        raise NoLimit()
    return f"client:authorized:{client.uid}:{connection.scope['path']}"


def anonymous_client_identifier(connection: HTTPConnection):
    client: typing.Optional[APIClient] = getattr(connection.state, "client", None)
    if client:
        raise NoLimit()
    return f"client:anonymous:{connection.scope['path']}"


async def internal_client_identifier(connection: HTTPConnection):
    client: typing.Optional[APIClient] = getattr(connection.state, "client", None)
    if not client or client.client_type != APIClient.ClientType.INTERNAL:
        raise NoLimit()
    return f"client:internal:{client.uid}:{connection.scope['path']}"


async def user_client_identifier(connection: HTTPConnection):
    client: typing.Optional[APIClient] = getattr(connection.state, "client", None)
    if not client or client.client_type != APIClient.ClientType.USER:
        raise NoLimit()
    return f"client:user:{client.uid}:{connection.scope['path']}"


async def partner_client_identifier(connection: HTTPConnection):
    client: typing.Optional[APIClient] = getattr(connection.state, "client", None)
    if not client or client.client_type != APIClient.ClientType.PARTNER:
        raise NoLimit()
    return f"client:partner:{client.uid}:{connection.scope['path']}"


client_throttle = functools.partial(throttle, identifier=client_identifier)
"""Generic throttle for all authorized API clients"""

anonymous_client_throttle = functools.partial(
    throttle, identifier=anonymous_client_identifier
)
"""Throttle for anonymous API clients"""

internal_client_throttle = functools.partial(
    throttle, identifier=internal_client_identifier
)
"""Throttle for `internal` type authorized API clients"""

user_client_throttle = functools.partial(throttle, identifier=user_client_identifier)
"""Throttle for `user` type authorized API clients"""

partner_client_throttle = functools.partial(
    throttle, identifier=partner_client_identifier
)
"""Throttle for `partner` type authorized API clients"""


# Generic client throttling
client_burst = client_throttle(limit=200_000, hours=1)
client_surge = client_throttle(limit=10_000, minutes=1)
client_sustained = client_throttle(limit=2000, seconds=1)

# Anonymous client throttling
anonymous_client_burst = anonymous_client_throttle(limit=100, minutes=1)
anonymous_client_surge = anonymous_client_throttle(limit=10, seconds=5)
anonymous_client_sustained = anonymous_client_throttle(limit=3, seconds=5)

# Internal client throttling
internal_client_burst = internal_client_throttle(limit=500_000, hours=1)
internal_client_surge = internal_client_throttle(limit=50_000, minutes=1)
internal_client_sustained = internal_client_throttle(limit=5000, seconds=1)

# User client throttling
user_client_burst = user_client_throttle(limit=100_000, hours=1)
user_client_surge = user_client_throttle(limit=5000, minutes=1)
user_client_sustained = user_client_throttle(limit=1000, seconds=1)

# Partner client throttling
partner_client_burst = partner_client_throttle(limit=300_000, hours=1)
partner_client_surge = partner_client_throttle(limit=20_000, minutes=1)
partner_client_sustained = partner_client_throttle(limit=3000, seconds=1)


ANONYMOUS_CLIENT_THROTTLES = (
    anonymous_client_burst,
    anonymous_client_surge,
    anonymous_client_sustained,
)

AUTHORIZED_CLIENT_THROTTLES = (
    client_burst,
    client_surge,
    client_sustained,
)

INTERNAL_CLIENT_THROTTLES = (
    internal_client_burst,
    internal_client_surge,
    internal_client_sustained,
)

USER_CLIENT_THROTTLES = (
    user_client_burst,
    user_client_surge,
    user_client_sustained,
)

PARTNER_CLIENT_THROTTLES = (
    partner_client_burst,
    partner_client_surge,
    partner_client_sustained,
)
