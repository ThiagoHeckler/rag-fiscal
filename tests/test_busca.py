from conftest import FIXTURES

from rag_fiscal import banco
from rag_fiscal.fontes import cfop, legislacao, ncm


def test_codigos_na_pergunta():
    assert banco.codigos_na_pergunta("qual o NCM 0901.21.00?") == ["09012100"]
    assert banco.codigos_na_pergunta("posso usar o CFOP 6.102 ou 5102?") == ["6102", "5102"]
    assert banco.codigos_na_pergunta("art. 26 do regulamento") == []


def test_rrf_premia_quem_aparece_nas_duas_listas():
    linha = lambda i: (i, "F", f"ref{i}", "t", "u")  # noqa: E731
    vetorial = [linha(1), linha(2), linha(3)]
    textual = [linha(3), linha(4)]
    fundidos = banco.fundir_rrf(vetorial, textual)
    assert fundidos[0].id == 3, "o 3 aparece nas duas listas e deve vencer"
    assert fundidos[0].posicao_vetor == 3 and fundidos[0].posicao_texto == 1


def _popular(conn, embedder):
    for doc in [
        ncm.ler((FIXTURES / "ncm_amostra.json").read_bytes()),
        cfop.ler_json('[{"Codigo": "5102", "Nome": "Venda de mercadoria adquirida de terceiros"},'
                 ' {"Codigo": "6102", "Nome": "Venda de mercadoria adquirida de terceiros"}]', "u"),
        legislacao.ler((FIXTURES / "ricms_amostra.htm").read_bytes(), "A2", "RICMS-SC, Anexo 2", "u"),
    ]:
        banco.gravar(conn, doc, embedder)


def test_codigo_exato_vem_primeiro(conn, embedder):
    _popular(conn, embedder)
    r = banco.buscar(conn, embedder, "o que é o NCM 2202.10.00?", k=3)
    assert r[0].referencia == "NCM 2202.10.00" and r[0].exato


def test_busca_textual_usa_radical_em_portugues(conn, embedder):
    _popular(conn, embedder)
    # "isentos" e "leites" não aparecem assim no texto; o stemming encontra "isentas"/"leite"
    r = banco.buscar(conn, embedder, "leites isentos", k=3, modo="textual")
    assert r and r[0].referencia == "RICMS-SC, Anexo 2, art. 1º"


def test_reingestao_substitui_sem_duplicar(conn, embedder):
    _popular(conn, embedder)
    _popular(conn, embedder)
    total = conn.execute("SELECT count(*) FROM trechos").fetchone()[0]
    assert total == 11 + 2 + 3  # 11 folhas NCM na amostra, 2 CFOP, 3 artigos


def test_filtro_por_fonte(conn, embedder):
    _popular(conn, embedder)
    r = banco.buscar(conn, embedder, "venda de mercadoria", k=5, fontes=["CFOP"])
    assert r and all(x.fonte == "CFOP" for x in r)


class RerankerInverso:
    """Reranker falso: inverte a ordem, para provar que a etapa é aplicada antes do corte em k."""

    def reordenar(self, pergunta, candidatos):
        return list(reversed(candidatos))


def test_reranker_reordena_mas_codigo_exato_continua_primeiro(conn, embedder):
    _popular(conn, embedder)
    sem = banco.buscar(conn, embedder, "café torrado 0901.21.00", k=20)
    com = banco.buscar(conn, embedder, "café torrado 0901.21.00", k=20, reranker=RerankerInverso())
    assert sem[0].exato and com[0].exato and com[0].id == sem[0].id
    assert [r.id for r in com[1:]] == [r.id for r in reversed(sem[1:])]
