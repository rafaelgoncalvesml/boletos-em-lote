"""Roda o fluxo inteiro com o gateway fake em ./demo, sem enviar e-mail."""

import os
import subprocess
import sys
from pathlib import Path

PASTA = Path("demo")
AMBIENTE = {
    **os.environ,
    "BOLETOS_DB": str(PASTA / "demo.db"),
    "BOLETOS_RASCUNHOS": str(PASTA / "rascunhos"),
    "BOLETOS_LOGS": str(PASTA / "logs"),
    "PYTHONIOENCODING": "utf-8",
}


def boletos(*args: str) -> int:
    print(f"\n$ boletos {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, "-m", "boletos.cli", *args], env=AMBIENTE).returncode


def main() -> None:
    PASTA.mkdir(exist_ok=True)
    (PASTA / "demo.db").unlink(missing_ok=True)
    planilha = str(PASTA / "clientes.csv")
    subprocess.run([sys.executable, "scripts/gerar_exemplo.py", "--saida", planilha], check=True)
    for passo in (
        ["importar", planilha],
        ["emitir", "--lote", "1"],
        ["rascunhos", "--lote", "1", "--sem-claude"],
        ["aprovar", "--lote", "1"],
        ["enviar", "--lote", "1"],
    ):
        if boletos(*passo):
            sys.exit(1)
    print("\nPronto. Abra demo/rascunhos/1/00001.eml. O envio de verdade pede --confirmar e um SMTP de captura.")


if __name__ == "__main__":
    main()
