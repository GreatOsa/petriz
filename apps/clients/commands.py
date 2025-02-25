import sys
import typing
import datetime
from core import commands

from helpers.fastapi.utils import timezone
from helpers.fastapi.sqlalchemy.setup import get_async_session
from . import crud
from .models import APIClient
from .permissions import DEFAULT_PERMISSIONS_SETS


AVAILABLE_CLIENT_TYPES = ["internal", "public", "partner"]


@commands.register
async def create_client(
    client_type: str,
    secret_validity_period: typing.Optional[int] = None,
):
    """
    Create an API Client with the specified client type.

    :param client_type: The client type. Available options: internal, public, partner.
    :param secret_validity_period: The client secret validity period in seconds.
    """
    client_type = client_type.strip().lower()
    if client_type not in AVAILABLE_CLIENT_TYPES:
        sys.stdout.write(
            f"Invalid client type. Available options: {', '.join(AVAILABLE_CLIENT_TYPES)}\n"
        )
        return

    client_type = APIClient.ClientType(client_type)
    if secret_validity_period:
        valid_until = timezone.now() + datetime.timedelta(
            seconds=float(secret_validity_period)
        )
    else:
        valid_until = None

    async with get_async_session() as session:
        api_client = await crud.create_api_client(
            session=session,
            client_type=client_type.value,
            permissions=DEFAULT_PERMISSIONS_SETS[client_type.value],
        )
        await session.flush()
        api_key = await crud.create_api_key(
            session=session, client=api_client, valid_until=valid_until
        )
        await session.commit()

    sys.stdout.write("############################################\n")
    sys.stdout.write(f"{client_type.value.upper()} API Client ID: {api_client.uid}\n")
    sys.stdout.write(
        f"{client_type.value.upper()} API Client Secret: {api_key.secret}\n"
    )
    sys.stdout.write("############################################\n")
    sys.stdout.write("\n")


@commands.register
async def backfill_client_permissions():
    """
    Backfill permissions for API Clients whose permissions have not been modified yet.

    This command is useful when new permissions are added to the system and we need to
    update the permissions for all API Clients that have not been modified yet.
    """
    count = 0
    async with get_async_session() as session:
        # Retrieve all API Clients whose permissions have not been modified yet
        api_clients = await crud.retrieve_api_clients(
            session=session, permissions_modified_at=None
        )
        for api_client in api_clients:
            permissions = DEFAULT_PERMISSIONS_SETS.get(
                api_client.client_type.lower(), None
            )
            if permissions:
                if api_client.permissions:
                    permissions = set(api_client.permissions).union(permissions)

                api_client.permissions = permissions
                session.add(api_client)
                await session.flush()
                count += 1
        await session.commit()

    sys.stdout.write("Successfully backfilled permissions for API Clients.\n")
    sys.stdout.write(f"Total API Clients updated: {count}\n")
    sys.stdout.write("\n")
