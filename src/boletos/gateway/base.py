from __future__ import annotations

from typing import Protocol

from boletos.models import Cliente, Cobranca, Emissao


class ErroTemporario(Exception):
    """Timeout, 5xx ou 429: pode repetir."""


class ErroPermanente(Exception):
    """4xx (menos 429): não repetir."""


class ErroCredencial(ErroPermanente):
    """401 ou 403: interrompe o lote inteiro."""


class BillingGateway(Protocol):
    def criar_cliente(self, cliente: Cliente) -> str: ...

    def emitir(self, cobranca: Cobranca) -> Emissao: ...

    def buscar_por_referencia(self, ref: str) -> Emissao | None: ...
