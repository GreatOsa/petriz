import typing
import datetime
from core import commands

from helpers.fastapi.utils import timezone
from helpers.fastapi.sqlalchemy.setup import get_async_session
from . import crud


@commands.register
async def create_internal_api_client(
    client_secret_validity_period: typing.Optional[int] = None
):
    if client_secret_validity_period:
        valid_until = timezone.now() + datetime.timedelta(
            seconds=float(client_secret_validity_period)
        )
    else:
        valid_until = None

    session = next(get_async_session())
    api_client = await crud.create_api_client(
        session=session,
        client_type=crud.APIClient.ClientType.INTERNAL,
    )
    await session.commit()
    api_key = await crud.create_api_key(
        session=session, client=api_client, valid_until=valid_until
    )
    await session.commit()
    print(f"API Client ID: {api_client.uid}")
    print(f"API Client Secret: {api_key.secret}")
