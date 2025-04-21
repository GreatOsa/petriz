import typing
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from helpers.fastapi.utils import timezone

from .models import Account


async def check_account_name_exists(session: AsyncSession, name: str) -> bool:
    """Check if an account with the given name exists."""
    exists = await session.execute(
        sa.select(
            sa.exists().where(
                Account.name == name,
                ~Account.is_deleted,
            )
        )
    )
    return exists.scalar_one()


async def check_account_exists(session: AsyncSession, email: str) -> bool:
    """Check if an account with the given email exists."""
    exists = await session.execute(
        sa.select(
            sa.exists().where(
                Account.email == email,
                ~Account.is_deleted,
            )
        )
    )
    return exists.scalar_one()


async def create_account(
    session: AsyncSession, email: str, name: str, password: str
) -> Account:
    """Create a new account."""
    account = Account(email=email, name=name)  # type: ignore
    account.set_password(password)
    session.add(account)
    return account


async def retrieve_account_by_email(
    session: AsyncSession, email: str
) -> typing.Optional[Account]:
    """Retrieve an account by email"""
    result = await session.execute(
        sa.select(Account).where(
            Account.email == email,
            ~Account.is_deleted,
        )
    )
    return result.scalar()


async def delete_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    deleted_by_id: typing.Optional[uuid.UUID] = None,
) -> typing.Optional[Account]:
    """Soft delete an account by ID."""
    result = await session.execute(
        sa.select(Account).where(
            Account.id == account_id,
            ~Account.is_deleted,
        ).with_for_update(nowait=True)
    )
    account = result.scalar()
    if not account:
        return

    account.is_deleted = True
    account.is_active = False
    account.deleted_at = timezone.now()
    account.deleted_by_id = deleted_by_id
    session.add(account)
    return account


__all__ = [
    "check_account_exists",
    "create_account",
    "retrieve_account_by_email",
]
