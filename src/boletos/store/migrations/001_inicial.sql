CREATE TABLE lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo TEXT NOT NULL,
    hash_arquivo TEXT NOT NULL,
    linhas_lidas INTEGER NOT NULL,
    linhas_rejeitadas INTEGER NOT NULL,
    criado_em TEXT NOT NULL
);

CREATE TABLE cobrancas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES lotes(id),
    chave_idem TEXT NOT NULL UNIQUE,
    cliente_nome TEXT NOT NULL,
    cliente_doc TEXT NOT NULL,
    cliente_email TEXT NOT NULL,
    competencia TEXT NOT NULL,
    valor_cent INTEGER NOT NULL CHECK (valor_cent > 0),
    vencimento TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL CHECK (estado IN ('validada','emitida','rascunho','aprovada','enviada','erro')),
    etapa_falha TEXT CHECK (etapa_falha IN ('importar','emitir','rascunho','envio')),
    id_cliente_gw TEXT,
    id_cobranca_gw TEXT,
    link_boleto TEXT,
    linha_digitavel TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX idx_cobrancas_lote ON cobrancas(lote_id, estado);
CREATE INDEX idx_cobrancas_doc_comp ON cobrancas(cliente_doc, competencia);

CREATE TABLE rejeicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES lotes(id),
    linha INTEGER NOT NULL,
    coluna TEXT NOT NULL,
    motivo TEXT NOT NULL
);

CREATE TABLE envios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cobranca_id INTEGER NOT NULL UNIQUE REFERENCES cobrancas(id),
    caminho_rascunho TEXT NOT NULL,
    assunto TEXT NOT NULL,
    origem_texto TEXT NOT NULL CHECK (origem_texto IN ('claude','modelo_fixo')),
    aprovado_em TEXT,
    enviado_em TEXT,
    erro TEXT
);

CREATE TABLE eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER REFERENCES lotes(id),
    cobranca_id INTEGER REFERENCES cobrancas(id),
    tipo TEXT NOT NULL,
    estado_antes TEXT,
    estado_depois TEXT,
    detalhe TEXT NOT NULL DEFAULT '',
    em TEXT NOT NULL
);
CREATE INDEX idx_eventos_lote ON eventos(lote_id, id);
CREATE INDEX idx_eventos_tipo_em ON eventos(tipo, em);
