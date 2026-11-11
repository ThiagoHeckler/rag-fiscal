"""Tabela NCM (Nomenclatura Comum do Mercosul).

Fonte oficial: Portal Único Siscomex, download em JSON. O arquivo traz uma
lista plana de códigos em vários níveis:

    09          capítulo         "Café, chá, mate e especiarias."
    09.01       posição          "Café, mesmo torrado ou descafeinado; ..."
    0901.2      subposição 1º    "- Café torrado:"
    0901.21.00  item/subitem     "-- Não descafeinado"

A descrição de uma folha ("-- Não descafeinado") sozinha não diz nada. Por
isso cada trecho indexado junta a HIERARQUIA inteira: assim a busca por
"café torrado" encontra o 0901.21.00. Isso é *chunking contextual*: o
trecho carrega o contexto que ele precisa para fazer sentido sozinho.
"""

from __future__ import annotations

import json
import re

from rag_fiscal.modelos import Documento, Trecho

URL_OFICIAL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"


def _digitos(codigo: str) -> str:
    return codigo.replace(".", "")


def _limpar(descricao: str) -> str:
    sem_html = re.sub(r"<[^>]+>", "", descricao)  # a tabela oficial traz <i> e <sup> em algumas descrições
    return re.sub(r"^[\s\-–]+", "", sem_html).rstrip(":").strip()


def formatar(digitos: str) -> str:
    """'09012100' -> '0901.21.00'"""
    return f"{digitos[:4]}.{digitos[4:6]}.{digitos[6:8]}"


def ler(conteudo: bytes | str, url_origem: str = URL_OFICIAL) -> Documento:
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("utf-8-sig")  # o arquivo oficial vem com BOM às vezes
    dados = json.loads(conteudo)
    itens = dados["Nomenclaturas"]
    versao = " | ".join(filter(None, [dados.get("Ato"), dados.get("Data_Ultima_Atualizacao_NCM")]))

    descricao_por_prefixo = {_digitos(i["Codigo"]): _limpar(i["Descricao"]) for i in itens}

    doc = Documento(fonte="NCM", titulo="Tabela NCM", url_origem=url_origem, versao=versao or None)
    for item in itens:
        d = _digitos(item["Codigo"])
        if len(d) != 8:
            continue  # só folhas (8 dígitos) viram trechos; os níveis acima entram como contexto
        # ancestrais: capítulo (2), posição (4), subposições (5, 6), item (7)
        caminho = [descricao_por_prefixo[d[:n]] for n in (2, 4, 5, 6, 7) if d[:n] in descricao_por_prefixo]
        caminho.append(_limpar(item["Descricao"]))
        caminho = [c for i, c in enumerate(caminho) if c and c not in caminho[:i]]  # sem repetições
        doc.trechos.append(
            Trecho(
                referencia=f"NCM {formatar(d)}",
                codigo=d,
                texto=" > ".join(caminho),
            )
        )
    return doc
