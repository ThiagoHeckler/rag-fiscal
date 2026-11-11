"""A cadeia de resposta com um LLM falso: testa a VALIDAÇÃO das citações,
que é o que impede o sistema de devolver resposta sem fonte."""

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda

from rag_fiscal.resposta import SEM_RESPOSTA, RespostaLLM, responder


class RecuperadorFixo(BaseRetriever):
    docs: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.docs


class LLMFalso:
    """Imita llm.with_structured_output(...) devolvendo uma resposta pronta."""

    def __init__(self, saida: RespostaLLM):
        self.saida = saida
        self.prompt_recebido = None

    def with_structured_output(self, _modelo):
        def responder_(prompt_valor):
            self.prompt_recebido = prompt_valor.to_string()
            return self.saida

        return RunnableLambda(responder_)


DOCS = [
    Document(page_content="Alíquota interna de 17%.", metadata={"referencia": "RICMS-SC, art. 26", "url": "u1"}),
    Document(page_content="Café torrado.", metadata={"referencia": "NCM 0901.21.00", "url": "u2"}),
]


def test_resposta_com_citacao_valida():
    llm = LLMFalso(RespostaLLM(resposta="A alíquota é 17% [1].", citacoes=[1], encontrou=True))
    r = responder("qual a alíquota interna?", RecuperadorFixo(docs=DOCS), llm)
    assert r.encontrou and [f["referencia"] for f in r.fontes] == ["RICMS-SC, art. 26"]
    assert "[1] RICMS-SC, art. 26" in llm.prompt_recebido, "os trechos vão numerados no prompt"


def test_citacao_inexistente_e_descartada():
    llm = LLMFalso(RespostaLLM(resposta="x [1] [7]", citacoes=[1, 7], encontrou=True))
    r = responder("pergunta", RecuperadorFixo(docs=DOCS), llm)
    assert [f["n"] for f in r.fontes] == [1]


def test_sem_citacao_valida_vira_nao_encontrei():
    llm = LLMFalso(RespostaLLM(resposta="Resposta inventada.", citacoes=[9], encontrou=True))
    r = responder("pergunta", RecuperadorFixo(docs=DOCS), llm)
    assert not r.encontrou and r.resposta == SEM_RESPOSTA


def test_modelo_diz_que_nao_encontrou():
    llm = LLMFalso(RespostaLLM(resposta="Os trechos não tratam disso.", citacoes=[], encontrou=False))
    r = responder("pergunta fora do tema", RecuperadorFixo(docs=DOCS), llm)
    assert not r.encontrou


def test_busca_vazia_nem_chama_o_llm():
    llm = LLMFalso(RespostaLLM(resposta="x", citacoes=[1], encontrou=True))
    r = responder("pergunta", RecuperadorFixo(docs=[]), llm)
    assert not r.encontrou and llm.prompt_recebido is None
