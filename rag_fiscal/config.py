"""Configuração por variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    modelo_embeddings: str
    modelo_llm: str
    k: int  # quantos trechos vão para o LLM
    rerank: bool  # reordenar com cross-encoder (mais lento, mais preciso)


def carregar() -> Config:
    return Config(
        database_url=os.getenv("DATABASE_URL", "postgresql://rag:rag@localhost:5436/rag_fiscal"),
        modelo_embeddings=os.getenv(
            "RAG_MODELO_EMBEDDINGS", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        ),
        modelo_llm=os.getenv("RAG_MODELO_LLM", "claude-sonnet-5-5"),
        k=int(os.getenv("RAG_K", "6")),
        rerank=os.getenv("RAG_RERANK", "1") == "1",
    )
