import datetime
import faker
import typing
import fastapi.exceptions
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .models import (
    APIClient,
    APIKey,
    generate_api_key_secret,
)
from apps.accounts.models import Account

fake = faker.Faker("en-us")


###############
# API CLIENTS #
###############


def generate_api_client_name() -> str:
    words = fake.words(nb=6, unique=True)
    return "-".join(words[:4])


async def check_api_client_name_exists_for_account(
    session: AsyncSession, account_id: str, name: str
) -> bool:
    """Check if a client name exists for an account."""
    exists = await session.execute(
        sa.select(
            sa.exists().where(
                APIClient.name == name,
                APIClient.account_id == account_id,
                ~APIClient.is_deleted,
            )
        )
    )
    return exists.scalar()


async def check_account_can_create_more_clients(
    session: AsyncSession, account: Account
):
    client_count = await session.execute(
        sa.select(sa.func.count()).where(
            APIClient.account_id == account.id,
            ~APIClient.is_deleted,
        )
    )
    return client_count.scalar() < Account.MAX_CLIENT_COUNT


async def create_api_client(
    session: AsyncSession,
    account_id: typing.Optional[str] = None,
    name: typing.Optional[str] = None,
    **kwargs,
):
    name = name or generate_api_client_name()
    if name and account_id:
        if await check_api_client_name_exists_for_account(session, account_id, name):
            raise fastapi.exceptions.ValidationException(
                errors=[
                    "Client with this name already exists for account.",
                ]
            )

    if account_id:
        kwargs["client_type"] = APIClient.ClientType.USER

    api_client = APIClient(
        name=name,
        account_id=account_id,
        **kwargs,
    )
    session.add(api_client)
    return api_client


async def retrieve_api_client(
    session: AsyncSession, **filters
) -> typing.Optional[APIClient]:
    """
    Retrieve the first API client that matches the given filter from the DB.
    Eagerly load the associated api key and account (if any).
    """
    result = await session.execute(
        sa.select(APIClient)
        .filter_by(
            is_deleted=False,
            **filters,
        )
        .options(joinedload(APIClient.api_key), joinedload(APIClient.account))
    )
    return result.scalar_one_or_none()


async def retrieve_api_clients(
    session: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
    **filters,
):
    result = await session.execute(
        sa.select(APIClient)
        .filter_by(is_deleted=False, **filters)
        .limit(limit)
        .offset(offset)
        .options(joinedload(APIClient.api_key), joinedload(APIClient.account))
    )
    return result.scalars().all()


async def retrieve_api_clients_by_uid(
    session: AsyncSession, uids: typing.List[str], **filters
):
    result = await session.execute(
        sa.select(APIClient)
        .where(
            ~APIClient.is_deleted,
            APIClient.id.in_(uids),
        )
        .filter_by(**filters)
    )
    return result.scalars().all()


async def delete_api_client(session: AsyncSession, api_client: APIClient):
    """
    Delete an API client. This will also disable the client and its associated api key.
    """
    api_client.is_deleted = True
    api_client.disabled = True
    if api_client.api_key:
        api_client.api_key.active = False
        await session.add(api_client.api_key)

    await session.add(api_client)
    return None


async def delete_api_clients_by_uid(
    session: AsyncSession, uids: typing.List[str], **filters
):
    result = await session.execute(
        sa.delete(APIClient).where(APIClient.id.in_(uids)).filter_by(**filters)
    )
    return result.scalar()


############
# API KEYS #
############


async def check_api_key_for_client_exists(
    session: AsyncSession, client: APIClient
) -> bool:
    """Check if an api key exists for a client."""
    exists = await session.execute(
        sa.select(
            sa.exists().where(
                APIKey.client_id == client.id,
            )
        )
    )
    return exists


async def create_api_key(
    session: AsyncSession,
    client: APIClient,
    valid_until: typing.Optional[datetime.datetime] = None,
) -> APIKey:
    """Create a new api key for the API client."""
    api_key = APIKey(
        client_id=client.id,
        valid_until=valid_until,
    )
    session.add(api_key)
    return api_key


async def retrieve_api_key_by_secret(
    session: AsyncSession, secret: str
) -> typing.Optional[APIKey]:
    """Retrieve an api key by its secret. Eagerly load the associated client."""
    result = await session.execute(
        sa.select(APIKey)
        .where(
            APIKey.secret == secret,
        )
        .options(joinedload(APIKey.client))
    )
    return result.scalar_one_or_none()


async def refresh_api_key_secret(session: AsyncSession, api_key: APIKey):
    api_key.secret = generate_api_key_secret()
    session.add(api_key)
    return api_key


__all__ = [
    "create_api_client",
    "retrieve_api_client",
    "retrieve_api_clients",
    "check_api_key_for_client_exists",
    "create_api_key",
    "retrieve_api_key_by_secret",
]
