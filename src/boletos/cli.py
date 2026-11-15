from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import typer

from boletos import lote as lote_mod
from boletos import reports
from boletos.config import Config, carregar, exigir_para
from boletos.erros import EntradaRecusada, ErroBoletos
from boletos.gateway.base import BillingGateway
from boletos.gateway.fake import FakeGateway
from boletos.logs import configurar_logs
from boletos.store.db import Banco

app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Emissão de boletos em lote (dados fictícios, sandbox)."
)


def comando(func):
    @functools.wraps(func)
    def interno(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise
        except ErroBoletos as erro:
            typer.echo(f"Erro: {erro}", err=True)
            raise typer.Exit(erro.codigo_saida) from erro
        except Exception:
            logging.getLogger("boletos").exception("falha inesperada")
            typer.echo("Erro inesperado. Os detalhes estão em logs/boletos.log.", err=True)
            raise typer.Exit(1) from None

    return interno


def _config(comando_nome: str, **opcoes) -> Config:
    cfg = carregar()
    exigir_para(cfg, comando_nome, **opcoes)  # antes de tocar no banco
    configurar_logs(cfg)
    return cfg


@contextmanager
def _banco(cfg: Config) -> Iterator[Banco]:
    banco = Banco.abrir(cfg.db_path)
    try:
        yield banco
    finally:
        banco.close()


def _exigir_lote(banco: Banco, lote_id: int) -> None:
    if banco.obter_lote(lote_id) is None:
        raise EntradaRecusada(f"O lote {lote_id} não existe.")


def _gateway(nome: str, cfg: Config) -> BillingGateway:
    if nome == "fake":
        return FakeGateway()
    if nome == "asaas":
        from boletos.gateway.asaas import AsaasGateway

        return AsaasGateway(cfg.asaas_api_key, cfg.asaas_base_url)
    raise EntradaRecusada("Gateway desconhecido. Use fake ou asaas.")


def _imprimir_resumo(banco: Banco, lote_id: int) -> None:
    typer.echo(reports.em_markdown(reports.montar(banco, lote_id)))


@app.command("importar")
@comando
def importar_cmd(
    arquivo: Path = typer.Argument(..., help="Planilha CSV ou XLSX."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Valida e mostra o resultado, sem gravar."),
) -> None:
    """Valida a planilha e grava um lote."""
    cfg = _config("importar")
    with _banco(cfg) as banco:
        res = lote_mod.importar(banco, arquivo, cfg, date.today(), dry_run=dry_run)
        quando = "seriam criadas" if dry_run else "criadas"
        typer.echo(f"{res.linhas_lidas} linhas lidas, {res.novas} cobranças {quando}, {len(res.rejeicoes)} rejeitadas.")
        for rej in res.rejeicoes:
            typer.echo(f"  rejeitada: linha {rej.linha}, coluna {rej.coluna}: {rej.motivo}")
        for aviso in res.avisos:
            typer.echo(f"  aviso: {aviso.texto}")
        for linha, existente in res.existentes:
            typer.echo(f"  linha {linha} já existe: cobrança {existente.id} em {existente.estado.value}")
        if res.lote_id is not None:
            typer.echo(f"Lote {res.lote_id} gravado.\n")
            _imprimir_resumo(banco, res.lote_id)


@app.command("emitir")
@comando
def emitir_cmd(
    lote: int = typer.Option(..., "--lote", help="Número do lote."),
    retomar: bool = typer.Option(False, "--retomar", help="Continua um lote pausado."),
    gateway: str = typer.Option("fake", "--gateway", help="fake ou asaas."),
) -> None:
    """Emite as cobranças validadas do lote."""
    cfg = _config("emitir", gateway=gateway)
    with _banco(cfg) as banco:
        _exigir_lote(banco, lote)
        gw = _gateway(gateway, cfg)
        res = lote_mod.emitir(banco, gw, lote, cfg, retomar=retomar)
        _imprimir_resumo(banco, lote)
        if res.pausado:
            typer.echo("Lote pausado por falhas seguidas. Confira o provedor e rode de novo com --retomar.", err=True)
            raise typer.Exit(3)


@app.command("relatorio")
@comando
def relatorio_cmd(
    lote: int = typer.Option(..., "--lote"),
    formato: str = typer.Option("md", "--formato", help="md ou csv."),
) -> None:
    """Resumo do lote."""
    if formato not in ("md", "csv"):
        raise EntradaRecusada("Formato desconhecido. Use md ou csv.")
    cfg = _config("relatorio")
    with _banco(cfg) as banco:
        _exigir_lote(banco, lote)
        resumo = reports.montar(banco, lote)
        typer.echo(reports.em_csv(resumo) if formato == "csv" else reports.em_markdown(resumo), nl=False)


@app.command("reprocessar")
@comando
def reprocessar_cmd(cobranca: int = typer.Option(..., "--cobranca", help="ID da cobrança em erro.")) -> None:
    """Leva uma cobrança em erro de volta para validada."""
    cfg = _config("reprocessar")
    with _banco(cfg) as banco:
        c = lote_mod.reprocessar(banco, cobranca)
        typer.echo(f"Cobrança {c.id} voltou para {c.estado.value}.")


if __name__ == "__main__":
    app()
