import fastapi
from sqlalchemy.exc import OperationalError

from . import schemas
from . import crud
from helpers.fastapi.mailing import send_mail
from helpers.fastapi.dependencies.connections import AsyncDBSession
from helpers.fastapi.dependencies.access_control import ActiveUser
from helpers.fastapi.response import shortcuts as response
from helpers.fastapi.exceptions import capture
from helpers.fastapi.auditing.dependencies import event
from api.dependencies.authorization import (
    internal_api_clients_only,
    permissions_required,
)
from api.dependencies.authentication import authentication_required
from apps.tokens import auth_tokens, totps
from .models import Account

router = fastapi.APIRouter(
    dependencies=[
        event(
            "accounts_access",
            description="Access accounts endpoints.",
        ),
    ]
)


########################
# ACCOUNT REGISTRATION #
########################


@router.post(
    "/registration/initiate",
    tags=["registration"],
    description="Initiate the registration process for a new account.",
    dependencies=[
        event(
            "account_registration_initiation",
            target="account",
            description="Initiate the registration process for a new account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::create"),
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def registration_initiation(
    data: schemas.AccountRegistrationInitiationSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    """
    Initiate the registration process for a new account.
    """
    account_already_exists = await crud.check_account_exists(
        session=session, email=data.email
    )
    if account_already_exists:
        return response.bad_request("An account with this email already exists.")

    totp = await totps.generate_totp_for_identifier(
        identifier=data.email, session=session, request=request
    )
    otp = totp.token()
    await send_mail(
        subject="Registration OTP",
        body=f"Your registration OTP is <b>{otp}</b>. Valid for 30 minutes.",
        recipients=[
            data.email,
        ],
    )

    await session.commit()
    return response.success(
        "Please check your email for an OTP token for email verification."
    )


@router.post(
    "/registration/verify",
    tags=["registration"],
    description="Verify the OTP token for email registration.",
    dependencies=[
        event(
            "account_registration_verification",
            target="account",
            description="Verify the OTP token for email registration.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::create"),
    ],
    response_model=response.DataSchema[
        response.NewSchema(
            "PasswordSetTokenSchema",
            {"password_set_token": str},
        )
    ],
    status_code=200,
)
async def registration_email_verification(
    data: schemas.EmailOTPVerificationSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    account_already_exists = await crud.check_account_exists(
        session=session, email=data.email
    )
    if account_already_exists:
        return response.bad_request("An account with this email already exists.")

    verified = await totps.verify_identifier_totp_token(
        token=data.otp,
        identifier=data.email,
        request=request,
        delete_on_verification=True,
        session=session,
    )
    if not verified:
        return response.bad_request("Invalid OTP token.")

    password_set_token = await totps.exchange_data_for_token(
        data={"email": data.email},
        expires_after=30 * 60,
        session=session,
        request=request,
    )

    await session.commit()
    return response.success(
        message="Email verified. Proceed to set your password. Token expires in 30 minutes.",
        data={"password_set_token": password_set_token},
    )


AuthCompletionSchema = response.NewSchema(
    "AuthCompletionSchema",
    {
        "account": schemas.AccountSchema,
        "auth_token": str,
    },
)


@router.post(
    "/registration/complete",
    tags=["registration"],
    description="Complete the registration process for a new account.",
    dependencies=[
        event(
            "account_registration_completion",
            target="account",
            description="Complete the registration process for a new account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::create"),
    ],
    response_model=response.DataSchema[AuthCompletionSchema],
    status_code=201,
)
async def registration_completion(
    data: schemas.AccountRegistrationCompletionSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    try:
        token_data = await totps.exchange_token_for_data(
            data.password_set_token,
            request=request,
            delete_on_success=True,
            session=session,
        )
    except totps.InvalidToken:
        return response.bad_request("Invalid or expired token.")
    if not token_data:
        return response.bad_request("Invalid or expired token.")

    account_already_exists = await crud.check_account_exists(
        session=session, email=token_data["email"]
    )
    if account_already_exists:
        return response.bad_request("An account with this email already exists.")

    name = data.name
    if not name:
        name = token_data["email"].split("@")[0]
    name_exists = await crud.check_account_name_exists(session=session, name=name)
    if name_exists:
        return response.bad_request(
            f"An account with name {name} already exists. Please provide a different name."
        )

    account = await crud.create_account(
        session=session,
        email=token_data["email"],
        name=name,
        password=data.password.get_secret_value(),
    )
    await session.commit()

    auth_token = await auth_tokens.create_auth_token(
        account=account,
        session=session,
    )
    await session.commit()
    await session.refresh(account)
    await session.refresh(auth_token)
    response_data = {
        "account": schemas.AccountSchema.model_validate(account),
        "auth_token": auth_token.secret,
    }
    return response.created("Account created successfully.", data=response_data)


##########################
# ACCOUNT AUTHENTICATION #
##########################


@router.post(
    "/authentication/initiate",
    tags=["authentication"],
    description="Initiate the authentication process for a new account.",
    dependencies=[
        event(
            "account_authentication_initiation",
            target="account",
            description="Initiate the authentication process for a new account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::authenticate"),
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def authentication_initiation(
    data: schemas.AccountAuthenticationInitiationSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    """
    Initiate the authentication process for a new account.
    """
    account = await crud.retrieve_account_by_email(session=session, email=data.email)
    if not account or not account.check_password(data.password.get_secret_value()):
        return response.bad_request("Invalid authentication credentials.")
    if not account.is_active:
        return response.bad_request("Account deactivated! Contact support.")

    totp = await totps.generate_totp_for_identifier(
        identifier=data.email, session=session, request=request
    )
    otp = totp.token()
    await send_mail(
        subject="Authentication OTP",
        body=f"Your authentication OTP is <b>{otp}</b>. Valid for 30 minutes",
        recipients=[
            data.email,
        ],
    )

    await session.commit()
    return response.success(
        "Please check your email for an OTP token for email verification."
    )


@router.post(
    "/authentication/complete",
    tags=["authentication"],
    description="Verify the OTP token for sent to authenticated account email to receive auth token.",
    dependencies=[
        event(
            "account_authentication_completion",
            target="account",
            description="Verify the OTP token for sent to authenticated account email to receive auth token.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::authenticate"),
    ],
    response_model=response.DataSchema[AuthCompletionSchema],
    status_code=200,
)
async def authentication_completion(
    data: schemas.EmailOTPVerificationSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    verified = await totps.verify_identifier_totp_token(
        token=data.otp,
        identifier=data.email,
        request=request,
        delete_on_verification=True,
        session=session,
    )
    if not verified:
        return response.bad_request("Invalid OTP token.")

    account = await crud.retrieve_account_by_email(session=session, email=data.email)
    if not account:
        return response.bad_request("No account found with this email.")

    auth_token, created = await auth_tokens.get_or_create_auth_token(
        session=session, account=account
    )
    if created:
        await session.commit()
        await session.refresh(auth_token)

    if not auth_token.is_valid:
        await session.delete(auth_token)
        auth_token = await auth_tokens.create_auth_token(
            account=account,
            session=session,
        )
        await session.commit()
        await session.refresh(auth_token)

    response_data = {
        "account": schemas.AccountSchema.model_validate(account),
        "auth_token": auth_token.secret,
    }
    return response.success(
        message="OTP verified successfully. Account authenticated successfully.",
        data=response_data,
    )


##########################
# ACCOUNT PASSWORD RESET #
##########################


@router.post(
    "/password-reset/initiate",
    tags=["password_reset"],
    description="Initiate the password reset process for an account.",
    dependencies=[
        event(
            "account_password_reset_initiation",
            target="account",
            description="Initiate the password reset process for an account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::update"),
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def password_reset_initiation(
    data: schemas.PasswordResetInitiationSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    account_exists = await crud.check_account_exists(session=session, email=data.email)
    if not account_exists:
        return response.bad_request("No account found with this email.")

    totp = await totps.generate_totp_for_identifier(
        identifier=data.email, session=session, request=request
    )
    otp = totp.token()
    await send_mail(
        subject="Password Reset OTP",
        body=f"Your password reset OTP is <b>{otp}</b>. Valid for 30 minutes",
        recipients=[
            data.email,
        ],
    )

    await session.commit()
    return response.success(
        "Please check your email for an OTP token for password reset."
    )


@router.post(
    "/password-reset/verify-otp",
    tags=["password_reset"],
    description="Verify the OTP token for password reset.",
    dependencies=[
        event(
            "account_password_reset_verification",
            target="account",
            description="Verify the OTP token for password reset.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::update"),
    ],
    response_model=response.DataSchema[
        response.NewSchema(
            "PasswordResetTokenSchema",
            {"password_reset_token": str},
        )
    ],
    status_code=200,
)
async def password_reset_verification(
    data: schemas.EmailOTPVerificationSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    verified = await totps.verify_identifier_totp_token(
        token=data.otp,
        identifier=data.email,
        request=request,
        delete_on_verification=True,
        session=session,
    )
    if not verified:
        return response.bad_request("Invalid OTP token.")

    password_reset_token = await totps.exchange_data_for_token(
        data={"email": data.email},
        expires_after=30 * 30,
        session=session,
        request=request,
    )
    await session.commit()
    return response.success(
        message="OTP verified successfully. Proceed to set a new password.",
        data={"password_reset_token": password_reset_token},
    )


@router.post(
    "/password-reset/complete",
    tags=["password_reset"],
    description="Complete the password reset process for an account.",
    dependencies=[
        event(
            "account_password_reset_completion",
            target="account",
            description="Complete the password reset process for an account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::update"),
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def password_reset_completion(
    data: schemas.PasswordResetCompletionSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    try:
        token_data = await totps.exchange_token_for_data(
            data.password_reset_token,
            request=request,
            delete_on_success=True,
            session=session,
        )
    except totps.InvalidToken:
        return response.bad_request("Invalid or expired token.")
    if not token_data:
        return response.bad_request("Invalid or expired token.")

    account = await crud.retrieve_account_by_email(
        session=session, email=token_data["email"]
    )
    if not account:
        return response.bad_request("No account found with this email.")

    account.set_password(data.new_password.get_secret_value())
    session.add(account)
    await session.commit()
    # Invalidate all authentications for the account
    await auth_tokens.delete_auth_tokens(session=session, account_id=account.id)
    return response.success("Password reset successfully!")


#################################
# AUTHENTICATED ACCOUNT ACTIONS #
#################################


@router.get(
    "/account",
    tags=["account"],
    description="Retrieve the authenticated account details.",
    dependencies=[
        event(
            "account_retrieve",
            target="account",
            description="Retrieve the authenticated account details.",
        ),
        authentication_required,
        permissions_required("accounts::*::view"),
    ],
    response_model=response.DataSchema[schemas.AccountSchema],
    status_code=200,
)
async def retrieve_account(account: ActiveUser[Account]):
    return response.success(data=schemas.AccountSchema.model_validate(account))


@router.patch(
    "/account",
    tags=["account"],
    description="Update the authenticated account details.",
    dependencies=[
        event(
            "account_update",
            target="account",
            description="Update the authenticated account details.",
        ),
        authentication_required,
        permissions_required("accounts::*::update"),
    ],
    response_model=response.DataSchema[schemas.AccountSchema],
    status_code=200,
)
async def update_account(
    data: schemas.AccountUpdateSchema,
    user: ActiveUser[Account],
    session: AsyncDBSession,
):
    changed_data = data.model_dump(exclude_unset=True)
    for key, value in changed_data.items():
        setattr(user, key, value)

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return response.success(data=schemas.AccountSchema.model_validate(user))


@router.post(
    "/account/change-email/initiate",
    tags=["account"],
    description="Update the authenticated account email.",
    dependencies=[
        event(
            "account_email_change_initiation",
            target="account",
            description="Update the authenticated account email.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::update"),
        authentication_required,
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def initiate_email_change(
    data: schemas.EmailChangeSchema,
    session: AsyncDBSession,
    request: fastapi.Request,
):
    account_exists = await crud.check_account_exists(
        session=session, email=data.new_email
    )
    if account_exists:
        return response.bad_request("An account with this email already exists.")

    totp = await totps.generate_totp_for_identifier(
        identifier=data.new_email, session=session, request=request
    )
    otp = totp.token()
    await send_mail(
        subject="Account Email Change OTP",
        body=f"Your account email change OTP is <b>{otp}</b>. Valid for 30 minutes",
        recipients=[
            data.new_email,
        ],
    )

    await session.commit()
    return response.success(
        "Please check your email for an OTP token for email change verification."
    )


@router.post(
    "/account/change-email/complete",
    tags=["account"],
    description="Verify the OTP token for email change and update the authenticated account email.",
    dependencies=[
        event(
            "account_email_change_completion",
            target="account",
            description="Verify the OTP token for email change and update the authenticated account email.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::update"),
        authentication_required,
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def complete_email_change(
    data: schemas.EmailOTPVerificationSchema,
    user: ActiveUser[Account],
    session: AsyncDBSession,
    request: fastapi.Request,
):
    verified = await totps.verify_identifier_totp_token(
        token=data.otp,
        identifier=data.email,
        request=request,
        delete_on_verification=True,
        session=session,
    )
    if not verified:
        return response.bad_request("Invalid OTP token.")

    user.email = data.email  # type: ignore
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return response.success("Email changed successfully!")


@router.post(
    "/account/change-password",
    tags=["account"],
    description="Update the authenticated account password.",
    dependencies=[
        event(
            "account_password_change",
            target="account",
            description="Update the authenticated account password.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::update"),
        authentication_required,
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def change_password(
    data: schemas.PasswordChangeSchema,
    user: ActiveUser[Account],
    session: AsyncDBSession,
):
    if user.check_password(data.old_password.get_secret_value()):
        return response.bad_request("Incorrect account password.")

    user.set_password(data.new_password.get_secret_value())
    session.add(user)
    await session.commit()
    return response.success("Password changed successfully!")


@router.post(
    "/logout",
    tags=["authentication"],
    dependencies=[
        event(
            "account_logout",
            target="account",
            description="Logout the authenticated account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::authenticate"),
        authentication_required,
    ],
    description="Logout the authenticated account.",
    response_model=response.DataSchema[None],
    status_code=200,
)
async def universal_logout_view(session: AsyncDBSession, account: ActiveUser[Account]):
    await auth_tokens.delete_auth_tokens(session=session, account_id=account.id)
    await session.commit()
    return response.success("Account logged-out successfully!")


@router.delete(
    "/account",
    tags=["account"],
    description="Delete the authenticated account.",
    dependencies=[
        event(
            "account_delete",
            target="account",
            description="Delete the authenticated account.",
        ),
        internal_api_clients_only,
        permissions_required("accounts::*::delete"),
        authentication_required,
    ],
    response_model=response.DataSchema[None],
    status_code=200,
)
async def delete_account(user: ActiveUser[Account], session: AsyncDBSession):
    async with capture.capture(
        OperationalError,
        code=409,
        content="There was a conflict while attempting to delete account",
    ):
        deleted_account = await crud.delete_account(
            session,
            account_id=user.id,
            deleted_by_id=user.id,
        )
    if not deleted_account:
        return response.conflict("This account has already been deleted")

    # Invalidate all authentications for the account
    await auth_tokens.delete_auth_tokens(
        session=session,
        account_id=deleted_account.id,
    )
    await session.commit()
    return response.success("Account deleted successfully!")
