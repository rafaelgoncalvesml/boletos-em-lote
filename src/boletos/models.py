from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Estado(StrEnum):
    VALIDADA = "validada"
    EMITIDA = "emitida"
    RASCUNHO = "rascunho"
    APROVADA = "aprovada"
    ENVIADA = "enviada"
    ERRO = "erro"


TRANSICOES: dict[Estado, set[Estado]] = {
    Estado.VALIDADA: {Estado.EMITIDA, Estado.ERRO},
    Estado.EMITIDA: {Estado.RASCUNHO, Estado.ERRO},
    Estado.RASCUNHO: {Estado.APROVADA, Estado.ERRO},
    Estado.APROVADA: {Estado.ENVIADA},
    Estado.ENVIADA: set(),
    Estado.ERRO: {Estado.VALIDADA},
}


@dataclass(frozen=True)
class LinhaValida:
    linha: int
    nome: str
    documento: str
    email: str
    valor_cent: int
    vencimento: date
    competencia: str
    descricao: str


@dataclass(frozen=True)
class Rejeicao:
    linha: int
    coluna: str
    motivo: str


@dataclass(frozen=True)
class Cliente:
    nome: str
    documento: str
    email: str


@dataclass(frozen=True)
class Emissao:
    id_gw: str
    link: str
    linha_digitavel: str


@dataclass(frozen=True)
class Cobranca:
    id: int
    lote_id: int
    chave_idem: str
    cliente_nome: str
    cliente_doc: str
    cliente_email: str
    competencia: str
    valor_cent: int
    vencimento: str
    descricao: str
    estado: Estado
    etapa_falha: str | None
    id_cliente_gw: str | None
    id_cobranca_gw: str | None
    link_boleto: str | None
    linha_digitavel: str | None
    criado_em: str
    atualizado_em: str


def chave_idem(documento: str, competencia: str, valor_cent: int, vencimento_iso: str) -> str:
    bruto = "|".join([documento, competencia, str(valor_cent), vencimento_iso])
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def chave_da_linha(linha: LinhaValida) -> str:
    return chave_idem(linha.documento, linha.competencia, linha.valor_cent, linha.vencimento.isoformat())
