"""API HTTP (FastAPI).

GET  /buscar?q=...        só a busca (sem LLM, sem custo) — útil para depurar
POST /perguntar           busca + resposta do LLM com citações
GET  /fontes              o que está indexado, versão e data
GET  /health
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from rag_fiscal import banco, config
from rag_fiscal.embeddings import FastEmbedder
from rag_fiscal.rerank import CrossEncoderReranker
from rag_fiscal.resposta import Resposta, criar_llm, criar_recuperador, responder

estado: dict = {}


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Carrega modelo e conexão UMA vez na subida, não a cada requisição.
    cfg = config.carregar()
    estado["cfg"] = cfg
    estado["conn"] = banco.conectar(cfg.database_url)
    estado["embedder"] = FastEmbedder(cfg.modelo_embeddings)
    estado["reranker"] = CrossEncoderReranker() if cfg.rerank else None
    yield
    estado["conn"].close()


app = FastAPI(title="RAG Fiscal", version="0.1.0", lifespan=ciclo_de_vida)


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=5, max_length=500)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/fontes")
def fontes() -> list[dict]:
    return [
        {"fonte": f, "titulo": t, "versao": v, "trechos": n, "baixado_em": b.isoformat()}
        for f, t, v, n, b in banco.estatisticas(estado["conn"])
    ]


@app.get("/buscar")
def buscar(q: str = Query(min_length=2, max_length=500), k: int = Query(6, ge=1, le=20)) -> list[dict]:
    resultados = banco.buscar(estado["conn"], estado["embedder"], q, k=k, reranker=estado["reranker"])
    return [r.__dict__ for r in resultados]


@app.post("/perguntar")
def perguntar(p: Pergunta) -> Resposta:
    cfg = estado["cfg"]
    try:
        llm = estado.setdefault("llm", criar_llm(cfg.modelo_llm))
    except Exception as exc:  # sem chave, por exemplo
        raise HTTPException(503, f"LLM indisponível: {exc}") from exc
    recuperador = criar_recuperador(estado["conn"], estado["embedder"], cfg.k, estado["reranker"])
    return responder(p.pergunta, recuperador, llm)
