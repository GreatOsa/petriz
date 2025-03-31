import datetime
import faker
import typing
import fastapi.exceptions
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from helpers.fastapi.requests.query import OrderingExpressions

from .models import (
    APIClient,
    ClientType,
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


async def check_api_client_name_exists(
    session: AsyncSession,
    name: str,
    account: typing.Optional[Account] = None,
) -> bool:
    """Check if a client name exists already."""
    filters = [APIClient.name == name, ~APIClient.is_deleted]
    if account:
        filters.append(APIClient.account_id == account.id)
    exists = await session.execute(sa.select(sa.exists().where(*filters)))
    return exists.scalar_one()


async def check_account_can_create_more_clients(
    session: AsyncSession, account: Account
):
    client_count = await session.execute(
        sa.select(sa.func.count()).where(
            APIClient.account_id == account.id,
            ~APIClient.is_deleted,
        )
    )
    return client_count.scalar_one() < Account.MAX_CLIENT_COUNT


async def create_api_client(
    session: AsyncSession,
    account: typing.Optional[Account] = None,
    name: typing.Optional[str] = None,
    **kwargs,
):
    name = name or generate_api_client_name()
    if await check_api_client_name_exists(session, name, account):
        raise fastapi.exceptions.ValidationException(
            errors=[
                "Client with this name already exists!",
            ]
        )

    if account:
        kwargs["client_type"] = ClientType.USER

    api_client = APIClient(
        name=name, # type: ignore
        account=account, # type: ignore
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
    ordering: OrderingExpressions[APIClient] = APIClient.DEFAULT_ORDERING,
    **filters,
):
    """
    Retrieve all API clients that match the given filter from the DB.
    Eagerly load the associated api key and account (if any).

    :param limit: The maximum number of clients to retrieve.
    :param offset: The number of clients to skip.
    :param ordering: The ordering to use when retrieving clients.
    :param filters: The filters to apply when retrieving clients
    :return: A list of API clients that match the given filters.
    """
    result = await session.execute(
        sa.select(APIClient)
        .filter_by(is_deleted=False, **filters)
        .limit(limit)
        .offset(offset)
        .options(joinedload(APIClient.api_key), joinedload(APIClient.account))
        .order_by(*ordering)
    )
    return list(result.scalars().all())


async def retrieve_api_clients_by_uid(
    session: AsyncSession, uids: typing.List[str], **filters
):
    result = await session.execute(
        sa.select(APIClient)
        .where(
            ~APIClient.is_deleted,
            APIClient.uid.in_(uids),
        )
        .filter_by(**filters)
    )
    return list(result.scalars().all())


async def delete_api_client(session: AsyncSession, api_client: APIClient):
    """
    Delete an API client. This will also disable the client and its associated api key.
    """
    api_client.is_deleted = True
    api_client.disabled = True
    session.add(api_client)
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
    return exists.scalar_one()


async def create_api_key(
    session: AsyncSession,
    client: APIClient,
    valid_until: typing.Optional[datetime.datetime] = None,
) -> APIKey:
    """Create a new api key for the API client."""
    api_key = APIKey(
        client_id=client.id, # type: ignore
        valid_until=valid_until, # type: ignore
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
