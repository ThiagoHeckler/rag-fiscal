"""Reordenação (rerank) com cross-encoder.

A busca híbrida é rápida, mas compara pergunta e trecho "de longe": o vetor
de cada um foi calculado separadamente. O cross-encoder lê a pergunta e o
trecho JUNTOS e dá uma nota de relevância. É lento demais para rodar no
banco inteiro, mas ótimo para reordenar os ~40 melhores candidatos que a busca
híbrida trouxe. Padrão comum em RAG: recuperar muito e barato, depois
reordenar pouco e caro.

Modelo: BAAI/bge-reranker-v2-m3 (multilíngue), versão INT8 (~0,6 GB),
local via fastembed. Na CPU, 40 pares de até 600 caracteres levam alguns segundos.
"""

from __future__ import annotations

import os
from typing import Protocol

from rag_fiscal.modelos import Resultado


class Reranker(Protocol):
    def reordenar(self, pergunta: str, candidatos: list[Resultado]) -> list[Resultado]: ...


class CrossEncoderReranker:
    def __init__(self, modelo: str = "BAAI/bge-reranker-v2-m3-int8", max_caracteres: int = 600) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._modelo = TextCrossEncoder(model_name=modelo, threads=os.cpu_count())
        self._max = max_caracteres

    def reordenar(self, pergunta: str, candidatos: list[Resultado]) -> list[Resultado]:
        if not candidatos:
            return []
        textos = [f"{c.referencia}: {c.texto[: self._max]}" for c in candidatos]
        notas = list(self._modelo.rerank(pergunta, textos, batch_size=8))
        for c, nota in zip(candidatos, notas, strict=True):
            c.pontuacao = float(nota)
        return sorted(candidatos, key=lambda c: c.pontuacao, reverse=True)
