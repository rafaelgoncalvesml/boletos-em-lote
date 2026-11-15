from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from boletos.config import Config
from boletos.ingest.planilha import ler_planilha
from boletos.models import LinhaValida, Rejeicao, chave_da_linha
from boletos.validation.regras import validar_linha


@dataclass(frozen=True)
class Aviso:
    tipo: str
    linha: int
    texto: str


@dataclass(frozen=True)
class ItemAnalise:
    linha: int
    dados: LinhaValida
    chave: str


@dataclass
class Analise:
    linhas_lidas: int
    itens: list[ItemAnalise] = field(default_factory=list)
    rejeicoes: list[Rejeicao] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)


def analisar(caminho: Path, cfg: Config, hoje: date) -> Analise:
    planilha = ler_planilha(caminho, cfg.linhas_por_lote)
    analise = Analise(linhas_lidas=len(planilha.linhas))
    por_chave: dict[str, int] = {}
    por_doc_competencia: dict[tuple[str, str], int] = {}
    for numero, bruto in planilha.linhas:
        dados, rejeicoes = validar_linha(numero, bruto, hoje, cfg.valor_maximo_cent)
        if dados is None:
            analise.rejeicoes.extend(rejeicoes)
            continue
        chave = chave_da_linha(dados)
        if chave in por_chave:
            analise.avisos.append(
                Aviso("duplicada_arquivo", numero, f"linha {numero} repete a linha {por_chave[chave]} e foi ignorada")
            )
            continue
        par = (dados.documento, dados.competencia)
        if par in por_doc_competencia:
            analise.avisos.append(
                Aviso(
                    "competencia_repetida",
                    numero,
                    f"linha {numero}: mesmo documento e competência da linha {por_doc_competencia[par]}, "
                    "com valor ou vencimento diferente (possível duplicidade)",
                )
            )
        por_chave[chave] = numero
        por_doc_competencia.setdefault(par, numero)
        analise.itens.append(ItemAnalise(numero, dados, chave))
    return analise
