from typing import Any, Hashable, Mapping, Union, Optional
import random
import fastapi
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from helpers.fastapi.models.users import AbstractBaseUser
from helpers.fastapi.config import settings
from helpers.generics.utils.totp import random_hex
from helpers.fastapi.utils.requests import get_ip_address

from .models import ConnectionIdentifierRelatedTOTP, AccountRelatedTOTP


async def get_totp_by_identifier(
    identifier: str, session: AsyncSession
) -> Optional[ConnectionIdentifierRelatedTOTP]:
    """
    Get the latest Time-based OTP for the identifier.

    :param identifier: The identifier of the OTP token.
    :param session: The database session to use.
    :return: The latest Time-based OTP for the identifier, if any.
    """
    query = select(ConnectionIdentifierRelatedTOTP).where(
        ConnectionIdentifierRelatedTOTP.identifier == identifier
    )
    result = await session.execute(query)
    return result.scalars().first()


async def get_totp_by_owner(
    owner: AbstractBaseUser, session: AsyncSession
) -> Optional[AccountRelatedTOTP]:
    """
    Get the latest Time-based OTP for the owner.

    :param owner: The owner of the OTP token.
    :param session: The database session to use.
    :return: The latest Time-based OTP for the owner, if any.
    """
    query = select(AccountRelatedTOTP).where(AccountRelatedTOTP.account_id == owner.id)
    result = await session.execute(query)
    return result.scalars().first()


async def generate_totp_for_identifier(
    identifier: str,
    *,
    length: int = settings.OTP_LENGTH,
    validity_period: int = settings.OTP_VALIDITY_PERIOD,
    request: Optional[fastapi.Request] = None,
    session: AsyncSession,
) -> ConnectionIdentifierRelatedTOTP:
    """
    Generate a Time-based OTP for the identifier.

    :param identifier: The identifier for which the OTP is to be generated.
    :param length: The length of the OTP token.
    :param validity_period: The validity period of the OTP token.
    :param request: The request object affiliated with token generation.
    :param session: The database session to use.
    :return: The OTP token generated.
    """
    async with session.begin_nested():
        existing_totp = await get_totp_by_identifier(identifier, session=session)
        if existing_totp:
            await session.delete(existing_totp)

        new_totp = ConnectionIdentifierRelatedTOTP(
            identifier=identifier,
            length=length,
            validity_period=validity_period,
            requestor_ip_address=get_ip_address(request) if request else None,
        )
        session.add(new_totp)

    return new_totp


async def verify_identifier_totp_token(
    token: str,
    identifier: str,
    *,
    request: Optional[fastapi.Request] = None,
    delete_on_verification: bool = True,
    session: AsyncSession,
) -> bool:
    """
    Verify the Time-based OTP token for the identifier.

    :param token: The token to verify.
    :param identifier: The identifier for which the token is to be verified.
    :param request: The request object affiliated with token verification.
    :param delete_on_verification: Whether to delete the OTP once verified.
    :param session: The database session to use.
    :return: True if the token is verified, False otherwise.
    """
    totp = await get_totp_by_identifier(identifier, session=session)
    valid = totp and totp.verify_token(token, request=request)
    if not valid:
        return False

    if delete_on_verification:
        async with session.begin_nested():
            await session.delete(totp)
        return True

    # Save the last verified counter
    session.add(totp)
    return True


async def generate_totp_for_user(
    user: AbstractBaseUser,
    *,
    length: int = settings.OTP_LENGTH,
    validity_period: int = settings.OTP_VALIDITY_PERIOD,
    request: Optional[fastapi.Request] = None,
    session: AsyncSession,
) -> AccountRelatedTOTP:
    """
    Generate a Time-based OTP for the user.

    :param user: The user for which the OTP is to be generated.
    :param length: The length of the OTP token.
    :param validity_period: The validity period of the OTP token.
    :param request: The request object affiliated with token generation.
    :param session: The database session to use.
    :return: The OTP token generated.
    """
    async with session.begin_nested():
        existing_totp = await get_totp_by_owner(user, session=session)
        if existing_totp:
            await session.delete(existing_totp)

        totp = AccountRelatedTOTP(
            account_id=user.id,
            length=length,
            validity_period=validity_period,
            requestor_ip_address=get_ip_address(request) if request else None,
        )
        session.add(totp)
    return totp


