"""Gera a planilha de exemplo com clientes inventados. E-mails sempre em .test."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
from random import Random

from boletos.validation.documentos import digito_cnpj, digito_cpf

PRENOMES = ["Mariana", "Carlos", "Juliana", "Rafael", "Beatriz", "Tiago", "Larissa", "Otávio", "Helena", "Paulo"]
SOBRENOMES = ["Souza", "Lima", "Pereira", "Almeida", "Ribeiro", "Barros", "Cardoso", "Nogueira", "Teixeira", "Moura"]
SUFIXOS = ["Ltda", "ME", "Consultoria", "Serviços", ""]
DESCRICOES = ["Mensalidade de novembro", "Plano básico", "Manutenção mensal", "Assinatura anual (parcela)", ""]
CABECALHO = ["nome", "documento", "email", "valor", "vencimento", "competencia", "descricao"]


def gerar_cpf(rng: Random) -> str:
    while True:
        base = "".join(str(rng.randint(0, 9)) for _ in range(9))
        if len(set(base)) > 1:
            break
    d1 = digito_cpf(base)
    d2 = digito_cpf(base + str(d1))
    return f"{base}{d1}{d2}"


def gerar_cnpj(rng: Random) -> str:
    base = "".join(str(rng.randint(0, 9)) for _ in range(8)) + "0001"
    d1 = digito_cnpj(base)
    d2 = digito_cnpj(base + str(d1))
    return f"{base}{d1}{d2}"


def _mascarar(doc: str) -> str:
    if len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"


def _reais(cent: int) -> str:
    return f"{cent // 100:,}".replace(",", ".") + f",{cent % 100:02d}"


def _linhas(hoje: date, n_validas: int, rng: Random) -> list[list[str]]:
    competencia = f"{hoje:%Y-%m}"
    vistos: set[str] = set()
    validas: list[list[str]] = []
    for i in range(1, n_validas + 1):
        doc = gerar_cnpj(rng) if i % 4 == 0 else gerar_cpf(rng)
        while doc in vistos:
            doc = gerar_cpf(rng)
        vistos.add(doc)
        nome = f"{rng.choice(PRENOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SUFIXOS)}".strip()
        venc = hoje + timedelta(days=rng.randint(30, 330))
        valor = _reais(rng.randrange(5000, 400000, 50))
        mostrado = _mascarar(doc) if i % 2 == 0 else doc
        validas.append(
            [
                nome,
                mostrado,
                f"cliente{i:02d}@exemplo.test",
                valor,
                venc.strftime("%d/%m/%Y"),
                competencia,
                rng.choice(DESCRICOES),
            ]
        )
    base = validas[0]
    ultimo = base[1][-1]
    doc_ruim = base[1][:-1] + ("0" if ultimo != "0" else "1")  # troca o último dígito: verificador inválido
    ruins = [
        [base[0], doc_ruim, "ruim01@exemplo.test", "100,00", base[4], competencia, ""],
        [
            base[0],
            gerar_cpf(rng),
            "ruim02@exemplo.test",
            "100,00",
            (hoje - timedelta(days=1)).strftime("%d/%m/%Y"),
            competencia,
            "",
        ],
        [base[0], gerar_cpf(rng), "ruim03@exemplo.test", "10,999", base[4], competencia, ""],
        [base[0], gerar_cpf(rng), "sem-arroba.exemplo.test", "100,00", base[4], competencia, ""],
    ]
    repetida = list(validas[2])
    return validas + ruins + [repetida]


def escrever(caminho: Path, hoje: date, n_validas: int = 20, semente: int = 2026) -> None:
    rng = Random(semente)
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arq:
        gravador = csv.writer(arq)
        gravador.writerow(CABECALHO)
        gravador.writerows(_linhas(hoje, n_validas, rng))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", default="sample_data/clientes_exemplo.csv")
    parser.add_argument("--hoje", default=None, help="AAAA-MM-DD, padrão: data de hoje")
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args()
    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()
    escrever(Path(args.saida), hoje, args.n)
    print(f"Gerado {args.saida} com data base {hoje.isoformat()}")


if __name__ == "__main__":
    main()
