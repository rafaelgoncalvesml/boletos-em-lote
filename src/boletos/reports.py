from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from boletos.formatos import formatar_reais
from boletos.models import Estado, Rejeicao
from boletos.store.db import Banco

_COM_BOLETO = {Estado.EMITIDA, Estado.RASCUNHO, Estado.APROVADA, Estado.ENVIADA}


@dataclass
class Resumo:
    lote_id: int
    arquivo: str
    linhas_lidas: int
    por_estado: dict[str, int]
    valor_emitido_cent: int
    rejeicoes: list[Rejeicao] = field(default_factory=list)
    erros: list[tuple[int, str, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def montar(banco: Banco, lote_id: int) -> Resumo:
    lote = banco.obter_lote(lote_id)
    cobrancas = banco.listar(lote_id)
    return Resumo(
        lote_id=lote_id,
        arquivo=lote["arquivo"],
        linhas_lidas=lote["linhas_lidas"],
        por_estado=banco.contar_por_estado(lote_id),
        valor_emitido_cent=sum(c.valor_cent for c in cobrancas if c.estado in _COM_BOLETO),
        rejeicoes=banco.rejeicoes(lote_id),
        erros=[(c.id, c.etapa_falha or "", banco.motivo_erro(c.id)) for c in cobrancas if c.estado == Estado.ERRO],
        avisos=[e["detalhe"] for e in banco.eventos(lote_id) if e["tipo"].startswith("aviso_")],
    )


def em_markdown(r: Resumo) -> str:
    linhas = [f"Lote {r.lote_id} ({r.arquivo}), {r.linhas_lidas} linhas lidas", ""]
    linhas.append("Cobranças por estado:")
    for estado in Estado:
        if estado.value in r.por_estado:
            linhas.append(f"- {estado.value}: {r.por_estado[estado.value]}")
    linhas += ["", f"Valor total emitido: {formatar_reais(r.valor_emitido_cent)}"]
    if r.rejeicoes:
        linhas += ["", "Linhas rejeitadas:"]
        linhas += [f"- linha {x.linha}, coluna {x.coluna}: {x.motivo}" for x in r.rejeicoes]
    if r.erros:
        linhas += ["", "Cobranças com erro:"]
        linhas += [f"- cobrança {i}, etapa {etapa}: {motivo}" for i, etapa, motivo in r.erros]
    if r.avisos:
        linhas += ["", "Avisos:"]
        linhas += [f"- {a}" for a in r.avisos]
    return "\n".join(linhas) + "\n"


def em_csv(r: Resumo) -> str:
    saida = io.StringIO()
    w = csv.writer(saida, lineterminator="\n")
    w.writerow(["secao", "chave", "valor", "detalhe"])
    for estado, n in r.por_estado.items():
        w.writerow(["estado", estado, n, ""])
    w.writerow(["total", "valor_emitido_cent", r.valor_emitido_cent, ""])
    for x in r.rejeicoes:
        w.writerow(["rejeicao", f"linha {x.linha} coluna {x.coluna}", "", x.motivo])
    for i, etapa, motivo in r.erros:
        w.writerow(["erro", f"cobranca {i}", "", f"{etapa}: {motivo}"])
    for aviso in r.avisos:
        w.writerow(["aviso", "", "", aviso])
    return saida.getvalue()
