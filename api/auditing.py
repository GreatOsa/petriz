import typing
import sys
from starlette.requests import HTTPConnection

from helpers.fastapi.utils.requests import get_ip_address
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.auditing.dependencies import ConnectionEvent
from helpers.fastapi.auditing.middleware import (
    ResponseStatus,
    timed_batched_logger_factory,
)
from helpers.fastapi.config import settings
from helpers.generics.utils.caching import ThreadSafeLRUCache
from apps.accounts.models import Account
from apps.clients.models import APIClient
from apps.audits.schemas import AuditLogEntryCreateSchema
from apps.audits.models import ActionStatus, AuditLogEntry
from .caching import redis


async def get_api_client_from_connection(
    connection: HTTPConnection,
) -> typing.Optional[APIClient]:
    """Get the API client from the connection."""
    api_client = getattr(connection.state, "client", None)
    if not isinstance(api_client, APIClient):
        return None
    return api_client


async def get_account_from_connection(
    connection: HTTPConnection,
) -> typing.Optional[Account]:
    """Get the account information from the connection."""
    account = getattr(connection.state, "user", None)
    if not isinstance(account, Account):
        return None
    return account


async def build_audit_log_entries(
    connection: HTTPConnection,
    connection_events: typing.Sequence[ConnectionEvent],
    status: ResponseStatus,
    metadata: typing.MutableMapping[str, typing.Any],
) -> typing.Sequence[typing.Dict[str, typing.Any]]:
    """
    Build audit log entries from connection events and metadata.

    :param connection_events: The connection events to log.
    :param metadata: The metadata to log.
    :param status: The status of the connection.
    :param connection: The HTTP connection object.
    :return: A list of audit log entries.
    """
    user_agent = connection.headers.get("user-agent")
    ip_address = get_ip_address(connection)
    api_client = await get_api_client_from_connection(connection)
    account = await get_account_from_connection(connection)
    entries = [
        AuditLogEntryCreateSchema(
            event=connection_event["event"],
            user_agent=user_agent,
            ip_address=ip_address,  # type: ignore
            actor_uid=api_client.uid if api_client else None,
            actor_type="api_client" if api_client else None,
            account_email=account.email if account else None,
            account_uid=account.uid if account else None,
            target=connection_event["target"],
            target_uid=connection_event["target_uid"],
            description=connection_event["description"],
            status=ActionStatus.SUCCESS
            if status == ResponseStatus.OK
            else ActionStatus.ERROR,
            metadata=dict(metadata),
        ).model_dump(mode="json")
        for connection_event in connection_events
    ]
    return entries


redis_cached_logger = timed_batched_logger_factory(
    db_session_factory=get_async_session,
    db_table_mapper=AuditLogEntry,  # type: ignore
    cache=redis,  # type: ignore
    cache_key="connection_events_logs",
    batch_size=settings.AUDIT_LOGGING_BATCH_SIZE,
    interval=settings.AUDIT_LOGGING_INTERVAL,
)


class _InMemoryCache:
    def __init__(
        self,
        maxsize: int,
        getsizeof: typing.Optional[typing.Callable[[typing.Any], int]] = None,
    ):
        self._cache = ThreadSafeLRUCache(maxsize, getsizeof)
        self._cache.clear()

    def __contains__(self, key: typing.Hashable) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> typing.Iterator[typing.Hashable]:
        return iter(self._cache)

    async def get(self, key: typing.Hashable) -> typing.Any:
        if key not in self._cache:
            return None
        return self._cache[key]

    async def set(self, key: typing.Hashable, value: typing.Any):
        self._cache[key] = value

    async def delete(self, key: typing.Hashable):
        if key not in self:
            return
        del self._cache[key]


in_memory_cache = _InMemoryCache(
    maxsize=1024 * 1024 * 1024,  # 1 GB
    getsizeof=sys.getsizeof,
)

in_memory_cached_logger = timed_batched_logger_factory(
    db_session_factory=get_async_session,
    db_table_mapper=AuditLogEntry,  # type: ignore
    cache=in_memory_cache,
    cache_key="connection_events_logs",
    batch_size=settings.AUDIT_LOGGING_BATCH_SIZE,
    interval=settings.AUDIT_LOGGING_INTERVAL,
)
