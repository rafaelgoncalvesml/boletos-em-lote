from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal

from boletos.models import LinhaValida, Rejeicao
from boletos.validation.documentos import documento_valido

_PROIBIDO_EM_TEXTO = re.compile(r"https?://|www\.|R\$", re.IGNORECASE)


class ErroCampo(ValueError):
    def __init__(self, coluna: str, motivo: str):
        super().__init__(motivo)
        self.coluna = coluna
        self.motivo = motivo


def normalizar_cabecalho(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def parse_valor(texto: str, maximo_cent: int) -> int:
    t = texto.strip()
    if "," in t:
        if not re.fullmatch(r"(\d{1,3}(\.\d{3})+|\d+),\d+", t, re.ASCII):
            raise ErroCampo("valor", "formato de valor inválido")
        t = t.replace(".", "").replace(",", ".")
    elif not re.fullmatch(r"\d+(\.\d+)?", t, re.ASCII):
        raise ErroCampo("valor", "formato de valor inválido")
    casas = len(t.split(".")[1]) if "." in t else 0
    if casas > 2:
        raise ErroCampo("valor", "valor com mais de duas casas decimais")
    cent = int(Decimal(t) * 100)
    if cent <= 0:
        raise ErroCampo("valor", "valor precisa ser maior que zero")
    if cent > maximo_cent:
        raise ErroCampo("valor", "valor acima do máximo permitido")
    return cent


def parse_data(texto: str) -> date:
    t = texto.strip()
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", t, re.ASCII):
            return datetime.strptime(t, "%d/%m/%Y").date()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t, re.ASCII):
            return date.fromisoformat(t)
    except ValueError:
        raise ErroCampo("vencimento", "data inexistente") from None
    raise ErroCampo("vencimento", "formato de data inválido, use DD/MM/AAAA ou AAAA-MM-DD")


def validar_vencimento(d: date, hoje: date) -> date:
    if d < hoje + timedelta(days=1):
        raise ErroCampo("vencimento", "vencimento precisa ser a partir de amanhã")
    if d > hoje + timedelta(days=365):
        raise ErroCampo("vencimento", "vencimento além de 365 dias")
    return d


def validar_competencia(texto: str) -> str:
    t = texto.strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", t, re.ASCII):
        raise ErroCampo("competencia", "competência precisa estar no formato AAAA-MM")
    return t


# vírgula, ponto e vírgula, <>, () e aspas fariam o cabeçalho To ler outro destinatário
_PARTE_EMAIL = r"[^@\s,;<>()\[\]\":\\]+"
_EMAIL = re.compile(rf"{_PARTE_EMAIL}@{_PARTE_EMAIL}\.{_PARTE_EMAIL}")


def validar_email(texto: str) -> str:
    t = texto.strip()
    if len(t) > 254:
        raise ErroCampo("email", "e-mail com mais de 254 caracteres")
    if not _EMAIL.fullmatch(t):
        raise ErroCampo("email", "e-mail inválido")
    return t


def parse_documento(texto: str) -> str:
    t = re.sub(r"[.\-/\s]", "", texto)
    if not t:
        raise ErroCampo("documento", "documento vazio")
    if not (t.isascii() and t.isdigit()):
        raise ErroCampo("documento", "documento com caracteres inválidos")
    if len(t) not in (11, 14):
        raise ErroCampo("documento", "documento precisa ter 11 (CPF) ou 14 (CNPJ) dígitos")
    if not documento_valido(t):
        raise ErroCampo("documento", "dígitos verificadores do documento não conferem")
    return t


def limpar_texto(coluna: str, texto: str, *, obrigatorio: bool = False, limite: int = 100) -> str:
    t = " ".join(texto.split())
    if obrigatorio and not t:
        raise ErroCampo(coluna, "campo obrigatório vazio")
    if _PROIBIDO_EM_TEXTO.search(t):
        raise ErroCampo(coluna, "texto não pode conter link nem valor em reais")
    return t[:limite]


def validar_linha(
    numero: int, bruto: dict[str, str], hoje: date, valor_maximo_cent: int
) -> tuple[LinhaValida | None, list[Rejeicao]]:
    passos: dict[str, Callable[[str], object]] = {
        "nome": lambda s: limpar_texto("nome", s, obrigatorio=True),
        "documento": parse_documento,
        "email": validar_email,
        "valor": lambda s: parse_valor(s, valor_maximo_cent),
        "vencimento": lambda s: validar_vencimento(parse_data(s), hoje),
        "competencia": validar_competencia,
        "descricao": lambda s: limpar_texto("descricao", s),
    }
    valores: dict[str, object] = {}
    rejeicoes: list[Rejeicao] = []
    for coluna, passo in passos.items():
        try:
            valores[coluna] = passo(bruto.get(coluna, ""))
        except ErroCampo as erro:
            rejeicoes.append(Rejeicao(numero, coluna, erro.motivo))
    if rejeicoes:
        return None, rejeicoes
    return (
        LinhaValida(
            linha=numero,
            nome=valores["nome"],
            documento=valores["documento"],
            email=valores["email"],
            valor_cent=valores["valor"],
            vencimento=valores["vencimento"],
            competencia=valores["competencia"],
            descricao=valores["descricao"],
        ),
        [],
    )
