from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class EmbedderFalso:
    """Embedding determinístico por palavras (hashing), sem baixar modelo.

    Não entende sinônimos como um modelo real, mas palavras em comum geram
    vetores próximos, o que basta para testar o encanamento da busca.
    """

    dimensao = 768

    def _vetor(self, texto: str) -> list[float]:
        v = [0.0] * self.dimensao
        for palavra in re.findall(r"\w{3,}", texto.lower()):
            v[int(hashlib.md5(palavra.encode()).hexdigest(), 16) % self.dimensao] += 1.0
        norma = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norma for x in v]

    def documentos(self, textos):
        return [self._vetor(t) for t in textos]

    def consulta(self, texto):
        return self._vetor(texto)


@pytest.fixture
def embedder():
    return EmbedderFalso()


@pytest.fixture
def conn():
    """Banco real (PostgreSQL + pgvector). Defina DATABASE_URL_TESTE para rodar.

    Usa um schema temporário para não tocar nos dados de verdade.
    """
    url = os.getenv("DATABASE_URL_TESTE")
    if not url:
        pytest.skip("defina DATABASE_URL_TESTE para os testes com banco")
    from rag_fiscal import banco

    c = banco.conectar(url)
    c.execute("DROP SCHEMA IF EXISTS teste_rag CASCADE")
    c.execute("CREATE SCHEMA teste_rag")
    c.execute("SET search_path TO teste_rag, public")
    banco.criar_schema(c)
    yield c
    c.execute("DROP SCHEMA teste_rag CASCADE")
    c.close()
