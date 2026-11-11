from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Trecho:
    """Um pedaço de documento pronto para indexar."""

    referencia: str
    texto: str
    codigo: str | None = None


@dataclass
class Documento:
    fonte: str
    titulo: str
    url_origem: str
    versao: str | None
    trechos: list[Trecho] = field(default_factory=list)


@dataclass
class Resultado:
    """Um trecho devolvido pela busca, com a pontuação de cada estratégia."""

    id: int
    fonte: str
    referencia: str
    texto: str
    url_origem: str
    pontuacao: float
    posicao_vetor: int | None = None
    posicao_texto: int | None = None
    exato: bool = False
