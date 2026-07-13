"""Declarative description of a Bling API endpoint.

An :class:`Endpoint` is immutable data: the factory (``factory.py``) turns each
one into a typed MCP tool, and the registry (``registry.py``) aggregates them.
Keeping endpoints as data — instead of hand-written methods — keeps the ~217
operations DRY and lets a single validation test guard the whole catalog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Param:
    """A single tool parameter and its Python type (used for schema inference)."""

    name: str
    type: type = str


@dataclass(frozen=True)
class Endpoint:
    """One Bling REST operation exposed as one MCP tool.

    - ``path`` is a template such as ``"produtos/{idProduto}"``; every ``{name}``
      placeholder must have a matching :class:`Param` in ``path_params``.
    - ``query_params`` are optional (default ``None`` and dropped before the call).
    - ``has_body`` adds a ``body: dict`` argument for POST/PUT/PATCH payloads.
    """

    name: str
    method: str
    path: str
    description: str
    path_params: tuple[Param, ...] = ()
    query_params: tuple[Param, ...] = ()
    has_body: bool = False

    def placeholders(self) -> set[str]:
        """Return the ``{name}`` placeholders present in ``path``."""
        return set(re.findall(r"{(\w+)}", self.path))
