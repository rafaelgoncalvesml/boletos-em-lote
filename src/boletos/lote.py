from __future__ import annotations

import hashlib
import logging
import smtplib
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from boletos.config import Config
from boletos.erros import CredencialRecusada, EntradaRecusada, LotePausado
from boletos.gateway.base import BillingGateway, ErroCredencial, ErroPermanente, ErroTemporario
from boletos.ingest.planilha import ler_planilha
from boletos.mail.composer import Email, Redator, montar_email
from boletos.mail.sender import Sender
from boletos.models import Cliente, Cobranca, Emissao, Estado, LinhaValida, Rejeicao, chave_da_linha
from boletos.store.db import Banco
from boletos.validation.regras import validar_linha

log = logging.getLogger("boletos")


@dataclass(frozen=True)
class Aviso:
    tipo: str
    linha: int
    texto: str


@dataclass(frozen=True)
class ItemAnalise:
    linha: int
    dados: LinhaValida
    chave: str


@dataclass
class Analise:
    linhas_lidas: int
    itens: list[ItemAnalise] = field(default_factory=list)
    rejeicoes: list[Rejeicao] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)


def analisar(caminho: Path, cfg: Config, hoje: date) -> Analise:
    planilha = ler_planilha(caminho, cfg.linhas_por_lote)
    analise = Analise(linhas_lidas=len(planilha.linhas))
    por_chave: dict[str, int] = {}
    por_doc_competencia: dict[tuple[str, str], int] = {}
    for numero, bruto in planilha.linhas:
        dados, rejeicoes = validar_linha(numero, bruto, hoje, cfg.valor_maximo_cent)
        if dados is None:
            analise.rejeicoes.extend(rejeicoes)
            continue
        chave = chave_da_linha(dados)
        if chave in por_chave:
            analise.avisos.append(
                Aviso("duplicada_arquivo", numero, f"linha {numero} repete a linha {por_chave[chave]} e foi ignorada")
            )
            continue
        par = (dados.documento, dados.competencia)
        if par in por_doc_competencia:
            analise.avisos.append(
                Aviso(
                    "competencia_repetida",
                    numero,
                    f"linha {numero}: mesmo documento e competência da linha {por_doc_competencia[par]}, "
                    "com valor ou vencimento diferente (possível duplicidade)",
                )
            )
        por_chave[chave] = numero
        por_doc_competencia.setdefault(par, numero)
        analise.itens.append(ItemAnalise(numero, dados, chave))
    return analise


@dataclass
class ResultadoImportacao:
    lote_id: int | None
    linhas_lidas: int
    criadas: list[Cobranca]
    existentes: list[tuple[int, Cobranca]]
    novas: int
    rejeicoes: list[Rejeicao]
    avisos: list[Aviso]
    arquivo_repetido: int | None
    dry_run: bool


