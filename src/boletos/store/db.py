from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from boletos.erros import BancoIndisponivel, TransicaoInvalida
from boletos.models import TRANSICOES, Cobranca, Estado, LinhaValida, Rejeicao

CAMPOS_GATEWAY = ("id_cliente_gw", "id_cobranca_gw", "link_boleto", "linha_digitavel")


def _relogio_padrao() -> datetime:
    return datetime.now(UTC)


def _cobranca(r: sqlite3.Row) -> Cobranca:
    return Cobranca(
        id=r["id"],
        lote_id=r["lote_id"],
        chave_idem=r["chave_idem"],
        cliente_nome=r["cliente_nome"],
        cliente_doc=r["cliente_doc"],
        cliente_email=r["cliente_email"],
        competencia=r["competencia"],
        valor_cent=r["valor_cent"],
        vencimento=r["vencimento"],
        descricao=r["descricao"],
        estado=Estado(r["estado"]),
        etapa_falha=r["etapa_falha"],
        id_cliente_gw=r["id_cliente_gw"],
        id_cobranca_gw=r["id_cobranca_gw"],
        link_boleto=r["link_boleto"],
        linha_digitavel=r["linha_digitavel"],
        criado_em=r["criado_em"],
        atualizado_em=r["atualizado_em"],
    )


