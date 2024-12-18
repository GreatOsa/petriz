import string
import random

UNICODE_CHARS = string.ascii_letters + string.digits


def generate_uid(length: int = 10, prefix: str = "petriz_") -> str:
    """"""
    return prefix + "".join(random.sample(UNICODE_CHARS, k=length))