def _hash_arquivo(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def importar(banco: Banco, caminho: Path, cfg: Config, hoje: date, *, dry_run: bool = False) -> ResultadoImportacao:
    analise = analisar(caminho, cfg, hoje)  # recusa o arquivo inteiro antes de gravar qualquer coisa
    hash_arquivo = _hash_arquivo(caminho)
    repetido = banco.lote_por_hash(hash_arquivo)
    avisos = list(analise.avisos)
    if repetido is not None:
        avisos.append(Aviso("arquivo_repetido", 0, f"este arquivo já foi importado no lote {repetido}"))

    if dry_run:
        novas = sum(1 for item in analise.itens if banco.buscar_por_chave(item.chave) is None)
        return ResultadoImportacao(None, analise.linhas_lidas, [], [], novas, analise.rejeicoes, avisos, repetido, True)

    criadas: list[Cobranca] = []
    existentes: list[tuple[int, Cobranca]] = []
    ids_por_linha: dict[int, int] = {}
    with banco.transacao():
        lote_id = banco.criar_lote(Path(caminho).name, hash_arquivo, analise.linhas_lidas, len(analise.rejeicoes))
        for rej in analise.rejeicoes:
            banco.inserir_rejeicao(lote_id, rej)
        for item in analise.itens:
            ja_existe = banco.buscar_por_chave(item.chave)
            if ja_existe is not None:
                existentes.append((item.linha, ja_existe))
                continue
            de_outros_lotes = [
                c
                for c in banco.buscar_por_doc_competencia(item.dados.documento, item.dados.competencia)
                if c.lote_id != lote_id
            ]
            nova = banco.inserir_cobranca(lote_id, item.dados, item.chave)
            criadas.append(nova)
            ids_por_linha[item.linha] = nova.id
            if de_outros_lotes:
                texto = (
                    f"linha {item.linha}: o documento já tem cobrança em {item.dados.competencia} "
                    f"(cobrança {de_outros_lotes[0].id}) com valor ou vencimento diferente"
                )
                avisos.append(Aviso("competencia_repetida", item.linha, texto))
                banco.registrar_evento(lote_id, "aviso_competencia_repetida", texto, cobranca_id=nova.id)
        for aviso in analise.avisos:
            if aviso.tipo == "competencia_repetida" and aviso.linha in ids_por_linha:
                banco.registrar_evento(
                    lote_id, "aviso_competencia_repetida", aviso.texto, cobranca_id=ids_por_linha[aviso.linha]
                )
        banco.registrar_evento(lote_id, "lote_importado", f"{len(criadas)} criadas, {len(existentes)} já existiam")
    return ResultadoImportacao(
        lote_id, analise.linhas_lidas, criadas, existentes, len(criadas), analise.rejeicoes, avisos, repetido, False
    )


ESPERAS_S = (1, 3, 9)


@dataclass
class ResultadoEmissao:
    emitidas: int = 0
    erros: int = 0
    pausado: bool = False


def _com_repeticao(acao: Callable[[], str], dormir: Callable[[float], None]) -> str:
    ultimo: ErroTemporario | None = None
    for espera in (0, *ESPERAS_S):
        if espera:
            dormir(espera)
        try:
            return acao()
        except ErroTemporario as erro:
            ultimo = erro
    raise ultimo


def _emitir_com_tentativas(gw: BillingGateway, cobranca: Cobranca, dormir: Callable[[float], None]) -> Emissao:
    ultimo: ErroTemporario | None = None
    for espera in (0, *ESPERAS_S):
        if espera:
            dormir(espera)
        try:
            # RN-11: consulta antes de todo POST, o primeiro inclusive. Uma execução interrompida entre o POST
            # e o commit, ou um reprocessar depois de tentativas esgotadas, deixa um boleto já criado no provedor.
            achada = gw.buscar_por_referencia(cobranca.chave_idem)
            if achada is not None:
                return achada
            return gw.emitir(cobranca)
        except ErroTemporario as erro:
            ultimo = erro
    # a última tentativa pode ter criado o boleto e perdido a resposta
    try:
        achada = gw.buscar_por_referencia(cobranca.chave_idem)
    except ErroTemporario:
        raise ultimo from None
    if achada is not None:
        return achada
    raise ultimo


def _emitir_uma(banco: Banco, gw: BillingGateway, c: Cobranca, dormir: Callable[[float], None]) -> None:
    if c.id_cobranca_gw and c.link_boleto:  # reprocessamento: o boleto já existe no provedor
        banco.transicionar(c.id, Estado.EMITIDA, detalhe="boleto já existia no provedor")
        return
    id_cliente = c.id_cliente_gw or banco.id_cliente_por_doc(c.cliente_doc)
    if not id_cliente:
        cliente = Cliente(c.cliente_nome, c.cliente_doc, c.cliente_email)
        id_cliente = _com_repeticao(lambda: gw.criar_cliente(cliente), dormir)
    banco.definir_cliente_gw(c.id, id_cliente)
    emissao = _emitir_com_tentativas(gw, replace(c, id_cliente_gw=id_cliente), dormir)
    banco.transicionar(
        c.id,
        Estado.EMITIDA,
        id_cliente_gw=id_cliente,
        id_cobranca_gw=emissao.id_gw,
        link_boleto=emissao.link,
        linha_digitavel=emissao.linha_digitavel,
        detalhe=f"boleto {emissao.id_gw}",
    )


def emitir(
    banco: Banco,
    gateway: BillingGateway,
    lote_id: int,
    cfg: Config,
    *,
    retomar: bool = False,
    dormir: Callable[[float], None] = time.sleep,
) -> ResultadoEmissao:
    if banco.lote_pausado(lote_id):
        if not retomar:
            raise LotePausado("O lote está pausado por falhas seguidas. Confira o provedor e use --retomar.")
        banco.registrar_evento(lote_id, "lote_retomado")
    resultado = ResultadoEmissao()
    seguidas = 0
    for i, c in enumerate(banco.listar(lote_id, Estado.VALIDADA)):
        if i > 0 and cfg.pausa_entre_req_ms:
            dormir(cfg.pausa_entre_req_ms / 1000)
        try:
            _emitir_uma(banco, gateway, c, dormir)
            resultado.emitidas += 1
            seguidas = 0
        except ErroCredencial as erro:
            banco.registrar_evento(lote_id, "credencial_recusada", str(erro), cobranca_id=c.id)
            raise CredencialRecusada("O provedor recusou a chave de API. Confira ASAAS_API_KEY.") from erro
        except (ErroPermanente, ErroTemporario) as erro:
            banco.transicionar(c.id, Estado.ERRO, etapa_falha="emitir", detalhe=str(erro))
            log.warning("cobrança %s falhou na emissão: %s", c.id, erro)
            resultado.erros += 1
            seguidas += 1
            if seguidas >= cfg.falhas_para_pausar:
                banco.registrar_evento(lote_id, "lote_pausado", f"{seguidas} falhas seguidas")
                resultado.pausado = True
                break
    return resultado


def reprocessar(banco: Banco, cobranca_id: int) -> Cobranca:
    c = banco.obter(cobranca_id)
    if c.estado != Estado.ERRO:
        raise EntradaRecusada(f"A cobrança {cobranca_id} está em {c.estado.value}; só cobrança em erro é reprocessada.")
    return banco.transicionar(cobranca_id, Estado.VALIDADA, detalhe="reprocessar")


@dataclass
class ResultadoRascunhos:
    gerados: int = 0
    pelo_claude: int = 0
    modelo_fixo: int = 0
    erros: int = 0


def _gravar_eml(pasta: Path, c: Cobranca, email: Email, remetente: str) -> Path:
    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = c.cliente_email  # levanta ValueError se tiver quebra de linha (injeção de cabeçalho)
    msg["Subject"] = email.assunto
    msg["X-Boletos-Origem"] = email.origem
    msg.set_content(email.corpo, charset="utf-8", cte="quoted-printable")
    caminho = pasta / f"{c.id:05d}.eml"
    caminho.write_bytes(msg.as_bytes())
    return caminho


def gerar_rascunhos(banco: Banco, lote_id: int, cfg: Config, redator: Redator | None) -> ResultadoRascunhos:
    pasta = cfg.rascunhos_dir / str(lote_id)
    pasta.mkdir(parents=True, exist_ok=True)
    resultado = ResultadoRascunhos()
    teto_avisado = False
    for c in banco.listar(lote_id, Estado.EMITIDA):
        usar = redator
        if usar is not None and banco.chamadas_claude_hoje() >= cfg.max_claude_calls_dia:
            usar = None
            if not teto_avisado:
                banco.registrar_evento(lote_id, "fallback_modelo", "teto diário de chamadas ao Claude atingido")
                teto_avisado = True
        if usar is not None:
            banco.registrar_evento(lote_id, "chamada_claude", cobranca_id=c.id)
        email = montar_email(c, usar)
        if email.fallback:
            banco.registrar_evento(lote_id, "fallback_modelo", email.fallback, cobranca_id=c.id)
        try:
            caminho = _gravar_eml(pasta, c, email, cfg.smtp_from)
        except (OSError, ValueError) as erro:
            banco.transicionar(c.id, Estado.ERRO, etapa_falha="rascunho", detalhe=str(erro)[:200])
            resultado.erros += 1
            continue
        with banco.transacao():
            banco.salvar_envio(c.id, str(caminho), email.assunto, email.origem)
            banco.transicionar(c.id, Estado.RASCUNHO, detalhe=f"origem={email.origem}")
        resultado.gerados += 1
        if email.origem == "claude":
            resultado.pelo_claude += 1
        else:
            resultado.modelo_fixo += 1
    return resultado


def aprovar(banco: Banco, *, lote_id: int | None = None, cobranca_id: int | None = None) -> int:
    if (lote_id is None) == (cobranca_id is None):
        raise EntradaRecusada("Informe --lote ou --cobranca, só um dos dois.")
    if cobranca_id is not None:
        try:
            c = banco.obter(cobranca_id)
        except KeyError:
            raise EntradaRecusada(f"A cobrança {cobranca_id} não existe.") from None
        if c.estado != Estado.RASCUNHO:
            raise EntradaRecusada(f"A cobrança {cobranca_id} está em {c.estado.value}; só rascunho pode ser aprovado.")
        alvos = [c]
    else:
        alvos = banco.listar(lote_id, Estado.RASCUNHO)
    for c in alvos:
        with banco.transacao():
            banco.transicionar(c.id, Estado.APROVADA, detalhe="aprovada pelo usuário")
            banco.marcar_aprovado(c.id)
    return len(alvos)


@dataclass
class ResultadoEnvio:
    previstas: list[int]
    enviadas: int = 0
    falhas: int = 0
    reenvios: int = 0
    confirmado: bool = False


def enviar(
    banco: Banco, lote_id: int, sender: Sender | None, *, confirmar: bool = False, reenviar: bool = False
) -> ResultadoEnvio:
    alvos = banco.listar(lote_id, Estado.APROVADA)
    if reenviar:
        alvos += banco.listar(lote_id, Estado.ENVIADA)
    resultado = ResultadoEnvio(previstas=[c.id for c in alvos], confirmado=confirmar)
    if not confirmar:
        return resultado
    if sender is None:
        raise ValueError("sender é obrigatório com confirmar=True")
    for c in alvos:
        envio = banco.obter_envio(c.id)
        try:
            if envio is None:
                raise OSError("cobrança sem rascunho gravado")
            sender.enviar(Path(envio["caminho_rascunho"]))
        except (OSError, smtplib.SMTPException) as erro:
            banco.registrar_evento(lote_id, "erro_envio", str(erro)[:200], cobranca_id=c.id)
            if envio is not None:
                banco.registrar_erro_envio(c.id, str(erro))
            resultado.falhas += 1
            continue
        with banco.transacao():
            if c.estado == Estado.APROVADA:
                banco.transicionar(c.id, Estado.ENVIADA, detalhe="e-mail enviado")
            else:
                banco.registrar_evento(lote_id, "reenvio", "e-mail reenviado", cobranca_id=c.id)
                resultado.reenvios += 1
            banco.marcar_enviado(c.id)
        resultado.enviadas += 1
    return resultado
