import sys
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

    async with get_async_session() as session:
        api_client = await crud.create_api_client(
            session=session,
            client_type=crud.APIClient.ClientType.INTERNAL,
        )
        await session.commit()
        api_key = await crud.create_api_key(
            session=session, client=api_client, valid_until=valid_until
        )
        await session.commit()

    sys.stdout.write(f"API Client ID: {api_client.uid}\n")
    sys.stdout.write(f"API Client Secret: {api_key.secret}\n")
