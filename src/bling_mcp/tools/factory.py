"""Turn an :class:`Endpoint` into a callable MCP tool.

Spike (test_factory_spike.py) confirmed FastMCP infers the input schema from a
function's ``__signature__``/``__annotations__``, so we build a keyword-only
signature dynamically (Plan A). Each generated tool formats the path from its
path params and dispatches to the matching ``BlingClient`` verb.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from .spec import Endpoint

_VERB = {"GET": "get", "POST": "post", "PUT": "put", "PATCH": "patch", "DELETE": "delete"}


def build_tool(endpoint: Endpoint, client: Any) -> Callable[..., Any]:
    """Build a typed, self-describing tool function for ``endpoint``."""
    verb = _VERB[endpoint.method]
    path_names = [p.name for p in endpoint.path_params]
    query_names = [p.name for p in endpoint.query_params]

    def impl(**kwargs: Any) -> Any:
        path = endpoint.path.format(**{n: kwargs[n] for n in path_names})
        method = getattr(client, verb)
        params = {n: kwargs.get(n) for n in query_names} or None
        if endpoint.method in ("GET", "DELETE"):
            return method(path, params=params)
        body = kwargs.get("body") if endpoint.has_body else None
        return method(path, json=body, params=params)

    parameters = [
        inspect.Parameter(
            p.name, inspect.Parameter.KEYWORD_ONLY, annotation=p.type
        )
        for p in endpoint.path_params
    ]
    parameters += [
        inspect.Parameter(
            p.name, inspect.Parameter.KEYWORD_ONLY, annotation=p.type, default=None
        )
        for p in endpoint.query_params
    ]
    if endpoint.has_body:
        parameters.append(
            inspect.Parameter("body", inspect.Parameter.KEYWORD_ONLY, annotation=dict)
        )

    impl.__signature__ = inspect.Signature(parameters)
    impl.__annotations__ = {p.name: p.annotation for p in parameters}
    impl.__name__ = f"bling_{endpoint.name}"
    impl.__doc__ = f"{endpoint.description} ({endpoint.method} /{endpoint.path})"
    return impl
