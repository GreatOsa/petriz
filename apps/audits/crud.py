import typing
import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLogEntry


async def create_audit_log_entry(
    session: AsyncSession,
    **create_kwargs,
) -> AuditLogEntry:
    """Create an audit log entry."""
    audit_log_entry = AuditLogEntry(**create_kwargs)
    session.add(audit_log_entry)
    return audit_log_entry


async def retrieve_audit_log_entry_by_uid(
    session: AsyncSession, uid: str
) -> typing.Optional[AuditLogEntry]:
    """Retrieve an audit log entry by its UID."""
    result = await session.execute(sa.select(AuditLogEntry).filter_by(uid=uid))
    return result.scalars().first()


async def retrieve_audit_log_entries(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    ordering: typing.List[
        sa.UnaryExpression[AuditLogEntry]
    ] = AuditLogEntry.DEFAULT_ORDERING,
    timestamp_gte: typing.Optional[datetime.datetime] = None,
    timestamp_lte: typing.Optional[datetime.datetime] = None,
    **filters,
) -> typing.List[AuditLogEntry]:
    """
    Retrieve audit log entries.

    :param session: The database session.
    :param limit: The maximum number of entries to retrieve.
    :param offset: The number of entries to skip.
    :param filters: Filters to apply to the query.
    """
    timestamp_filters = []
    if timestamp_gte:
        timestamp_filters.append(AuditLogEntry.created_at >= timestamp_gte)
    if timestamp_lte:
        timestamp_filters.append(AuditLogEntry.created_at <= timestamp_lte)

    result = await session.execute(
        sa.select(AuditLogEntry)
        .where(*timestamp_filters)
        .filter_by(**filters)
        .order_by(*ordering)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
