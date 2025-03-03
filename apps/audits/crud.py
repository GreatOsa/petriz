import typing
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLogEntry, ActionStatus


async def create_audit_log_entry(
    session: AsyncSession,
    event: str,
    source: str,
    actor_id: str,
    actor_type: str,
    account_email: typing.Optional[str] = None,
    account_id: typing.Optional[uuid.UUID] = None,
    target: typing.Optional[str] = None,
    target_id: typing.Optional[str] = None,
    description: typing.Optional[str] = None,
    status: typing.Optional[ActionStatus] = None,
    metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
) -> AuditLogEntry:
    """Create an audit log entry."""
    audit_log_entry = AuditLogEntry(
        event=event,
        source=source,
        actor_id=actor_id,
        actor_type=actor_type,
        account_email=account_email,
        account_id=account_id,
        target=target,
        target_id=target_id,
        description=description,
        status=status,
        data=metadata,
    )
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
    **filters,
) -> typing.List[AuditLogEntry]:
    """
    Retrieve audit log entries.
    
    :param session: The database session.
    :param limit: The maximum number of entries to retrieve.
    :param offset: The number of entries to skip.
    :param filters: Filters to apply to the query.
    """
    result = await session.execute(
        sa.select(AuditLogEntry)
        .filter_by(**filters)
        .order_by(AuditLogEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
