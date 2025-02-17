import typing
import pydantic

from helpers.fastapi.config import settings


class AccountRegistrationInitiationSchema(pydantic.BaseModel):
    """Schema for initiating a new Account registration."""

    email: typing.Annotated[
        typing.Annotated[
            pydantic.EmailStr,
            pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
        ],
        pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
    ] = pydantic.Field(
        title="Account email",
        description="Email to be used to create the account",
    )


class EmailOTPVerificationSchema(pydantic.BaseModel):
    """Schema for verifying an account registration email with an OTP."""

    otp: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=settings.OTP_LENGTH,
            max_length=settings.OTP_LENGTH,
        ),
    ] = pydantic.Field(
        title="OTP token",
        description="One-time password token received in email for verification.",
    )

    email: typing.Annotated[
        typing.Annotated[
            pydantic.EmailStr,
            pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
        ],
        pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
    ] = pydantic.Field(title="Account email", description="Email to be verified")


class AccountRegistrationCompletionSchema(pydantic.BaseModel):
    """Schema for creating a new Account."""

    password_set_token: str = pydantic.Field(
        description="Token received on account email verification, to be used to set password."
    )
    name: typing.Optional[
        typing.Annotated[
            str,
            pydantic.StringConstraints(
                strip_whitespace=True, max_length=50, min_length=1
            ),
        ]
    ] = pydantic.Field(
        None,
        title="Account name",
        description="Name to be used for the account",
    )
    password: pydantic.SecretStr = pydantic.Field(
        title="Account password",
        description="Secret to be used as account password",
    )


class AccountAuthenticationInitiationSchema(pydantic.BaseModel):
    """Schema for initiating an account authentication."""

    email: typing.Annotated[
        pydantic.EmailStr,
        pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
    ] = pydantic.Field(
        title="Account email",
    )
    password: pydantic.SecretStr = pydantic.Field(
        title="Account password",
    )


class PasswordResetInitiationSchema(pydantic.BaseModel):
    """Schema for initiating a password reset."""

    email: typing.Annotated[
        pydantic.EmailStr,
        pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
    ] = pydantic.Field(
        title="Account email",
    )


class PasswordResetCompletionSchema(pydantic.BaseModel):
    """Schema for completing a password reset."""

    password_reset_token: str = pydantic.Field(
        description="Token received on account email verification, to be used to reset password."
    )

    new_password: pydantic.SecretStr = pydantic.Field(
        title="New account password",
        description="Replacement account password",
    )


class AccountSchema(pydantic.BaseModel):
    """Account schema For serialization purposes only."""

    uid: pydantic.StrictStr = pydantic.Field(
        title="Account UID",
        description="Unique identifier for the account",
        frozen=True,
    )
    name: typing.Optional[
        typing.Annotated[
            str,
            pydantic.StringConstraints(
                strip_whitespace=True, max_length=50, min_length=1
            ),
        ]
    ] = pydantic.Field(
        None,
        title="Account name",
    )
    email: typing.Annotated[
        pydantic.EmailStr,
        pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
    ] = pydantic.Field(
        title="Account email",
    )
    is_active: pydantic.StrictBool = pydantic.Field(
        description="Is account active?",
    )
    is_staff: pydantic.StrictBool = pydantic.Field(
        description="Is account staff?",
    )
    is_admin: pydantic.StrictBool = pydantic.Field(
        description="Is account admin?",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Account update date and time",
    )

    class Config:
        from_attributes = True


class AccountUpdateSchema(pydantic.BaseModel):
    """Schema for updating an account."""

    name: typing.Optional[
        typing.Annotated[
            str,
            pydantic.StringConstraints(
                strip_whitespace=True, max_length=50, min_length=1
            ),
        ]
    ] = pydantic.Field(
        None,
        title="Account name",
    )


class PasswordChangeSchema(pydantic.BaseModel):
    """Schema for changing an account password."""

    old_password: pydantic.SecretStr = pydantic.Field(
        title="Old account password",
        description="Old account password",
    )
    new_password: pydantic.SecretStr = pydantic.Field(
        title="New account password",
        description="New account password",
    )


class EmailChangeSchema(pydantic.BaseModel):
    """Schema for changing an account email."""

    new_email: typing.Annotated[
        pydantic.EmailStr,
        pydantic.StringConstraints(to_lower=True, strip_whitespace=True),
    ] = pydantic.Field(
        title="New account email",
        description="New account email",
    )


__all__ = [
    "AccountRegistrationInitiationSchema",
    "EmailOTPVerificationSchema",
    "AccountRegistrationCompletionSchema",
    "AccountAuthenticationInitiationSchema",
    "PasswordResetInitiationSchema",
    "PasswordResetCompletionSchema",
    "AccountSchema",
    "AccountUpdateSchema",
    "PasswordChangeSchema",
]
