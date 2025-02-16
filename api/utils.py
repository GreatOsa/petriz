import ulid


def generate_uid(prefix: str = "petriz_") -> str:
    """
    Generate a unique identifier using the ULID algorithm

    :param prefix: The prefix to prepend to the generated ULID
    :return: prefix + ulid
    """
    return prefix + ulid.ulid()
