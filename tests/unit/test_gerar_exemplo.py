import importlib.util
from datetime import date
from pathlib import Path
from random import Random

from boletos.lote import analisar
from boletos.validation.documentos import cnpj_valido, cpf_valido

RAIZ = Path(__file__).resolve().parents[2]


def _carregar_script():
    spec = importlib.util.spec_from_file_location("gerar_exemplo", RAIZ / "scripts" / "gerar_exemplo.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_exemplo_tem_20_validas_4_rejeitadas_e_1_repetida(tmp_path, cfg, hoje):
    script = _carregar_script()
    arq = tmp_path / "exemplo.csv"
    script.escrever(arq, hoje, n_validas=20, semente=2026)
    a = analisar(arq, cfg, hoje)
    assert len(a.itens) == 20
    assert len(a.rejeicoes) == 4
    assert [x.tipo for x in a.avisos] == ["duplicada_arquivo"]


def test_documentos_gerados_sao_validos_e_emails_sao_test(tmp_path):
    script = _carregar_script()
    rng = Random(1)
    assert all(cpf_valido(script.gerar_cpf(rng)) for _ in range(50))
    assert all(cnpj_valido(script.gerar_cnpj(rng)) for _ in range(50))
    arq = tmp_path / "x.csv"
    script.escrever(arq, date(2026, 11, 15))
    emails = [linha.split(",")[2] for linha in arq.read_text(encoding="utf-8").splitlines()[1:] if "@" in linha]
    assert emails and all(e.endswith(".test") for e in emails if "sem-arroba" not in e)
