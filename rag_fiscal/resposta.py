"""Geração da resposta com LangChain.

Fluxo:  pergunta ─► Recuperador (busca híbrida) ─► prompt com trechos numerados
                 ─► LLM com saída estruturada ─► validação das citações

Regras que tornam a resposta confiável:
1. O modelo só pode usar os trechos fornecidos (prompt) e precisa citar o
   número [n] de cada trecho usado (saída estruturada).
2. O CÓDIGO confere: citação para um trecho que não existe é removida, e
   resposta sem nenhuma citação válida vira "não encontrei".
3. Se a busca não trouxe nada relevante, o modelo deve responder que não
   encontrou, em vez de responder de memória.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from pydantic import BaseModel, ConfigDict, Field

from rag_fiscal import banco
from rag_fiscal.embeddings import Embedder

SEM_RESPOSTA = "Não encontrei isso nos documentos indexados (RICMS-SC, tabela NCM e tabela CFOP)."


class RecuperadorFiscal(BaseRetriever):
    """Adapta a busca híbrida para a interface de Retriever do LangChain.

    Com isso o recuperador funciona em qualquer chain/agente do LangChain ou
    como ferramenta num grafo LangGraph (ex.: o Auditor NF-e).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    conn: Any
    embedder: Any
    reranker: Any = None
    k: int = 6

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        return [
            Document(
                page_content=r.texto,
                metadata={"id": r.id, "fonte": r.fonte, "referencia": r.referencia, "url": r.url_origem,
                          "exato": r.exato, "pontuacao": r.pontuacao},
            )
            for r in banco.buscar(self.conn, self.embedder, query, k=self.k, reranker=self.reranker)
        ]


class RespostaLLM(BaseModel):
    resposta: str = Field(description="Resposta objetiva em português, com [n] após cada afirmação")
    citacoes: list[int] = Field(description="Números dos trechos usados")
    encontrou: bool = Field(description="False se os trechos não respondem à pergunta")


class Resposta(BaseModel):
    pergunta: str
    resposta: str
    fontes: list[dict]
    encontrou: bool


PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Você é um assistente de legislação tributária para escritórios de contabilidade em Santa Catarina.\n"
     "Responda SOMENTE com base nos trechos numerados abaixo. Não use conhecimento próprio.\n"
     "Depois de cada afirmação, coloque o número do trecho entre colchetes, ex.: [2].\n"
     "Se os trechos não responderem à pergunta, diga isso e marque encontrou=false.\n"
     "Seja objetivo. Quando houver código (NCM, CFOP) ou artigo, cite-o.\n"
     "Lembre o usuário de conferir a redação vigente quando a resposta depender de prazo ou alíquota."),
    ("human", "Trechos:\n{contexto}\n\nPergunta: {pergunta}"),
])


def formatar_contexto(docs: list[Document]) -> str:
    return "\n\n".join(f"[{i}] {d.metadata['referencia']}\n{d.page_content}" for i, d in enumerate(docs, start=1))


def responder(pergunta: str, recuperador: BaseRetriever, llm: BaseChatModel) -> Resposta:
    docs = recuperador.invoke(pergunta)
    if not docs:
        return Resposta(pergunta=pergunta, resposta=SEM_RESPOSTA, fontes=[], encontrou=False)

    cadeia = PROMPT | llm.with_structured_output(RespostaLLM)
    saida: RespostaLLM = cadeia.invoke({"contexto": formatar_contexto(docs), "pergunta": pergunta})

    validas = sorted({n for n in saida.citacoes if 1 <= n <= len(docs)})
    if not saida.encontrou or not validas:
        return Resposta(pergunta=pergunta, resposta=SEM_RESPOSTA, fontes=[], encontrou=False)

    fontes = [
        {"n": n, "referencia": docs[n - 1].metadata["referencia"], "url": docs[n - 1].metadata["url"],
         "trecho": docs[n - 1].page_content[:500]}
        for n in validas
    ]
    return Resposta(pergunta=pergunta, resposta=saida.resposta, fontes=fontes, encontrou=True)


def criar_llm(modelo: str) -> BaseChatModel:
    import os

    from langchain_anthropic import ChatAnthropic

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("defina ANTHROPIC_API_KEY para gerar respostas (a rota /buscar funciona sem)")

    return ChatAnthropic(model=modelo, temperature=0, max_tokens=1500)


def criar_recuperador(conn: Any, embedder: Embedder, k: int, reranker: Any = None) -> RecuperadorFiscal:
    return RecuperadorFiscal(conn=conn, embedder=embedder, k=k, reranker=reranker)
