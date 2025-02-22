import fastapi

from . import schemas
from . import crud
from helpers.fastapi.mailing import send_mail
from helpers.fastapi.dependencies.connections import DBSession
from helpers.fastapi.dependencies.access_control import ActiveUser
from helpers.fastapi.response import shortcuts as response
from api.dependencies.authorization import internal_api_clients_only
from api.dependencies.authentication import authentication_required
from apps.tokens import auth_tokens, totps


router = fastapi.APIRouter()


########################
# ACCOUNT REGISTRATION #
########################


@router.post(
    "/registration/initiate",
    tags=["registration"],
    summary="Initiate the registration process for a new account.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def registration_initiation(
    data: schemas.AccountRegistrationInitiationSchema,
    session: DBSession,
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
    summary="Verify the OTP token for email registration.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def registration_email_verification(
    data: schemas.EmailOTPVerificationSchema,
    session: DBSession,
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


@router.post(
    "/registration/complete",
    tags=["registration"],
    summary="Complete the registration process for a new account.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def registration_completion(
    data: schemas.AccountRegistrationCompletionSchema,
    session: DBSession,
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
    return response.success(data=response_data)


##########################
# ACCOUNT AUTHENTICATION #
##########################


@router.post(
    "/authentication/initiate",
    tags=["authentication"],
    summary="Initiate the authentication process for a new account.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def authentication_initiation(
    data: schemas.AccountAuthenticationInitiationSchema,
    session: DBSession,
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
    summary="Verify the OTP token for sent to authenticated account email to receive auth token.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def authentication_completion(
    data: schemas.EmailOTPVerificationSchema,
    session: DBSession,
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
    summary="Initiate the password reset process for an account.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def password_reset_initiation(
    data: schemas.PasswordResetInitiationSchema,
    session: DBSession,
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
    summary="Verify the OTP token for password reset.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def password_reset_verification(
    data: schemas.EmailOTPVerificationSchema,
    session: DBSession,
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
    summary="Complete the password reset process for an account.",
    dependencies=[
        internal_api_clients_only,
    ],
)
async def password_reset_completion(
    data: schemas.PasswordResetCompletionSchema,
    session: DBSession,
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
    summary="Retrieve the authenticated account details.",
    dependencies=[
        authentication_required,
    ],
)
async def retrieve_account(account: ActiveUser):
    return response.success(data=schemas.AccountSchema.model_validate(account))


@router.patch(
    "/account",
    tags=["account"],
    summary="Update the authenticated account details.",
    dependencies=[
        authentication_required,
    ],
)
async def update_account(
    data: schemas.AccountUpdateSchema,
    account: ActiveUser,
    session: DBSession,
):
    changed_data = data.model_dump(exclude_unset=True)
    for key, value in changed_data.items():
        setattr(account, key, value)

    session.add(account)
    await session.commit()
    await session.refresh(account)
    return response.success(data=schemas.AccountSchema.model_validate(account))


@router.post(
    "/account/change-email/initiate",
    tags=["account"],
    summary="Update the authenticated account email.",
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ],
)
async def initiate_email_change(
    data: schemas.EmailChangeSchema,
    session: DBSession,
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
    summary="Verify the OTP token for email change and update the authenticated account email.",
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ],
)
async def complete_email_change(
    data: schemas.EmailOTPVerificationSchema,
    account: ActiveUser,
    session: DBSession,
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

    account.email = data.email
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return response.success("Email changed successfully!")


@router.post(
    "/account/change-password",
    tags=["account"],
    summary="Update the authenticated account password.",
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ],
)
async def change_password(
    data: schemas.PasswordChangeSchema,
    account: ActiveUser,
    session: DBSession,
):
    if account.check_password(data.old_password.get_secret_value()):
        return response.bad_request("Incorrect account password.")

    account.set_password(data.new_password.get_secret_value())
    session.add(account)
    await session.commit()
    return response.success("Password changed successfully!")


@router.post(
    "/logout",
    tags=["authentication"],
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ],
)
async def universal_logout_view(session: DBSession, account: ActiveUser):
    await auth_tokens.delete_auth_tokens(session=session, account_id=account.id)
    await session.commit()
    return response.success("Account logged-out successfully!")


@router.delete(
    "/account",
    tags=["account"],
    summary="Delete the authenticated account.",
    dependencies=[
        internal_api_clients_only,
        authentication_required,
    ],
)
async def delete_account(account: ActiveUser, session: DBSession):
    account.is_deleted = True
    account.is_active = False
    await session.add(account)
    # Invalidate all authentications for the account
    await auth_tokens.delete_auth_tokens(session=session, account_id=account.id)
    await session.commit()
    return response.no_content("Account deleted successfully!")
