import importlib.util
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from boletos import cli
from boletos.gateway.fake import FakeGateway

pytestmark = pytest.mark.integration
runner = CliRunner()
RAIZ = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location("gerar_exemplo", RAIZ / "scripts" / "gerar_exemplo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for var in ("ASAAS_API_KEY", "ANTHROPIC_API_KEY", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BOLETOS_DB", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BOLETOS_RASCUNHOS", str(tmp_path / "rascunhos"))
    monkeypatch.setenv("BOLETOS_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("PAUSA_ENTRE_REQ_MS", "0")
    return tmp_path


@pytest.fixture
def planilha(ambiente):
    caminho = ambiente / "clientes.csv"
    _script().escrever(caminho, date.today())
    return caminho


def test_importar_dry_run_lista_rejeicoes_e_nao_cria_lote(ambiente, planilha):
    r = runner.invoke(cli.app, ["importar", str(planilha), "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "20" in r.output and "rejeitadas" in r.output
    assert "linha" in r.output and "coluna" in r.output
    r2 = runner.invoke(cli.app, ["relatorio", "--lote", "1"])
    assert r2.exit_code == 2


def test_importar_emitir_relatorio_com_gateway_fake(ambiente, planilha):
    assert runner.invoke(cli.app, ["importar", str(planilha)]).exit_code == 0
    r = runner.invoke(cli.app, ["emitir", "--lote", "1"])
    assert r.exit_code == 0, r.output
    assert "emitida: 20" in r.output
    md = runner.invoke(cli.app, ["relatorio", "--lote", "1"])
    assert "Valor total emitido" in md.output
    csv_ = runner.invoke(cli.app, ["relatorio", "--lote", "1", "--formato", "csv"])
    assert csv_.output.startswith("secao,chave,valor,detalhe")


def test_importar_com_coluna_faltando_sai_com_2_sem_lote(ambiente):
    ruim = ambiente / "ruim.csv"
    ruim.write_text("nome,documento\nAna,1\n", encoding="utf-8")
    r = runner.invoke(cli.app, ["importar", str(ruim)])
    assert r.exit_code == 2 and "Faltam colunas" in r.output


def test_emitir_asaas_sem_chave_falha_antes_de_criar_o_banco(ambiente):
    r = runner.invoke(cli.app, ["emitir", "--lote", "1", "--gateway", "asaas"])
    assert r.exit_code == 1 and "ASAAS_API_KEY" in r.output
    assert not (ambiente / "cli.db").exists()


def test_banco_ilegivel_sai_com_1_e_mensagem_curta(ambiente, monkeypatch):
    monkeypatch.setenv("BOLETOS_DB", str(ambiente))  # diretório no lugar do arquivo
    r = runner.invoke(cli.app, ["emitir", "--lote", "1"])
    assert r.exit_code == 1 and "banco" in r.output.lower()
    assert "Traceback" not in r.output


def test_rn16_lote_pausado_sai_com_3_e_retomar_conclui(ambiente, planilha, monkeypatch):
    runner.invoke(cli.app, ["importar", str(planilha)])
    gw = FakeGateway(["perm"] * 5)  # uma instância só: o roteiro de falhas é consumido ao longo das três execuções
    monkeypatch.setattr(cli, "_gateway", lambda nome, cfg: gw)
    assert runner.invoke(cli.app, ["emitir", "--lote", "1"]).exit_code == 3
    assert runner.invoke(cli.app, ["emitir", "--lote", "1"]).exit_code == 3  # sem --retomar recusa
    r = runner.invoke(cli.app, ["emitir", "--lote", "1", "--retomar"])
    assert r.exit_code == 0, r.output
    assert "emitida: 15" in r.output and "erro: 5" in r.output


def test_rn17_credencial_recusada_sai_com_1(ambiente, planilha, monkeypatch):
    runner.invoke(cli.app, ["importar", str(planilha)])
    monkeypatch.setattr(cli, "_gateway", lambda nome, cfg: FakeGateway(["credencial"]))
    r = runner.invoke(cli.app, ["emitir", "--lote", "1"])
    assert r.exit_code == 1 and "chave de API" in r.output


def test_reprocessar_cobranca_que_nao_esta_em_erro_sai_com_2(ambiente, planilha):
    runner.invoke(cli.app, ["importar", str(planilha)])
    r = runner.invoke(cli.app, ["reprocessar", "--cobranca", "1"])
    assert r.exit_code == 2


def test_gateway_desconhecido_sai_com_2(ambiente, planilha):
    runner.invoke(cli.app, ["importar", str(planilha)])
    r = runner.invoke(cli.app, ["emitir", "--lote", "1", "--gateway", "outro"])
    assert r.exit_code == 2
