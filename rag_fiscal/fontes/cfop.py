"""Tabela CFOP (Código Fiscal de Operações e Prestações).

Fonte oficial: Anexo II do Convênio s/nº de 1970, no PDF publicado pela
SEF-SC (texto extraído com `pdftotext -layout`). Cada código vem com a
NOTA EXPLICATIVA ("Classificam-se neste código..."), que é o que realmente
responde perguntas como "qual CFOP uso para remessa para conserto?".

Formato do texto:
    5.100 - VENDAS DE PRODUÇÃO PRÓPRIA OU DE TERCEIROS      <- grupo
    5.102 - Venda de mercadoria adquirida ou recebida de    <- código
    terceiros, ...
    - Classificam-se neste código as vendas de ...          <- nota explicativa

Cada trecho leva também o GRUPO e o significado do 1º dígito, porque o
usuário pergunta com palavras ("venda para outro estado"), não com código.
"""

from __future__ import annotations

import json
import re

from rag_fiscal.modelos import Documento, Trecho

ABRANGENCIA = {
    "1": "Entrada, operação dentro do estado (estadual)",
    "2": "Entrada, operação de outro estado (interestadual)",
    "3": "Entrada, operação do exterior (importação)",
    "5": "Saída, operação dentro do estado (estadual)",
    "6": "Saída, operação para outro estado (interestadual)",
    "7": "Saída, operação para o exterior (exportação)",
}

RE_CODIGO = re.compile(r"^([1-35-7])\.(\d{3})\s*-\s*(.+)$")
RE_RODAPE = re.compile(r"^(\d{1,3}|ESTADO DE SANTA CATARINA|SECRETARIA DE ESTADO DA FAZENDA|"
                       r"DIRETORIA DE ADMINISTRAÇÃO TRIBUTÁRIA)$")


def formatar(codigo: str) -> str:
    """'6102' -> '6.102'"""
    return f"{codigo[0]}.{codigo[1:]}"


def _juntar(linhas: list[str]) -> str:
    texto = " ".join(linhas)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto.replace(" - Classificam-se", "\nClassificam-se").lstrip("- ")


def ler_texto_oficial(texto: str, url_origem: str, versao: str | None = None) -> Documento:
    doc = Documento(fonte="CFOP", titulo="Tabela CFOP", url_origem=url_origem, versao=versao)
    grupo = ""
    atual: tuple[str, list[str]] | None = None  # (código de 4 dígitos, linhas)

    def fechar() -> None:
        if not atual:
            return
        codigo, linhas = atual
        corpo = _juntar(linhas)
        contexto = f"Grupo {grupo}. " if grupo else ""
        doc.trechos.append(Trecho(
            referencia=f"CFOP {formatar(codigo)}",
            codigo=codigo,
            texto=f"{formatar(codigo)} - {corpo}\n{contexto}({ABRANGENCIA[codigo[0]]})",
        ))

    for bruta in texto.splitlines():
        linha = bruta.strip()
        if not linha or RE_RODAPE.match(linha):
            continue
        m = RE_CODIGO.match(linha)
        if m:
            fechar()
            codigo = m.group(1) + m.group(2)
            if codigo.endswith("00"):  # X.000 e X.X00 são títulos de grupo, não códigos
                grupo = f"{formatar(codigo)} - {re.sub(r'\s+', ' ', m.group(3))}"
                atual = None
            else:
                atual = (codigo, [m.group(3)])
            continue
        if atual:
            atual[1].append(linha)
        elif grupo and not linha.startswith("-") and linha.isupper():
            grupo += " " + linha  # título de grupo quebrado em duas linhas
    fechar()
    return doc


def ler_json(conteudo: bytes | str, url_origem: str, versao: str | None = None) -> Documento:
    """Alternativa: lista simples [{"Codigo": "5102", "Nome": "..."}], sem notas explicativas."""
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("utf-8-sig")
    doc = Documento(fonte="CFOP", titulo="Tabela CFOP", url_origem=url_origem, versao=versao)
    for item in json.loads(conteudo):
        codigo = str(item["Codigo"]).replace(".", "").strip()
        if len(codigo) != 4 or codigo[0] not in ABRANGENCIA:
            continue
        doc.trechos.append(Trecho(
            referencia=f"CFOP {formatar(codigo)}",
            codigo=codigo,
            texto=f"{formatar(codigo)} - {item['Nome'].strip()}\n({ABRANGENCIA[codigo[0]]})",
        ))
    return doc
