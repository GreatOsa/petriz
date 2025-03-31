import typing
import click
import datetime

from helpers.fastapi import commands
from helpers.fastapi.utils import timezone
from helpers.fastapi.utils.sync import async_to_sync
from helpers.fastapi.sqlalchemy.setup import get_async_session
from . import crud
from .models import ClientType
from .permissions import ALLOWED_PERMISSIONS_SETS


AVAILABLE_CLIENT_TYPES = ["internal", "public", "partner"]


def _client_type(ctx, param, client_type) -> ClientType:
    """Convert client type string to ClientType"""
    return ClientType(client_type)


@commands.register("create_client")
@click.option(
    "--client-type",
    "-t",
    required=True,
    type=click.Choice(AVAILABLE_CLIENT_TYPES, case_sensitive=False),
    callback=_client_type,
    help="The type of API Client to create",
)
@click.option(
    "--secret-validity-seconds",
    "-s",
    type=float,
    help="The client secret validity period in seconds",
)
@async_to_sync
async def create_client(
    client_type: ClientType,
    secret_validity_seconds: typing.Optional[float] = None,
):
    """Create an API Client with the specified client type."""
    valid_until = (
        timezone.now() + datetime.timedelta(seconds=secret_validity_seconds)
        if secret_validity_seconds
        else None
    )

    async with get_async_session() as session:
        api_client = await crud.create_api_client(
            session=session,
            client_type=client_type.value,
            permissions=ALLOWED_PERMISSIONS_SETS[client_type.value],
        )
        await session.flush()
        api_key = await crud.create_api_key(
            session=session, client=api_client, valid_until=valid_until
        )
        await session.commit()

    click.echo(
        click.style(
            "##############################################################", bold=True, fg="white"
        )
    )
    click.echo(
        click.style(
            f"{client_type.value.upper()} API Client ID: {api_client.uid}",
            bold=True,
            fg="green",
        )
    )
    click.echo(
        click.style(
            f"{client_type.value.upper()} API Client Secret: {api_key.secret}",
            bold=True,
            fg="green",
        )
    )
    click.echo(
        click.style(
            "##############################################################", bold=True, fg="white"
        )
    )


@commands.register("backfill_client_permissions")
@async_to_sync
async def backfill_client_permissions():
    """Backfill permissions for API Clients whose permissions have not been modified."""
    count = 0
    async with get_async_session() as session:
        api_clients = await crud.retrieve_api_clients(
            session=session, permissions_modified_at=None
        )
        for api_client in api_clients:
            permissions = ALLOWED_PERMISSIONS_SETS.get(
                api_client.client_type.lower(), None
            )
            if permissions:
                api_client.permissions = list(permissions)
                session.add(api_client)
                await session.flush()
                count += 1
        await session.commit()

    click.echo(
        click.style("Successfully backfilled permissions for API Clients.", fg="green")
    )
    click.echo(click.style(f"Total API Clients updated: {count}\n", bold=True))


__all__ = ["create_client", "backfill_client_permissions"]
