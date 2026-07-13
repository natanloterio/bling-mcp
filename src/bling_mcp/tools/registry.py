"""Aggregate every domain module's endpoints into one catalog.

``MODULES`` maps a domain name (used by the optional ``BLING_MODULES`` filter)
to its endpoints; ``ALL_ENDPOINTS`` is the flat catalog the server registers.
The validation tests in ``tests/test_registry.py`` guard the whole set.
"""

from __future__ import annotations

from .spec import Endpoint

from .cadastros import ENDPOINTS as CADASTROS
from .contatos import ENDPOINTS as CONTATOS
from .estoque import ENDPOINTS as ESTOQUE
from .financeiro import ENDPOINTS as FINANCEIRO
from .fiscal import ENDPOINTS as FISCAL
from .logistica import ENDPOINTS as LOGISTICA
from .pedidos import ENDPOINTS as PEDIDOS
from .producao import ENDPOINTS as PRODUCAO
from .produtos import ENDPOINTS as PRODUTOS
from .situacoes import ENDPOINTS as SITUACOES

MODULES: dict[str, tuple[Endpoint, ...]] = {
    "produtos": PRODUTOS,
    "pedidos": PEDIDOS,
    "contatos": CONTATOS,
    "financeiro": FINANCEIRO,
    "fiscal": FISCAL,
    "estoque": ESTOQUE,
    "logistica": LOGISTICA,
    "producao": PRODUCAO,
    "situacoes": SITUACOES,
    "cadastros": CADASTROS,
}

ALL_ENDPOINTS: tuple[Endpoint, ...] = tuple(
    endpoint for endpoints in MODULES.values() for endpoint in endpoints
)
