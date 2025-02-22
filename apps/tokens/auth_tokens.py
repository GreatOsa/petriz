import typing
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from sqlalchemy.orm import joinedload

from apps.accounts.models import Account
from .models import AuthToken


async def check_auth_token_for_account_exists(
    session: AsyncSession, account: Account
) -> bool:
    """Check if an auth token exists for the account."""
    exists = await session.execute(
        sa.select(sa.exists().where(AuthToken.account_id == account.id))
    )
    return exists.scalar()


async def create_auth_token(session: AsyncSession, account: Account) -> AuthToken:
    """Create a new auth token for an account."""
    auth_token = AuthToken(account_id=account.id)
    session.add(auth_token)
    return auth_token


async def get_or_create_auth_token(session: AsyncSession, account: Account):
    """Get or create an auth token for an account."""
    result = await session.execute(
        sa.select(AuthToken).where(AuthToken.account_id == account.id)
    )

    created = False
    existing_token = result.scalar()
    if not existing_token:
        new_token = await create_auth_token(session=session, account=account)
        created = True
        return new_token, created
    return existing_token, created


async def retrieve_auth_token(
    session: AsyncSession, **filters
) -> typing.Optional[AuthToken]:
    """
    Retrieve an auth token by the given filters.
    """
    result = await session.execute(
        sa.select(AuthToken).where(**filters).options(joinedload(AuthToken.owner))
    )
    return result.scalar()


async def delete_auth_tokens(session: AsyncSession, **filters):
    """Delete auth tokens by the given filters."""
    result = await session.execute(sa.delete(AuthToken).where(**filters))
    return result.scalar()


async def get_auth_token_by_secret(
    session: AsyncSession, secret: str
) -> typing.Optional[AuthToken]:
    """Get an auth token by its secret."""
    result = await session.execute(
        sa.select(AuthToken)
        .where(AuthToken.secret == secret)
        .options(joinedload(AuthToken.owner))
    )
    return result.scalar()