async def verify_user_totp_token(
    token: str,
    user: AbstractBaseUser,
    *,
    request: Optional[fastapi.Request] = None,
    delete_on_verification: bool = True,
    session: AsyncSession,
) -> bool:
    """
    Verify the Time-based OTP token for the user.

    :param token: The token to verify.
    :param user: The user for which the token is to be verified.
    :param request: The request object affiliated with token verification.
    :param delete_on_verification: Whether to delete the OTP once verified.
    :param session: The database session to use.
    :return: True if the token is verified, False otherwise.
    """
    totp = await get_totp_by_owner(user, session=session)
    valid = totp and totp.verify_token(token, request=request)
    if not valid:
        return False

    if delete_on_verification:
        async with session.begin_nested():
            await session.delete(totp)
        return True
    
    # Save the last verified counter
    session.add(totp)
    return True


async def verify_totp_token(
    token: str,
    on_behalf_of: Union[AbstractBaseUser, str, Any],
    *,
    request: Optional[fastapi.Request] = None,
    delete_on_verification: bool = True,
    session: AsyncSession,
) -> bool:
    """
    Verify the Time based OTP token for the user or identifier.

    :param token: The token to verify.
    :param on_behalf_of: The user or identifier for which the token is to be verified.
    :param request: The request object affiliated with token generation, for verification.
    :param delete_on_verification: Whether to delete once verified.
    :param session: The database session to use.
    :return: True if the token is verified, False otherwise.
    """
    if isinstance(on_behalf_of, AbstractBaseUser):
        return await verify_user_totp_token(
            token,
            on_behalf_of,
            request=request,
            delete_on_verification=delete_on_verification,
            session=session,
        )
    return await verify_identifier_totp_token(
        token,
        on_behalf_of,
        request=request,
        delete_on_verification=delete_on_verification,
        session=session,
    )


def dummy_verify_totp_token(**kwargs) -> bool:
    """Dummy version of the `verify_totp_token` function"""
    token = kwargs.get("token")
    return token == ("0" * settings.OTP_LENGTH)


async def exchange_data_for_token(
    data: Mapping[Hashable, Any],
    *,
    expires_after: int = 5 * 60,
    request: Optional[fastapi.Request] = None,
    session: AsyncSession,
) -> str:
    """
    Exchange the data for an access token.

    The access token returned can be used to retrieve the data later.

    :param data: The data to exchange for the access token.
    :param expires_after: The validity period of the access token.
    :param request: The request object affiliated with data-to-token exchange, for verification.
    :param session: The database session to use.
    :return: The data access token.
    """
    identifier = random_hex(length=16)
    totp_length = random.randint(6, 12)
    totp = await generate_totp_for_identifier(
        identifier,
        length=totp_length,
        validity_period=expires_after,
        request=request,
        session=session,
    )
    totp.extradata = data
    session.add(totp)
    return ".".join((identifier, totp.token(), totp.key))


class InvalidToken(ValueError):
    pass


async def exchange_token_for_data(
    access_token: str,
    *,
    request: Optional[fastapi.Request] = None,
    delete_on_success: bool = True,
    session: AsyncSession,
) -> Optional[Mapping[Hashable, Any]]:
    """
    Exchange the access token for the associated data.

    :param access_token: The access token to exchange for the data.
    :param request: The request object affiliated with token-to-data exchange, for verification.
    :param delete_on_success: Whether to delete the token on successful retrieval.
    :param session: The database session to use.
    :return: The data associated with the access token.
    :raises InvalidToken: If the access token is invalid.
    """
    try:
        identifier, token, _ = access_token.split(".")
    except ValueError:
        raise InvalidToken("Invalid access token")

    valid = await verify_identifier_totp_token(
        token,
        identifier,
        request=request,
        delete_on_verification=False,
        session=session,
    )
    if not valid:
        raise InvalidToken("Invalid access token")

    totp = await get_totp_by_identifier(identifier, session=session)
    if delete_on_success:
        async with session.begin_nested():
            await session.delete(totp)

    return dict(totp.extradata)
