"""Gravação e busca no PostgreSQL + pgvector.

A busca é HÍBRIDA, porque cada estratégia sozinha falha em casos típicos:

| Pergunta                                | Vetorial (sentido) | Textual (palavras) |
|-----------------------------------------|--------------------|--------------------|
| "venda para outro estado"               | acha o 6.102       | pode falhar        |
| "art. 15 do anexo 2"                    | fraca              | acha               |
| "0901.21.00"                            | fraca              | acha               |

1. Código exato (NCM/CFOP digitado na pergunta): devolvido primeiro.
2. Vetorial: distância de cosseno no pgvector (índice HNSW).
3. Textual: full-text search do Postgres em português (stemming:
   "vendas" encontra "venda").
2 e 3 são combinadas por RRF (Reciprocal Rank Fusion): cada trecho ganha
1/(60 + posição) em cada lista. Isso dispensa normalizar pontuações de
escalas diferentes, porque só a posição importa.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg
from pgvector.psycopg import register_vector

from rag_fiscal.embeddings import Embedder
from rag_fiscal.modelos import Documento, Resultado

if TYPE_CHECKING:
    from rag_fiscal.rerank import Reranker

SCHEMA = Path(__file__).with_name("schema.sql")
RRF_K = 60
CANDIDATOS = 60  # quantos trechos cada estratégia traz antes da fusão (medido: 30 deixava o certo de fora)
REORDENAR = 40  # quantos dos fundidos vão para o reranker (custo cresce linear com isso)

RE_NCM = re.compile(r"\b(\d{4})\.?(\d{2})\.?(\d{2})\b")
RE_CFOP = re.compile(r"\b([1-35-7])\.?(\d{3})\b")


def conectar(database_url: str) -> psycopg.Connection:
    conn = psycopg.connect(database_url, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def criar_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA.read_text())


def gravar(conn: psycopg.Connection, doc: Documento, embedder: Embedder, lote: int = 256) -> int:
    """Substitui o documento inteiro (reingestão idempotente) numa transação."""
    with conn.transaction():
        conn.execute("DELETE FROM documentos WHERE fonte = %s AND titulo = %s", (doc.fonte, doc.titulo))
        doc_id = conn.execute(
            "INSERT INTO documentos (fonte, titulo, url_origem, versao) VALUES (%s, %s, %s, %s) RETURNING id",
            (doc.fonte, doc.titulo, doc.url_origem, doc.versao),
        ).fetchone()[0]
        for i in range(0, len(doc.trechos), lote):
            parte = doc.trechos[i : i + lote]
            vetores = embedder.documentos([f"{t.referencia}: {t.texto}" for t in parte])
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO trechos (documento_id, referencia, codigo, texto, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::vector)",
                    [(doc_id, t.referencia, t.codigo, t.texto, v) for t, v in zip(parte, vetores, strict=True)],
                )
    return len(doc.trechos)


def existe(conn: psycopg.Connection, doc: Documento) -> bool:
    return conn.execute(
        "SELECT 1 FROM documentos WHERE fonte = %s AND titulo = %s", (doc.fonte, doc.titulo)
    ).fetchone() is not None


# Palavras que aparecem em quase toda pergunta e só atrapalham a busca textual.
PALAVRAS_VAZIAS = {"qual", "quais", "como", "posso", "devo", "uso", "usar", "fazer", "código", "codigo",
                   "ncm", "cfop", "icms", "nota", "fiscal", "imposto"}


def fontes_da_pergunta(pergunta: str) -> list[str] | None:
    """Roteamento simples: quem pergunta "qual o NCM..." quer a tabela NCM."""
    p = pergunta.lower()
    if re.search(r"\bncm\b", p):
        return ["NCM"]
    if re.search(r"\bcfop\b", p):
        return ["CFOP"]
    return None


def consulta_textual(pergunta: str) -> str:
    termos = [t for t in re.findall(r"\w{3,}", pergunta.lower()) if t not in PALAVRAS_VAZIAS]
    return " or ".join(termos) or pergunta


def codigos_na_pergunta(pergunta: str) -> list[str]:
    codigos = ["".join(m.groups()) for m in RE_NCM.finditer(pergunta)]
    sem_ncm = RE_NCM.sub(" ", pergunta)
    codigos += [m.group(1) + m.group(2) for m in RE_CFOP.finditer(sem_ncm)]
    return codigos


def buscar(
    conn: psycopg.Connection,
    embedder: Embedder,
    pergunta: str,
    k: int = 6,
    modo: str = "hibrida",
    fontes: list[str] | None = None,
    rotear: bool = True,
    reranker: Reranker | None = None,
) -> list[Resultado]:
    """modo: 'hibrida' (padrão), 'vetorial' ou 'textual' (os dois últimos existem para a avaliação).

    rotear: se a pergunta fala em NCM ou CFOP e nenhuma fonte foi pedida, busca só nela.
    reranker: se informado, reordena os candidatos com um cross-encoder antes de cortar em k.
    """
    if fontes is None and rotear:
        fontes = fontes_da_pergunta(pergunta)
    filtro = "AND d.fonte = ANY(%(fontes)s)" if fontes else ""
    base = f"""SELECT t.id, d.fonte, t.referencia, t.texto, d.url_origem
               FROM trechos t JOIN documentos d ON d.id = t.documento_id WHERE TRUE {filtro}"""
    params: dict = {"fontes": fontes, "n": CANDIDATOS}

    exatos: list[Resultado] = []
    codigos = codigos_na_pergunta(pergunta)
    if codigos:
        for linha in conn.execute(base + " AND t.codigo = ANY(%(codigos)s)", {**params, "codigos": codigos}):
            exatos.append(Resultado(*linha, pontuacao=1.0, exato=True))

    vetorial: list[tuple] = []
    if modo in ("hibrida", "vetorial"):
        params["vetor"] = embedder.consulta(pergunta)
        vetorial = conn.execute(
            base + " ORDER BY t.embedding <=> %(vetor)s::vector LIMIT %(n)s", params
        ).fetchall()

    textual: list[tuple] = []
    if modo in ("hibrida", "textual"):
        # websearch_to_tsquery aceita texto livre; 'OR' entre termos dá recall melhor
        # que exigir todas as palavras (perguntas têm palavras que não estão no texto).
        params["q"] = consulta_textual(pergunta)
        textual = conn.execute(
            base
            + " AND t.tsv @@ websearch_to_tsquery('portuguese', %(q)s)"
            " ORDER BY ts_rank_cd(t.tsv, websearch_to_tsquery('portuguese', %(q)s)) DESC, t.id LIMIT %(n)s",
            params,
        ).fetchall()

    fundidos = fundir_rrf(vetorial, textual)
    vistos = {r.id for r in exatos}
    candidatos = [r for r in fundidos if r.id not in vistos]
    if reranker is not None:
        candidatos = reranker.reordenar(pergunta, candidatos[:REORDENAR])
    return (exatos + candidatos)[:k]


def fundir_rrf(vetorial: list[tuple], textual: list[tuple]) -> list[Resultado]:
    por_id: dict[int, Resultado] = {}
    for lista, campo in ((vetorial, "posicao_vetor"), (textual, "posicao_texto")):
        for pos, linha in enumerate(lista, start=1):
            r = por_id.setdefault(linha[0], Resultado(*linha, pontuacao=0.0))
            r.pontuacao += 1.0 / (RRF_K + pos)
            setattr(r, campo, pos)
    return sorted(por_id.values(), key=lambda r: r.pontuacao, reverse=True)


def estatisticas(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(
        """SELECT d.fonte, d.titulo, d.versao, count(t.id), d.baixado_em
           FROM documentos d LEFT JOIN trechos t ON t.documento_id = d.id
           GROUP BY d.id ORDER BY d.fonte"""
    ).fetchall()
