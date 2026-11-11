"""De onde cada documento vem. Um lugar só para auditar as fontes."""

from __future__ import annotations

BASE_RICMS = "https://legislacao.sef.sc.gov.br/html/regulamentos/icms"

# arquivo -> (título, prefixo da citação)
RICMS_SC = {
    "ricms_01_00": ("RICMS-SC (Decreto 2.870/2001) – texto principal", "RICMS-SC"),
    "ricms_01_02": ("RICMS-SC – Anexo 2 – Benefícios Fiscais", "RICMS-SC, Anexo 2"),
    "ricms_01_03": ("RICMS-SC – Anexo 3 – Substituição Tributária", "RICMS-SC, Anexo 3"),
    "ricms_01_05": ("RICMS-SC – Anexo 5 – Obrigações Acessórias", "RICMS-SC, Anexo 5"),
    "ricms_01_06": ("RICMS-SC – Anexo 6 – Regimes Especiais", "RICMS-SC, Anexo 6"),
    "ricms_01_11": ("RICMS-SC – Anexo 11 – NF-e", "RICMS-SC, Anexo 11"),
}
# Fora da v1, de propósito: Anexo 1 (listas de mercadorias em tabela; precisa de
# um leitor de tabelas) e anexos 4, 7, 8, 9, 10 (equipamentos, ECF, códigos).

NCM_URL = "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"

# Tabela CFOP oficial: Anexo II do Convênio s/nº de 1970, em PDF publicado pela SEF-SC.
# O texto é extraído com `pdftotext -layout` (pacote poppler-utils).
CFOP_URL = "https://www.sef.sc.gov.br/api-portal/Documento/ver/4941"
CFOP_VERSAO = "Anexo II do Convênio s/nº/1970 (redação do Ajuste SINIEF 03/22), PDF da SEF-SC"
