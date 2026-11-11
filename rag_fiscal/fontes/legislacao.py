"""Legislação (RICMS-SC) dividida por ARTIGO, com o contexto de capítulo e seção.

Por que por artigo e não a cada N caracteres?
- O artigo é a unidade que o contador cita ("RICMS-SC, Anexo 2, art. 1º").
- Um corte cego por tamanho separa o caput dos incisos e a resposta perde
  o sentido.

Cada trecho leva junto o capítulo e a seção onde o artigo está (ex.:
"CAPÍTULO I – DAS ISENÇÕES / Seção I – Das Operações com Mercadorias").
Muitos artigos só fazem sentido com esse contexto: o art. 1º do Anexo 2
lista produtos sem nunca repetir a palavra "isenção".

Sobre o HTML da SEF-SC: cada parágrafo tem uma classe CSS. Usamos só a
redação atual ("redaoatual*") e os títulos; descartamos notas e redações
passadas, que contam o histórico do texto e confundiriam a resposta.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_fiscal.modelos import Documento, Trecho

MAX_CARACTERES = 1000
SOBREPOSICAO = 150

RE_ARTIGO = re.compile(r"^Art\.\s*(\d+)\s*(?:º|°|o)?\s*(-\s*[A-Z])?\s*\.?\s*")
RE_CAPITULO = re.compile(r"^CAP[ÍI]TULO\s+[IVXLC]+", re.IGNORECASE)
RE_SECAO = re.compile(r"^(Sub)?[Ss]e[çc][ãa]o\s+[IVXLC]+")

CLASSES_DESCARTADAS = ("nota", "redaopassada", "versao")

_divisor = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CARACTERES,
    chunk_overlap=SOBREPOSICAO,
    # tenta quebrar entre parágrafos (§), depois entre incisos/linhas, depois em frase
    separators=["\n§", "\n", "; ", ". ", " "],
)


def paragrafos(html: str | bytes) -> list[str]:
    sopa = BeautifulSoup(html, "lxml")
    linhas = []
    for p in sopa.find_all("p"):
        classe = " ".join(p.get("class") or []).lower()
        if any(classe.startswith(c) for c in CLASSES_DESCARTADAS):
            continue
        texto = " ".join(p.get_text(" ").split())
        if texto:
            linhas.append(texto)
    return linhas


def _numero(m: re.Match) -> str:
    sufixo = (m.group(2) or "").replace(" ", "")
    n = int(m.group(1))
    return f"{n}{'º' if n < 10 else ''}{sufixo}"


def dividir_em_artigos(linhas: list[str], prefixo: str) -> list[Trecho]:
    """prefixo: ex. 'RICMS-SC' ou 'RICMS-SC, Anexo 2'."""
    trechos: list[Trecho] = []
    capitulo = secao = ""
    pendente_titulo: str | None = None  # "CAPÍTULO I" vem numa linha e o nome na seguinte
    artigo: tuple[str, str, list[str]] | None = None  # (número, contexto, linhas)

    def fechar() -> None:
        if not artigo:
            return
        numero, contexto, corpo_linhas = artigo
        corpo = "\n".join(corpo_linhas).strip()
        if not corpo:
            return
        ref = f"{prefixo}, art. {numero}"
        cab = f"{ref}{f' ({contexto})' if contexto else ''}"
        pedacos = _divisor.split_text(corpo) if len(corpo) > MAX_CARACTERES else [corpo]
        for i, pedaco in enumerate(pedacos, start=1):
            sufixo = f" (parte {i}/{len(pedacos)})" if len(pedacos) > 1 else ""
            trechos.append(Trecho(referencia=ref + sufixo, texto=f"{cab}:\n{pedaco}"))

    for linha in linhas:
        if pendente_titulo is not None:
            if pendente_titulo == "capitulo":
                capitulo = f"{capitulo} – {linha}"
            else:
                secao = f"{secao} – {linha}"
            pendente_titulo = None
            continue
        if RE_CAPITULO.match(linha):
            fechar()
            artigo = None
            capitulo, secao = linha, ""
            pendente_titulo = "capitulo" if len(linha) < 20 else None
            continue
        if RE_SECAO.match(linha):
            fechar()
            artigo = None
            secao = linha
            pendente_titulo = "secao" if len(linha) < 20 else None
            continue
        m = RE_ARTIGO.match(linha)
        if m:
            fechar()
            contexto = " / ".join(filter(None, [capitulo, secao]))
            artigo = (_numero(m), contexto, [linha[m.end():]])
            continue
        if artigo:
            artigo[2].append(linha)
    fechar()
    return trechos


def ler(html: str | bytes, titulo: str, prefixo: str, url_origem: str, versao: str | None = None) -> Documento:
    doc = Documento(fonte=prefixo.split(",")[0], titulo=titulo, url_origem=url_origem, versao=versao)
    doc.trechos = dividir_em_artigos(paragrafos(html), prefixo)
    return doc
