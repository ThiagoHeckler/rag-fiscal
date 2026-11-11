"""Geração de embeddings (texto -> vetor) rodando LOCALMENTE.

Usamos o fastembed (ONNX, sem PyTorch): o modelo é baixado uma vez do
Hugging Face (~1 GB para o mpnet) e depois roda offline, sem custo por
chamada e sem mandar a legislação para uma API externa.

A interface `Embedder` permite trocar por um provedor pago (OpenAI, Voyage)
ou por um falso nos testes, sem mexer no resto.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from typing import Protocol


class Embedder(Protocol):
    dimensao: int

    def documentos(self, textos: Sequence[str]) -> list[list[float]]: ...
    def consulta(self, texto: str) -> list[float]: ...


class FastEmbedder:
    def __init__(self, modelo: str, lote: int = 16, max_tokens: int = 128) -> None:
        from fastembed import TextEmbedding  # import tardio: carregar o modelo é pesado

        # threads=None usa todos os núcleos; sem isso o ONNX ficava num núcleo só
        self._modelo = TextEmbedding(model_name=modelo, threads=os.cpu_count())
        # Os modelos paraphrase-multilingual foram TREINADOS com no máximo 128 tokens.
        # O fastembed usa 512 por padrão no mpnet: além de ~4x mais lento, não melhora
        # a qualidade. Texto além do limite é cortado só no vetor; a busca textual vê tudo.
        tokenizer = getattr(getattr(self._modelo, "model", None), "tokenizer", None)
        if tokenizer is not None:
            tokenizer.enable_truncation(max_length=max_tokens)
        self._lote = lote
        self.nome = modelo
        # Modelos da família E5 foram treinados com prefixos; os demais não usam.
        self._e5 = "e5" in modelo.lower()
        self.dimensao = len(self.consulta("teste"))

    def documentos(self, textos: Sequence[str]) -> list[list[float]]:
        entrada: Iterable[str] = (f"passage: {t}" for t in textos) if self._e5 else textos
        return [v.tolist() for v in self._modelo.embed(list(entrada), batch_size=self._lote)]

    def consulta(self, texto: str) -> list[float]:
        entrada = f"query: {texto}" if self._e5 else texto
        return next(iter(self._modelo.embed([entrada]))).tolist()