class Banco:
    def __init__(self, con: sqlite3.Connection, relogio: Callable[[], datetime] = _relogio_padrao):
        self.con = con
        self._relogio = relogio
        self._nivel = 0

    @classmethod
    def abrir(cls, caminho: Path | str, relogio: Callable[[], datetime] | None = None) -> Banco:
        try:
            con = sqlite3.connect(str(caminho), timeout=5)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys = ON")
            banco = cls(con, relogio or _relogio_padrao)
            banco._migrar()
        except sqlite3.Error as erro:
            raise BancoIndisponivel(f"Não foi possível abrir o banco {caminho}: {erro}") from erro
        return banco

    def close(self) -> None:
        self.con.close()

    def _migrar(self) -> None:
        atual = self.con.execute("PRAGMA user_version").fetchone()[0]
        pasta = resources.files("boletos.store") / "migrations"
        arquivos = sorted((p for p in pasta.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name)
        for arq in arquivos:
            numero = int(arq.name.split("_")[0])
            if numero > atual:
                sql = arq.read_text(encoding="utf-8")
                self.con.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {numero};\nCOMMIT;")

    @contextmanager
    def transacao(self) -> Iterator[None]:
        self._nivel += 1
        try:
            yield
        except BaseException:
            self._nivel -= 1
            if self._nivel == 0:
                self.con.rollback()
            raise
        else:
            self._nivel -= 1
            if self._nivel == 0:
                self.con.commit()

    def _agora(self) -> str:
        return self._relogio().isoformat(timespec="seconds")

    # lotes e rejeições

    def criar_lote(self, arquivo: str, hash_arquivo: str, linhas_lidas: int, linhas_rejeitadas: int) -> int:
        with self.transacao():
            cur = self.con.execute(
                "INSERT INTO lotes (arquivo, hash_arquivo, linhas_lidas, linhas_rejeitadas, criado_em)"
                " VALUES (?,?,?,?,?)",
                (arquivo, hash_arquivo, linhas_lidas, linhas_rejeitadas, self._agora()),
            )
            return cur.lastrowid

    def obter_lote(self, lote_id: int) -> dict | None:
        r = self.con.execute("SELECT * FROM lotes WHERE id = ?", (lote_id,)).fetchone()
        return dict(r) if r else None

    def lote_por_hash(self, hash_arquivo: str) -> int | None:
        r = self.con.execute(
            "SELECT id FROM lotes WHERE hash_arquivo = ? ORDER BY id DESC LIMIT 1", (hash_arquivo,)
        ).fetchone()
        return r["id"] if r else None

    def inserir_rejeicao(self, lote_id: int, rej: Rejeicao) -> None:
        with self.transacao():
            self.con.execute(
                "INSERT INTO rejeicoes (lote_id, linha, coluna, motivo) VALUES (?,?,?,?)",
                (lote_id, rej.linha, rej.coluna, rej.motivo),
            )

    def rejeicoes(self, lote_id: int) -> list[Rejeicao]:
        linhas = self.con.execute(
            "SELECT linha, coluna, motivo FROM rejeicoes WHERE lote_id = ? ORDER BY id", (lote_id,)
        )
        return [Rejeicao(r["linha"], r["coluna"], r["motivo"]) for r in linhas]

    # cobranças

    def inserir_cobranca(self, lote_id: int, linha: LinhaValida, chave: str) -> Cobranca:
        agora = self._agora()
        with self.transacao():
            cur = self.con.execute(
                "INSERT INTO cobrancas (lote_id, chave_idem, cliente_nome, cliente_doc, cliente_email,"
                " competencia, valor_cent, vencimento, descricao, estado, criado_em, atualizado_em)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    lote_id,
                    chave,
                    linha.nome,
                    linha.documento,
                    linha.email,
                    linha.competencia,
                    linha.valor_cent,
                    linha.vencimento.isoformat(),
                    linha.descricao,
                    Estado.VALIDADA.value,
                    agora,
                    agora,
                ),
            )
            self._evento(lote_id, cur.lastrowid, "importada", None, Estado.VALIDADA.value, f"linha {linha.linha}")
            return self.obter(cur.lastrowid)

    def obter(self, cobranca_id: int) -> Cobranca:
        r = self.con.execute("SELECT * FROM cobrancas WHERE id = ?", (cobranca_id,)).fetchone()
        if r is None:
            raise KeyError(f"cobrança {cobranca_id} não existe")
        return _cobranca(r)

    def listar(self, lote_id: int, estado: Estado | None = None) -> list[Cobranca]:
        if estado is None:
            linhas = self.con.execute("SELECT * FROM cobrancas WHERE lote_id = ? ORDER BY id", (lote_id,))
        else:
            linhas = self.con.execute(
                "SELECT * FROM cobrancas WHERE lote_id = ? AND estado = ? ORDER BY id", (lote_id, estado.value)
            )
        return [_cobranca(r) for r in linhas]

    def buscar_por_chave(self, chave: str) -> Cobranca | None:
        r = self.con.execute("SELECT * FROM cobrancas WHERE chave_idem = ?", (chave,)).fetchone()
        return _cobranca(r) if r else None

    def buscar_por_doc_competencia(self, doc: str, competencia: str) -> list[Cobranca]:
        linhas = self.con.execute(
            "SELECT * FROM cobrancas WHERE cliente_doc = ? AND competencia = ? ORDER BY id", (doc, competencia)
        )
        return [_cobranca(r) for r in linhas]

    def contar_por_estado(self, lote_id: int) -> dict[str, int]:
        linhas = self.con.execute(
            "SELECT estado, COUNT(*) AS n FROM cobrancas WHERE lote_id = ? GROUP BY estado", (lote_id,)
        )
        return {r["estado"]: r["n"] for r in linhas}

    def id_cliente_por_doc(self, doc: str) -> str | None:
        r = self.con.execute(
            "SELECT id_cliente_gw FROM cobrancas WHERE cliente_doc = ? AND id_cliente_gw IS NOT NULL LIMIT 1",
            (doc,),
        ).fetchone()
        return r["id_cliente_gw"] if r else None

    def definir_cliente_gw(self, cobranca_id: int, id_cliente: str) -> None:
        with self.transacao():
            self.con.execute(
                "UPDATE cobrancas SET id_cliente_gw = ?, atualizado_em = ? WHERE id = ?",
                (id_cliente, self._agora(), cobranca_id),
            )

    def transicionar(
        self, cobranca_id: int, novo: Estado, *, detalhe: str = "", etapa_falha: str | None = None, **campos: str
    ) -> Cobranca:
        invalidos = set(campos) - set(CAMPOS_GATEWAY)
        if invalidos:
            raise ValueError(f"campos não permitidos: {sorted(invalidos)}")
        if novo == Estado.ERRO and not etapa_falha:
            raise ValueError("etapa_falha é obrigatória ao ir para erro")
        with self.transacao():
            atual = self.obter(cobranca_id)
            if novo not in TRANSICOES[atual.estado]:
                raise TransicaoInvalida(f"{atual.estado.value} para {novo.value} não é permitido")
            sets = ["estado = ?", "etapa_falha = ?", "atualizado_em = ?"]
            valores: list[object] = [novo.value, etapa_falha if novo == Estado.ERRO else None, self._agora()]
            for nome, valor in campos.items():  # nomes vêm da lista fixa acima, nunca do usuário
                sets.append(f"{nome} = ?")
                valores.append(valor)
            valores.append(cobranca_id)
            self.con.execute(f"UPDATE cobrancas SET {', '.join(sets)} WHERE id = ?", valores)
            self._evento(atual.lote_id, cobranca_id, f"estado_{novo.value}", atual.estado.value, novo.value, detalhe)
        return self.obter(cobranca_id)

    # eventos

    def _evento(
        self,
        lote_id: int | None,
        cobranca_id: int | None,
        tipo: str,
        antes: str | None,
        depois: str | None,
        detalhe: str,
    ) -> None:
        self.con.execute(
            "INSERT INTO eventos (lote_id, cobranca_id, tipo, estado_antes, estado_depois, detalhe, em)"
            " VALUES (?,?,?,?,?,?,?)",
            (lote_id, cobranca_id, tipo, antes, depois, detalhe, self._agora()),
        )

    def registrar_evento(
        self,
        lote_id: int | None,
        tipo: str,
        detalhe: str = "",
        *,
        cobranca_id: int | None = None,
        antes: str | None = None,
        depois: str | None = None,
    ) -> None:
        with self.transacao():
            self._evento(lote_id, cobranca_id, tipo, antes, depois, detalhe)

    def eventos(self, lote_id: int) -> list[dict]:
        linhas = self.con.execute("SELECT * FROM eventos WHERE lote_id = ? ORDER BY id", (lote_id,))
        return [dict(r) for r in linhas]

    def lote_pausado(self, lote_id: int) -> bool:
        r = self.con.execute(
            "SELECT tipo FROM eventos WHERE lote_id = ? AND tipo IN ('lote_pausado','lote_retomado')"
            " ORDER BY id DESC LIMIT 1",
            (lote_id,),
        ).fetchone()
        return bool(r and r["tipo"] == "lote_pausado")

    def chamadas_claude_hoje(self) -> int:
        hoje = self._relogio().date().isoformat()
        r = self.con.execute(
            "SELECT COUNT(*) AS n FROM eventos WHERE tipo = 'chamada_claude' AND substr(em, 1, 10) = ?", (hoje,)
        ).fetchone()
        return r["n"]

    def motivo_erro(self, cobranca_id: int) -> str:
        r = self.con.execute(
            "SELECT detalhe FROM eventos WHERE cobranca_id = ? AND estado_depois = 'erro' ORDER BY id DESC LIMIT 1",
            (cobranca_id,),
        ).fetchone()
        return r["detalhe"] if r else ""

    # envios

    def salvar_envio(self, cobranca_id: int, caminho: str, assunto: str, origem: str) -> None:
        with self.transacao():
            self.con.execute(
                "INSERT INTO envios (cobranca_id, caminho_rascunho, assunto, origem_texto) VALUES (?,?,?,?)"
                " ON CONFLICT(cobranca_id) DO UPDATE SET caminho_rascunho = excluded.caminho_rascunho,"
                " assunto = excluded.assunto, origem_texto = excluded.origem_texto, erro = NULL",
                (cobranca_id, caminho, assunto, origem),
            )

    def obter_envio(self, cobranca_id: int) -> dict | None:
        r = self.con.execute("SELECT * FROM envios WHERE cobranca_id = ?", (cobranca_id,)).fetchone()
        return dict(r) if r else None

    def marcar_aprovado(self, cobranca_id: int) -> None:
        with self.transacao():
            self.con.execute("UPDATE envios SET aprovado_em = ? WHERE cobranca_id = ?", (self._agora(), cobranca_id))

    def marcar_enviado(self, cobranca_id: int) -> None:
        with self.transacao():
            self.con.execute(
                "UPDATE envios SET enviado_em = ?, erro = NULL WHERE cobranca_id = ?", (self._agora(), cobranca_id)
            )

    def registrar_erro_envio(self, cobranca_id: int, erro: str) -> None:
        with self.transacao():
            self.con.execute("UPDATE envios SET erro = ? WHERE cobranca_id = ?", (erro[:500], cobranca_id))
