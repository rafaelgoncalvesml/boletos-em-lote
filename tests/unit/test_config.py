import pytest

from boletos.config import carregar, exigir_para
from boletos.erros import ErroConfig


def test_padroes_da_planta():
    cfg = carregar(env={}, arquivo=None)
    assert cfg.valor_maximo_cent == 5_000_000
    assert cfg.linhas_por_lote == 500
    assert cfg.pausa_entre_req_ms == 300
    assert cfg.falhas_para_pausar == 5
    assert cfg.max_claude_calls_dia == 200
    assert "sandbox" in cfg.asaas_base_url
    assert cfg.claude_model == "claude-haiku-5-5"


def test_variaveis_sobrescrevem_padroes():
    cfg = carregar(env={"LINHAS_POR_LOTE": "10", "SMTP_PORT": "1025"}, arquivo=None)
    assert cfg.linhas_por_lote == 10
    assert cfg.smtp_port == 1025


def test_inteiro_invalido_diz_qual_variavel():
    with pytest.raises(ErroConfig, match="LINHAS_POR_LOTE"):
        carregar(env={"LINHAS_POR_LOTE": "dez"}, arquivo=None)


def test_ambiente_vence_o_dotenv(tmp_path):
    arq = tmp_path / ".env"
    arq.write_text('LINHAS_POR_LOTE=7\nASAAS_API_KEY="abc"\n# comentario\n\n', encoding="utf-8")
    cfg = carregar(env={"LINHAS_POR_LOTE": "9"}, arquivo=arq)
    assert cfg.linhas_por_lote == 9
    assert cfg.asaas_api_key == "abc"


def test_asaas_exige_chave_antes_de_tocar_no_banco():
    cfg = carregar(env={}, arquivo=None)
    with pytest.raises(ErroConfig, match="ASAAS_API_KEY"):
        exigir_para(cfg, "emitir", gateway="asaas")
    exigir_para(cfg, "emitir", gateway="fake")


def test_envio_confirmado_exige_smtp():
    cfg = carregar(env={}, arquivo=None)
    exigir_para(cfg, "enviar", confirmar=False)
    with pytest.raises(ErroConfig, match="SMTP_HOST"):
        exigir_para(cfg, "enviar", confirmar=True)
    meio = carregar(env={"SMTP_HOST": "localhost", "SMTP_PORT": "1025", "SMTP_USER": "u"}, arquivo=None)
    with pytest.raises(ErroConfig, match="SMTP_PASS"):
        exigir_para(meio, "enviar", confirmar=True)


def test_segredos_lista_so_o_que_existe():
    cfg = carregar(env={"ASAAS_API_KEY": "k1", "SMTP_PASS": "p1"}, arquivo=None)
    assert sorted(cfg.segredos()) == ["k1", "p1"]
