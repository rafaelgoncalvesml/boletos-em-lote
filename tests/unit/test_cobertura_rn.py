import re
from pathlib import Path

EXIGIDAS = {f"{n:02d}" for n in [*range(3, 12), *range(15, 21)]}  # RN-03 a RN-11 e RN-15 a RN-20


# Só prova que existe um teste com o nome da regra, não que ele cubra o caso difícil.
def test_cada_regra_exigida_pelos_criterios_de_aceite_tem_pelo_menos_um_teste():
    pasta = Path(__file__).resolve().parents[1]
    achadas: set[str] = set()
    for arq in pasta.rglob("test_*.py"):
        achadas |= set(re.findall(r"def test_rn(\d{2})_", arq.read_text(encoding="utf-8")))
    assert EXIGIDAS - achadas == set(), f"regras sem teste: {sorted(EXIGIDAS - achadas)}"
