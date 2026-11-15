from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from boletos.erros import ErroConfig

URL_SANDBOX_ASAAS = "https://api-sandbox.asaas.com/v3"
MODELO_PADRAO = "claude-haiku-5-5"


@dataclass(frozen=True)
class Config:
    asaas_api_key: str | None = None
    asaas_base_url: str = URL_SANDBOX_ASAAS
    anthropic_api_key: str | None = None
    claude_model: str = MODELO_PADRAO
    max_claude_calls_dia: int = 200
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str = "cobranca@exemplo.test"
    valor_maximo_cent: int = 5_000_000
    linhas_por_lote: int = 500
    pausa_entre_req_ms: int = 300
    falhas_para_pausar: int = 5
    db_path: Path = Path("boletos.db")
    rascunhos_dir: Path = Path("rascunhos")
    logs_dir: Path = Path("logs")

    def segredos(self) -> list[str]:
        return [s for s in (self.asaas_api_key, self.anthropic_api_key, self.smtp_pass) if s]


def ler_dotenv(caminho: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not caminho.is_file():
        return valores
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valores[chave.strip()] = valor.strip().strip("'\"")
    return valores


def _inteiro(env: Mapping[str, str], nome: str, padrao: int, minimo: int = 0) -> int:
    bruto = env.get(nome)
    if bruto is None or bruto == "":
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise ErroConfig(f"{nome} precisa ser um número inteiro") from None
    if valor < minimo:
        raise ErroConfig(f"{nome} precisa ser pelo menos {minimo}")
    return valor


def _texto(env: Mapping[str, str], nome: str) -> str | None:
    valor = env.get(nome)
    return valor if valor else None


def carregar(env: Mapping[str, str] | None = None, arquivo: Path | None = Path(".env")) -> Config:
    base: dict[str, str] = dict(ler_dotenv(arquivo)) if arquivo else {}
    base.update(os.environ if env is None else env)
    porta = _inteiro(base, "SMTP_PORT", 0)
    return Config(
        asaas_api_key=_texto(base, "ASAAS_API_KEY"),
        asaas_base_url=_texto(base, "ASAAS_BASE_URL") or URL_SANDBOX_ASAAS,
        anthropic_api_key=_texto(base, "ANTHROPIC_API_KEY"),
        claude_model=_texto(base, "CLAUDE_MODEL") or MODELO_PADRAO,
        max_claude_calls_dia=_inteiro(base, "MAX_CLAUDE_CALLS_DIA", 200),
        smtp_host=_texto(base, "SMTP_HOST"),
        smtp_port=porta or None,
        smtp_user=_texto(base, "SMTP_USER"),
        smtp_pass=_texto(base, "SMTP_PASS"),
        smtp_from=_texto(base, "SMTP_FROM") or "cobranca@exemplo.test",
        valor_maximo_cent=_inteiro(base, "VALOR_MAXIMO_CENT", 5_000_000, minimo=1),
        linhas_por_lote=_inteiro(base, "LINHAS_POR_LOTE", 500, minimo=1),
        pausa_entre_req_ms=_inteiro(base, "PAUSA_ENTRE_REQ_MS", 300),
        falhas_para_pausar=_inteiro(base, "FALHAS_PARA_PAUSAR", 5, minimo=1),
        db_path=Path(_texto(base, "BOLETOS_DB") or "boletos.db"),
        rascunhos_dir=Path(_texto(base, "BOLETOS_RASCUNHOS") or "rascunhos"),
        logs_dir=Path(_texto(base, "BOLETOS_LOGS") or "logs"),
    )


def exigir_para(cfg: Config, comando: str, *, gateway: str = "fake", confirmar: bool = False) -> None:
    faltam: list[str] = []
    if comando == "emitir" and gateway == "asaas" and not cfg.asaas_api_key:
        faltam.append("ASAAS_API_KEY")
    if comando == "enviar" and confirmar:
        if not cfg.smtp_host:
            faltam.append("SMTP_HOST")
        if not cfg.smtp_port:
            faltam.append("SMTP_PORT")
        if bool(cfg.smtp_user) != bool(cfg.smtp_pass):
            faltam.append("SMTP_PASS" if cfg.smtp_user else "SMTP_USER")
    if faltam:
        raise ErroConfig("Faltam variáveis de ambiente: " + ", ".join(faltam))
