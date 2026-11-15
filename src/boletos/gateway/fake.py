from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from boletos.gateway.base import ErroCredencial, ErroPermanente, ErroTemporario
from boletos.models import Cliente, Cobranca, Emissao


class FakeGateway:
    def __init__(self, roteiro_emitir: Iterable[str | None] = ()):
        self._roteiro = deque(roteiro_emitir)
        self._por_referencia: dict[str, Emissao] = {}
        self._todas: list[Emissao] = []
        self.chamadas_emitir = 0
        self.chamadas_buscar = 0
        self.chamadas_criar_cliente = 0

    @property
    def total_emitido(self) -> int:
        return len(self._todas)

    def criar_cliente(self, cliente: Cliente) -> str:
        self.chamadas_criar_cliente += 1
        return f"cus_fake_{self.chamadas_criar_cliente:04d}"

    def emitir(self, cobranca: Cobranca) -> Emissao:
        self.chamadas_emitir += 1
        passo = self._roteiro.popleft() if self._roteiro else None
        if passo == "credencial":
            raise ErroCredencial("chave de API recusada (401)")
        if passo == "perm":
            raise ErroPermanente("dados recusados pelo provedor (400)")
        if passo == "temp":
            raise ErroTemporario("timeout simulado")
        emissao = self._criar(cobranca)
        if passo == "cair_apos_criar":
            raise ErroTemporario("conexão caiu depois de criar o boleto")
        return emissao

    def buscar_por_referencia(self, ref: str) -> Emissao | None:
        self.chamadas_buscar += 1
        return self._por_referencia.get(ref)

    def _criar(self, cobranca: Cobranca) -> Emissao:
        n = len(self._todas) + 1
        emissao = Emissao(
            id_gw=f"pay_fake_{n:05d}",
            link=f"https://sandbox.exemplo.test/boleto/{n:05d}",
            linha_digitavel="00000.00000 00000.000000 00000.000000 0 00000000000000",
        )
        self._todas.append(emissao)
        self._por_referencia[cobranca.chave_idem] = emissao
        return emissao
