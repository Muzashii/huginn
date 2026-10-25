-- Huginn — modelo de dados
-- Roda automaticamente na primeira subida do Postgres (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS vector;

-- Chunks da base de conhecimento. Mesmo formato que o nó PGVector do n8n espera
-- (colunas id, text, metadata, embedding). Criamos aqui para fixar a dimensão e o índice.
-- nomic-embed-text = 768 dimensões. Se trocar para text-embedding-3-small, use 1536.
CREATE TABLE IF NOT EXISTS n8n_vectors (
  id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  text      TEXT NOT NULL,
  metadata  JSONB NOT NULL DEFAULT '{}'::jsonb,   -- documento, secao, fonte, atualizado_em, chunk
  embedding vector(768)
);
CREATE INDEX IF NOT EXISTS n8n_vectors_embedding_hnsw
  ON n8n_vectors USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS n8n_vectors_documento
  ON n8n_vectors ((metadata->>'documento'));

CREATE TABLE IF NOT EXISTS ingestoes (
  id        SERIAL PRIMARY KEY,
  documento TEXT NOT NULL,
  chunks    INT,
  hash      TEXT,
  origem    TEXT DEFAULT 'n8n' CHECK (origem IN ('n8n', 'script')),
  em        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingestoes_documento ON ingestoes (documento, id DESC);

CREATE TABLE IF NOT EXISTS conversas (
  chat_id       BIGINT PRIMARY KEY,
  modo          TEXT DEFAULT 'bot' CHECK (modo IN ('bot', 'humano')),
  iniciada_em   TIMESTAMPTZ DEFAULT now(),
  ultima_msg_em TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mensagens (
  id             SERIAL PRIMARY KEY,
  chat_id        BIGINT REFERENCES conversas(chat_id) ON DELETE CASCADE,
  canal          TEXT DEFAULT 'telegram' CHECK (canal IN ('telegram', 'eval')),
  pergunta       TEXT,          -- já mascarada pelo filtro LGPD
  resposta       TEXT,
  fontes         JSONB,
  confianca      TEXT CHECK (confianca IN ('alta', 'media', 'baixa')),
  acao           TEXT CHECK (acao IN ('responder', 'chamar_humano')),
  tokens_entrada INT,           -- estimativa (caracteres / 4), ver docs/decisoes.md
  tokens_saida   INT,
  latencia_ms    INT,
  em             TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mensagens_em ON mensagens (em);

CREATE TABLE IF NOT EXISTS feedback (
  id          SERIAL PRIMARY KEY,
  mensagem_id INT UNIQUE REFERENCES mensagens(id) ON DELETE CASCADE,
  nota        SMALLINT CHECK (nota IN (-1, 1)),
  em          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fila_humana (
  id            SERIAL PRIMARY KEY,
  chat_id       BIGINT,
  motivo        TEXT,           -- sem_base | baixa_confianca | pedido_cliente
  pergunta      TEXT,
  status        TEXT DEFAULT 'aberto' CHECK (status IN ('aberto', 'em_atendimento', 'encerrado')),
  assumido_por  TEXT,
  msg_grupo_id  BIGINT,         -- mensagem do ticket no grupo de atendimento
  aberto_em     TIMESTAMPTZ DEFAULT now(),
  encerrado_em  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS fila_humana_aberta ON fila_humana (chat_id) WHERE status <> 'encerrado';

CREATE TABLE IF NOT EXISTS lacunas_base (
  id          SERIAL PRIMARY KEY,
  pergunta    TEXT,
  origem      TEXT CHECK (origem IN ('feedback_negativo', 'escalonamento')),
  mensagem_id INT REFERENCES mensagens(id) ON DELETE SET NULL,
  resolvida   BOOLEAN DEFAULT false,
  em          TIMESTAMPTZ DEFAULT now()
);

-- Memória do AI Agent (nó Postgres Chat Memory). O n8n criaria sozinho;
-- criamos aqui para o job de retenção poder apagar por sessão.
CREATE TABLE IF NOT EXISTS n8n_chat_histories (
  id         SERIAL PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  message    JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS n8n_chat_histories_session ON n8n_chat_histories (session_id);
