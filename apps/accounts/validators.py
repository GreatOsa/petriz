from helpers.generics.utils.validators import min_length_validator


def min_password_length_validator(password: str):
    return min_length_validator(min_length=8, value=password)
