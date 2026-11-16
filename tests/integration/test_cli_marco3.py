import pytest
from typer.testing import CliRunner

from boletos import cli

pytestmark = pytest.mark.integration
runner = CliRunner()


def _ate_rascunho():
    assert runner.invoke(cli.app, ["importar", "clientes.csv"]).exit_code == 0
    assert runner.invoke(cli.app, ["emitir", "--lote", "1"]).exit_code == 0
    r = runner.invoke(cli.app, ["rascunhos", "--lote", "1", "--sem-claude"])
    assert r.exit_code == 0, r.output
    return r


def test_rascunhos_gera_20_arquivos(ambiente, planilha):
    r = _ate_rascunho()
    assert "rascunho: 20" in r.output
    assert len(list((ambiente / "rascunhos" / "1").glob("*.eml"))) == 20


def test_rascunhos_sem_chave_do_claude_avisa_e_usa_modelo_fixo(ambiente, planilha):
    runner.invoke(cli.app, ["importar", "clientes.csv"])
    runner.invoke(cli.app, ["emitir", "--lote", "1"])
    r = runner.invoke(cli.app, ["rascunhos", "--lote", "1"])
    assert r.exit_code == 0 and "modelo fixo" in r.output


def test_aprovar_exige_lote_ou_cobranca(ambiente, planilha):
    _ate_rascunho()
    assert runner.invoke(cli.app, ["aprovar"]).exit_code == 2
    assert runner.invoke(cli.app, ["aprovar", "--lote", "1", "--cobranca", "1"]).exit_code == 2
    r = runner.invoke(cli.app, ["aprovar", "--lote", "1"])
    assert r.exit_code == 0 and "20 cobranças aprovadas" in r.output


def test_rn26_enviar_sem_confirmar_lista_com_email_mascarado_e_nao_envia(ambiente, planilha, monkeypatch):
    _ate_rascunho()
    runner.invoke(cli.app, ["aprovar", "--lote", "1"])

    def nao_deve_chamar(cfg):
        raise AssertionError("o remetente não pode ser criado sem --confirmar")

    monkeypatch.setattr(cli, "_sender", nao_deve_chamar)
    r = runner.invoke(cli.app, ["enviar", "--lote", "1"])
    assert r.exit_code == 0 and "Enviaria 20" in r.output
    assert "***@exemplo.test" in r.output and "cliente01@" not in r.output


def test_enviar_confirmado_sem_smtp_configurado_sai_com_1(ambiente, planilha):
    _ate_rascunho()
    runner.invoke(cli.app, ["aprovar", "--lote", "1"])
    r = runner.invoke(cli.app, ["enviar", "--lote", "1", "--confirmar"])
    assert r.exit_code == 1 and "SMTP_HOST" in r.output
