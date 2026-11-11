# RAG Fiscal

Assistente que responde perguntas sobre **legislação do ICMS de Santa
Catarina, NCM e CFOP** e cita a fonte de cada afirmação ("RICMS-SC, Anexo 2,
art. 1º", "NCM 0901.21.00", "CFOP 6.108"). Quando os documentos não
respondem, ele diz que não encontrou, em vez de inventar.

```
            ┌───────────── ingestão (1x, ou quando a legislação muda) ─────────────┐
 SEF-SC ───►│ RICMS-SC (HTML)  ─► 1 trecho por artigo + capítulo/seção             │
 Siscomex ─►│ NCM (JSON)       ─► 1 trecho por código + hierarquia                 ├─► PostgreSQL
 SEF-SC ───►│ CFOP (PDF)       ─► 1 trecho por código + nota explicativa           │   + pgvector
            │                     embeddings locais (fastembed, sem custo)         │
            └──────────────────────────────────────────────────────────────────────┘
                                                                                        │
 pergunta ─► busca híbrida: código exato + vetorial (HNSW) + textual (pt) ─► RRF ─► rerank ─► top 6
                                                                                        │
           LLM (LangChain, saída estruturada) ─► resposta com [n] ─► código valida citações
```

## O que está indexado

| Fonte | Trechos | Versão |
|---|---|---|
| RICMS-SC: texto principal e Anexos 2, 3, 5, 6 e 11 | ~3.500 artigos/partes | redação vigente no dia do download |
| Tabela NCM | ~10.500 códigos | Resolução Gecex vigente no dia do download |
| Tabela CFOP | 641 códigos | Anexo II do Convênio s/nº/1970 (Ajuste SINIEF 03/22), PDF da SEF-SC |

`python -m rag_fiscal fontes` mostra exatamente o que está no banco, com
versão e data.

## Rodando

Pré-requisitos: Python 3.12+, Docker e `pdftotext` (pacote `poppler-utils`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env && export $(grep -v '^#' .env | xargs)

make db          # PostgreSQL + pgvector na porta 5436
make baixar      # baixa RICMS-SC, NCM e CFOP das fontes oficiais
make ingerir     # indexa (1ª vez baixa ~1,6 GB de modelos; ~25 min numa CPU de 2 núcleos)

python -m rag_fiscal buscar "qual cfop para venda a não contribuinte de outro estado"   # sem LLM
python -m rag_fiscal perguntar "a venda de leite fresco ao consumidor é isenta?"       # precisa de ANTHROPIC_API_KEY
make api         # http://localhost:8000/docs
```

## Qualidade medida

40 perguntas com a resposta conferida à mão no texto oficial
([avaliacao/perguntas.jsonl](avaliacao/perguntas.jsonl)), medindo se o
trecho certo volta da busca:

| Modo | Acerto@5 | MRR@10 |
|---|---|---|
| só vetorial | 35% | 0,27 |
| só textual | 57% | 0,40 |
| híbrida | 72% | 0,58 |
| **híbrida + rerank (padrão)** | **80%** | **0,65** |

Detalhes, onde erra e as limitações da própria avaliação (as perguntas
foram escritas por quem construiu o sistema) estão em
[docs/avaliacao.md](docs/avaliacao.md). Para rodar: `make avaliar`.

## Estrutura

```
rag_fiscal/
  fontes/legislacao.py   RICMS-SC: HTML → artigos com capítulo/seção (ignora notas e redação passada)
  fontes/ncm.py          NCM: JSON → códigos de 8 dígitos com a hierarquia
  fontes/cfop.py         CFOP: texto do PDF oficial → códigos com nota explicativa
  fontes/catalogo.py     URLs e versões das fontes (um lugar para auditar)
  embeddings.py          fastembed local, atrás de uma interface trocável
  rerank.py              cross-encoder multilíngue (bge-reranker-v2-m3) que reordena os candidatos
  schema.sql             tabelas, índice HNSW (vetor) e GIN (texto)
  banco.py               gravação e busca híbrida com RRF
  resposta.py            Retriever do LangChain + cadeia com saída estruturada + validação das citações
  api.py                 FastAPI: /buscar, /perguntar, /fontes
avaliacao/               40 perguntas + script de métricas
tests/                   17 testes (fontes, busca com Postgres real, validação da resposta)
docs/                    decisões, avaliação, guia para entrevista
```

## Testes

```bash
make test
```

- `test_fontes.py`: os três leitores com amostras reais (notas e redação
  passada ficam fora, a hierarquia da NCM é montada, cabeçalho de página do
  PDF é descartado).
- `test_busca.py`: busca no **PostgreSQL real** com um embedder falso
  (código exato em 1º, stemming em português, reingestão sem duplicar,
  filtro por fonte, RRF, rerank aplicado antes do corte).
- `test_resposta.py`: a cadeia com um LLM falso (citação inexistente é
  descartada, resposta sem citação vira "não encontrei", busca vazia nem
  chama o LLM).

**O que os testes NÃO cobrem:** a qualidade do texto gerado por um LLM de
verdade. Isso exige chave de API e uma avaliação própria (ver
"Próximos passos" em [docs/avaliacao.md](docs/avaliacao.md)).

## Documentação

- [docs/decisoes.md](docs/decisoes.md): por que cada escolha (chunking, busca híbrida, pgvector, validação)
- [docs/avaliacao.md](docs/avaliacao.md): métricas, onde erra e próximos passos
- [docs/entrevista.md](docs/entrevista.md): como apresentar e perguntas prováveis

> As respostas são apoio à consulta, não parecer fiscal. Confira sempre a
> redação vigente na fonte citada.
