"""Bling tool layer: declarative endpoint specs + factory + registry.

During the migration to full API coverage, the legacy ``BlingTools`` class is
re-exported so existing imports keep working. It is removed once the registry
covers every endpoint.
"""

from .legacy import BlingTools  # noqa: F401  (removed in cleanup task)
