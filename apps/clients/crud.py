import datetime
import uuid
import faker
import typing
import fastapi.exceptions
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from helpers.fastapi.requests.query import OrderingExpressions
from helpers.fastapi.utils import timezone
from helpers.fastapi.sqlalchemy.utils import build_conditions

from .models import APIClient, ClientType, APIKey
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
    account_id: typing.Optional[uuid.UUID] = None,
) -> bool:
    """Check if a client name exists already."""
    filters = [APIClient.name == name, ~APIClient.is_deleted]
    if account_id:
        filters.append(APIClient.account_id == account_id)
    exists = await session.execute(sa.select(sa.exists().where(*filters)))
    return exists.scalar_one()


async def check_account_can_create_more_clients(
    session: AsyncSession, account_id: uuid.UUID
):
    client_count = await session.execute(
        sa.select(sa.func.count()).where(
            APIClient.account_id == account_id,
            ~APIClient.is_deleted,
        )
    )
    return client_count.scalar_one() < Account.MAX_CLIENT_COUNT


async def create_api_client(
    session: AsyncSession,
    account_id: typing.Optional[uuid.UUID] = None,
    name: typing.Optional[str] = None,
    **kwargs,
):
    name = name or generate_api_client_name()
    if await check_api_client_name_exists(session, name, account_id):
        raise fastapi.exceptions.ValidationException(
            errors=[
                "Client with this name already exists!",
            ]
        )

    if account_id:
        kwargs["client_type"] = ClientType.USER

    api_client = APIClient(
        name=name,  # type: ignore
        account_id=account_id,  # type: ignore
        **kwargs,
    )
    session.add(api_client)
    return api_client


async def retrieve_api_client(
    session: AsyncSession, for_update: bool = False, **filters
) -> typing.Optional[APIClient]:
    """
    Retrieve the first API client that matches the given filter from the DB.
    Eagerly load the associated api key and account (if any).
    """
    query = sa.select(APIClient).where(
        ~APIClient.is_deleted,
        *build_conditions(filters, APIClient),
    )
    if for_update:
        query = query.with_for_update(nowait=True, read=True)

    result = await session.execute(
        query.options(
            joinedload(APIClient.api_key),
            joinedload(APIClient.account),
        )
    )
    return result.scalar()


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
        .where(~APIClient.is_deleted, *build_conditions(filters, APIClient))
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
        sa.select(APIClient).where(
            ~APIClient.is_deleted,
            APIClient.uid.in_(uids),
            *build_conditions(filters, APIClient),
        )
    )
    return list(result.scalars().all())


async def delete_api_client(
    session: AsyncSession,
    uid: str,
    deleted_by_id: typing.Optional[uuid.UUID] = None,
    **filters,
) -> typing.Optional[APIClient]:
    """
    Soft delete an API client. This will also disable the client.

    :param session: The database session to use.
    :param uid: The UID of the API client to delete.
    :param deleted_by_id: The ID of the user who deleted the client.
    :param filters: Additional filters to apply when retrieving the client.
    :return: The deleted API client, or None if no client was found.
    """
    result = await session.execute(
        sa.update(APIClient)
        .where(
            APIClient.uid == uid,
            ~APIClient.is_deleted,
            *build_conditions(filters, APIClient),
        )
        .values(
            is_deleted=True,
            deleted_by_id=deleted_by_id,
            deleted_at=timezone.now(),
        )
        .returning(APIClient)
    )
    return result.scalar()


async def bulk_delete_api_clients_by_uid(
    session: AsyncSession,
    uids: typing.Sequence[str],
    deleted_by_id: typing.Optional[uuid.UUID] = None,
    **filters,
) -> int:
    """
    Soft delete API clients in bulk. This will also disable the clients.

    :param session: The database session to use.
    :param uids: The UIDs of the API clients to delete.
    :param deleted_by_id: The ID of the user who deleted the clients.
    :param filters: Additional filters to apply when retrieving the clients.
    :return: The number of clients that were deleted.
    """
    result = await session.execute(
        sa.update(APIClient)
        .where(
            APIClient.uid.in_(uids),
            ~APIClient.is_deleted,
            *build_conditions(filters, APIClient),
        )
        .values(
            is_deleted=True,
            is_disabled=True,
            deleted_by_id=deleted_by_id,
            deleted_at=timezone.now(),
        ).returning(sa.func.count(APIClient.id))
    )
    return result.scalar_one()


############
# API KEYS #
############


async def check_api_key_for_client_exists(
    session: AsyncSession, client_id: uuid.UUID
) -> bool:
    """Check if an api key exists for a client."""
    exists = await session.execute(
        sa.select(
            sa.exists().where(
                APIKey.client_id == client_id,
            )
        )
    )
    return exists.scalar_one()


async def create_api_key(
    session: AsyncSession,
    client_id: uuid.UUID,
    valid_until: typing.Optional[datetime.datetime] = None,
) -> APIKey:
    """Create a new api key for the API client."""
    api_key = APIKey(
        client_id=client_id,  # type: ignore
        valid_until=valid_until,  # type: ignore
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
