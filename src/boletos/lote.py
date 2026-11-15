from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from boletos.config import Config
from boletos.ingest.planilha import ler_planilha
from boletos.models import Cobranca, LinhaValida, Rejeicao, chave_da_linha
from boletos.store.db import Banco
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


@dataclass
class ResultadoImportacao:
    lote_id: int | None
    linhas_lidas: int
    criadas: list[Cobranca]
    existentes: list[tuple[int, Cobranca]]
    novas: int
    rejeicoes: list[Rejeicao]
    avisos: list[Aviso]
    arquivo_repetido: int | None
    dry_run: bool


def _hash_arquivo(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def importar(banco: Banco, caminho: Path, cfg: Config, hoje: date, *, dry_run: bool = False) -> ResultadoImportacao:
    analise = analisar(caminho, cfg, hoje)  # recusa o arquivo inteiro antes de gravar qualquer coisa
    hash_arquivo = _hash_arquivo(caminho)
    repetido = banco.lote_por_hash(hash_arquivo)
    avisos = list(analise.avisos)
    if repetido is not None:
        avisos.append(Aviso("arquivo_repetido", 0, f"este arquivo já foi importado no lote {repetido}"))

    if dry_run:
        novas = sum(1 for item in analise.itens if banco.buscar_por_chave(item.chave) is None)
        return ResultadoImportacao(None, analise.linhas_lidas, [], [], novas, analise.rejeicoes, avisos, repetido, True)

    criadas: list[Cobranca] = []
    existentes: list[tuple[int, Cobranca]] = []
    ids_por_linha: dict[int, int] = {}
    with banco.transacao():
        lote_id = banco.criar_lote(Path(caminho).name, hash_arquivo, analise.linhas_lidas, len(analise.rejeicoes))
        for rej in analise.rejeicoes:
            banco.inserir_rejeicao(lote_id, rej)
        for item in analise.itens:
            ja_existe = banco.buscar_por_chave(item.chave)
            if ja_existe is not None:
                existentes.append((item.linha, ja_existe))
                continue
            de_outros_lotes = [
                c
                for c in banco.buscar_por_doc_competencia(item.dados.documento, item.dados.competencia)
                if c.lote_id != lote_id
            ]
            nova = banco.inserir_cobranca(lote_id, item.dados, item.chave)
            criadas.append(nova)
            ids_por_linha[item.linha] = nova.id
            if de_outros_lotes:
                texto = (
                    f"linha {item.linha}: o documento já tem cobrança em {item.dados.competencia} "
                    f"(cobrança {de_outros_lotes[0].id}) com valor ou vencimento diferente"
                )
                avisos.append(Aviso("competencia_repetida", item.linha, texto))
                banco.registrar_evento(lote_id, "aviso_competencia_repetida", texto, cobranca_id=nova.id)
        for aviso in analise.avisos:
            if aviso.tipo == "competencia_repetida" and aviso.linha in ids_por_linha:
                banco.registrar_evento(
                    lote_id, "aviso_competencia_repetida", aviso.texto, cobranca_id=ids_por_linha[aviso.linha]
                )
        banco.registrar_evento(lote_id, "lote_importado", f"{len(criadas)} criadas, {len(existentes)} já existiam")
    return ResultadoImportacao(
        lote_id, analise.linhas_lidas, criadas, existentes, len(criadas), analise.rejeicoes, avisos, repetido, False
    )
