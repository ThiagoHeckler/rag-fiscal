from conftest import FIXTURES

from rag_fiscal.fontes import cfop, legislacao, ncm


def test_ncm_so_folhas_com_hierarquia_completa():
    doc = ncm.ler((FIXTURES / "ncm_amostra.json").read_bytes())
    refs = {t.referencia: t for t in doc.trechos}

    assert "NCM 0901.21.00" in refs
    assert all(len(t.codigo) == 8 for t in doc.trechos), "só códigos de 8 dígitos viram trechos"
    texto = refs["NCM 0901.21.00"].texto
    # a folha "-- Não descafeinado" sozinha não diz nada; com a hierarquia, diz
    assert "Café" in texto and "torrado" in texto and "Não descafeinado" in texto
    assert not texto.startswith("-")
    assert "Gecex" in doc.versao


def test_cfop_formata_e_explica_o_primeiro_digito():
    doc = cfop.ler_json('[{"Codigo": "6102", "Nome": "Venda de mercadoria adquirida de terceiros"},'
                   ' {"Codigo": "abc", "Nome": "lixo"}]', url_origem="x")
    assert len(doc.trechos) == 1
    t = doc.trechos[0]
    assert t.referencia == "CFOP 6.102"
    assert "outro estado" in t.texto


def test_cfop_texto_oficial_com_nota_explicativa_e_grupo():
    texto = (FIXTURES / "cfop_amostra.txt").read_text()
    doc = cfop.ler_texto_oficial(texto, "url")
    refs = {t.referencia: t.texto for t in doc.trechos}
    assert list(refs) == ["CFOP 5.101", "CFOP 5.102", "CFOP 6.108"], "títulos de grupo (X.X00) não viram código"
    assert "Classificam-se neste código as vendas de mercadorias adquiridas" in refs["CFOP 5.102"]
    assert "Grupo 5.100 - VENDAS DE PRODUÇÃO PRÓPRIA OU DE TERCEIROS" in refs["CFOP 5.102"]
    assert "ESTADO DE SANTA CATARINA" not in refs["CFOP 5.102"], "cabeçalho de página fica fora"
    assert "não contribuinte" in refs["CFOP 6.108"] and "outro estado" in refs["CFOP 6.108"]


def test_legislacao_divide_por_artigo_com_contexto_e_sem_notas():
    doc = legislacao.ler((FIXTURES / "ricms_amostra.htm").read_bytes(), "Anexo 2", "RICMS-SC, Anexo 2", "url")
    refs = [t.referencia for t in doc.trechos]
    assert refs == ["RICMS-SC, Anexo 2, art. 1º", "RICMS-SC, Anexo 2, art. 2º-A", "RICMS-SC, Anexo 2, art. 7º"]

    art1 = doc.trechos[0].texto
    assert "leite fresco" in art1 and "ovos" in art1
    assert "NÃO deve ser indexado" not in art1, "notas e redação passada ficam fora"
    assert "DAS ISENÇÕES" in art1 and "Das Operações com Mercadorias" in art1

    art7 = doc.trechos[2].texto
    assert "DA REDUÇÃO DA BASE DE CÁLCULO" in art7 and "§ 1º" in art7
    assert "Seção I" not in art7, "seção do capítulo anterior não pode vazar"


def test_artigo_longo_e_dividido_e_cada_parte_continua_citavel():
    corpo = "\n".join(f"{i} - inciso número {i} com bastante texto para ocupar espaço na linha." for i in range(80))
    trechos = legislacao.dividir_em_artigos([f"Art. 5º Ficam isentas: {corpo}"], "RICMS-SC")
    assert len(trechos) > 1
    assert all(t.texto.startswith("RICMS-SC, art. 5º") for t in trechos)
    assert trechos[0].referencia.endswith(f"(parte 1/{len(trechos)})")
