import typing
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from .models import Account, generate_account_uid


async def check_account_exists(session: AsyncSession, email: str) -> bool:
    """Check if an account with the given email exists."""
    exists = await session.execute(sa.select(sa.exists().where(Account.email == email)))
    return exists.scalar()


async def create_account(session: AsyncSession, email: str, password: str) -> Account:
    """Create a new account."""
    while True:
        uid = generate_account_uid()
        exists = await session.execute(sa.select(sa.exists().where(Account.uid == uid)))
        if not exists.scalar():
            break

    account = Account(uid=uid, email=email)
    account.set_password(password)
    session.add(account)
    return account


async def retrieve_account_by_email(session: AsyncSession, email: str) -> typing.Optional[Account]:
    result = await session.execute(
        sa.select(Account).where(Account.email == email)
    )
    return result.scalar()


__all__ = [
    "check_account_exists",
    "create_account",
    "retrieve_account_by_email",
]
