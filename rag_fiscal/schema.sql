-- Esquema do RAG fiscal. PostgreSQL 16+ com a extensão pgvector.
--
-- documentos -> de onde veio (RICMS-SC, tabela NCM, tabela CFOP), versão e data
-- trechos    -> os pedaços que a busca devolve: texto, referência citável e vetor

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documentos (
    id           BIGSERIAL   PRIMARY KEY,
    fonte        TEXT        NOT NULL,          -- 'NCM', 'CFOP', 'RICMS-SC'
    titulo       TEXT        NOT NULL,
    url_origem   TEXT        NOT NULL,          -- de onde foi baixado (rastreabilidade)
    versao       TEXT,                          -- ex.: 'Resolução Gecex nº 812/2025'
    baixado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fonte, titulo)
);

CREATE TABLE IF NOT EXISTS trechos (
    id            BIGSERIAL PRIMARY KEY,
    documento_id  BIGINT    NOT NULL REFERENCES documentos (id) ON DELETE CASCADE,
    -- Referência que aparece na citação: 'NCM 0901.21.00', 'CFOP 6.102',
    -- 'RICMS-SC, Anexo 2, art. 15'. É o que o usuário confere na fonte.
    referencia    TEXT      NOT NULL,
    -- Código exato quando existe (NCM/CFOP), para busca direta sem IA.
    codigo        TEXT,
    texto         TEXT      NOT NULL,
    -- Dimensão do modelo de embeddings (paraphrase-multilingual-mpnet-base-v2 = 768).
    -- Trocar de modelo exige recriar a coluna e reindexar tudo.
    embedding     vector(768),
    -- Busca textual em português, gerada pelo próprio banco.
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', referencia || ' ' || texto)) STORED
);

CREATE INDEX IF NOT EXISTS idx_trechos_documento ON trechos (documento_id);
CREATE INDEX IF NOT EXISTS idx_trechos_codigo    ON trechos (codigo);
CREATE INDEX IF NOT EXISTS idx_trechos_tsv       ON trechos USING gin (tsv);
-- HNSW: índice aproximado de vizinhos mais próximos (rápido, ótimo recall).
CREATE INDEX IF NOT EXISTS idx_trechos_embedding ON trechos USING hnsw (embedding vector_cosine_ops);
