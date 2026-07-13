"""Bling tool layer: declarative endpoint specs, factory, and registry.

- ``spec`` — the immutable :class:`~bling_mcp.tools.spec.Endpoint`/``Param`` data.
- ``factory`` — turns an ``Endpoint`` into a typed MCP tool.
- ``registry`` — aggregates every domain module into ``ALL_ENDPOINTS``.
- domain modules (``produtos``, ``pedidos``, …) — the endpoint catalogs.
"""
