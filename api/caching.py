import typing
import orjson
import hashlib
from starlette.requests import Request
from starlette.responses import Response

from fastapi.encoders import jsonable_encoder
from fastapi_cache import Coder


def _safe_serialize(obj: typing.Any) -> str:
    """Safely serialize objects to string representation."""
    if hasattr(obj, "__dict__"):
        return str(vars(obj))
    if isinstance(obj, (list, tuple)):
        return str([_safe_serialize(x) for x in obj])
    if isinstance(obj, dict):
        return str({k: _safe_serialize(v) for k, v in sorted(obj.items())})
    return str(obj)


RELEVANT_HEADERS = [
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
]


def request_key_builder_factory(
    *,
    default_namespace: str = "",
    use_headers: typing.Optional[typing.List[str]] = None,
    use_path: bool = True,
    use_query: bool = True,
    use_args: bool = False,
    use_kwargs: typing.Optional[typing.List[str]] = None,
) -> typing.Callable[..., typing.Awaitable[str]]:
    """
    Factory function for creating a request key builder function.

    :param default_namespace: Default namespace to use for cache keys
    :param use_headers: List of headers to include in cache key
    :param use_path: Whether to include the request path in cache key
    :param use_query: Whether to include the request query parameters in cache key
    :param use_args: Whether to include positional arguments in cache key
    :param use_kwargs: List of keyword arguments to include in cache key
    :returns: Function that builds a cache key based on request parameters
    """

    async def _key_builder(
        func: typing.Callable[..., typing.Any],
        namespace: str = default_namespace,
        *,
        request: typing.Optional[Request] = None,
        response: typing.Optional[Response] = None,
        args: typing.Tuple[typing.Any, ...],
        kwargs: typing.Dict[typing.Any, typing.Any],
    ) -> str:
        """Builds a cache key based on request parameters in a deterministic way."""
        nonlocal use_headers, use_path, use_query, use_args, use_kwargs

        key_parts = [func.__module__, func.__name__]

        if request:
            if use_path:
                key_parts.append(request.url.path)

            if use_query and request.query_params:
                query_items = sorted(request.query_params.items())
                key_parts.append(repr(query_items))

            if use_headers and request.headers:
                relevant_headers = {
                    k: v for k, v in request.headers.items() if k.lower() in use_headers
                }
                if relevant_headers:
                    key_parts.append(repr(sorted(relevant_headers.items())))

        if use_args and args:
            key_parts.append(_safe_serialize(args))

        if use_kwargs and kwargs:
            clean_kwargs = {k: v for k, v in kwargs.items() if k in use_kwargs}
            if clean_kwargs:
                key_parts.append(_safe_serialize(clean_kwargs))

        cache_key = ":".join(str(part) for part in key_parts)
        key_hash = hashlib.md5(cache_key.encode()).hexdigest()
        return f"{namespace}:{key_hash}"

    return _key_builder


request_key_builder = request_key_builder_factory(
    use_headers=RELEVANT_HEADERS,
    use_path=True,
    use_query=True,
    use_args=False,
    use_kwargs=None,
)


class ORJsonCoder(Coder):
    """Custom coder for serializing and deserializing cache values."""

    @classmethod
    def encode(cls, value: typing.Any) -> bytes:
        if isinstance(value, Response):
            return value.body
        return orjson.dumps(
            value,
            default=jsonable_encoder,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
        )

    @classmethod
    def decode(cls, value: bytes) -> typing.Any:
        return orjson.loads(value)
