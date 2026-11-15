import logging

from boletos.config import Config
from boletos.logs import configurar_logs
from boletos.privacidade import mascarar_documento, mascarar_email, ocultar


def test_rn30_mascara_de_cpf_cnpj_e_email():
    assert mascarar_documento("11145678900") == "***.456.789-**"
    assert mascarar_documento("111.456.789-00") == "***.456.789-**"
    assert mascarar_documento("11222333000181") == "**.***.333/0001-**"
    assert mascarar_email("joao@dominio.com") == "j***@dominio.com"
    assert mascarar_email("sem-arroba") == "***"


def test_ocultar_troca_segredos_documentos_e_emails():
    texto = "chave=sk-ant-123 cpf 111.444.777-35 mail ana@exemplo.test cnpj 11222333000181"
    limpo = ocultar(texto, ["sk-ant-123"])
    assert "sk-ant-123" not in limpo
    assert "111.444.777-35" not in limpo and "ana@" not in limpo and "0001-81" not in limpo
    assert "***.444.777-**" in limpo and "a***@exemplo.test" in limpo


def test_rn31_log_em_arquivo_nao_guarda_segredo_nem_dado_pessoal(tmp_path):
    cfg = Config(asaas_api_key="chave-asaas-secreta", logs_dir=tmp_path / "logs")
    logger = configurar_logs(cfg)
    logger.info("chamando com %s para 11144477735 e ana@exemplo.test", cfg.asaas_api_key)
    try:
        raise RuntimeError("falha com chave-asaas-secreta")
    except RuntimeError:
        logger.exception("erro inesperado")
    for h in logger.handlers:
        h.flush()
    conteudo = (tmp_path / "logs" / "boletos.log").read_text(encoding="utf-8")
    assert "chave-asaas-secreta" not in conteudo
    assert "11144477735" not in conteudo and "ana@exemplo" not in conteudo
    assert "***.444.777-**" in conteudo
    assert "Traceback" in conteudo


def test_configurar_logs_duas_vezes_nao_duplica_handler(tmp_path):
    cfg = Config(logs_dir=tmp_path / "logs")
    configurar_logs(cfg)
    logger = configurar_logs(cfg)
    assert sum(isinstance(h, logging.FileHandler) for h in logger.handlers) == 1
