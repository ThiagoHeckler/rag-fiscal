# Decisões técnicas

Formato curto: o que foi decidido e por quê. É o que costuma ser perguntado
em entrevista.

### 1. Fontes oficiais, com rastreabilidade

Cada trecho sabe de onde veio (`documentos.url_origem`), qual versão
(`versao`: ex. "Resolução Gecex nº 926/2026") e quando foi baixado. Num
domínio em que a regra muda toda semana, "segundo qual versão?" é a primeira
pergunta do contador.

| Fonte | Origem | Observação |
|---|---|---|
| RICMS-SC (texto principal e Anexos 2, 3, 5, 6, 11) | legislacao.sef.sc.gov.br | HTML com classes CSS por tipo de parágrafo |
| Tabela NCM | Portal Único Siscomex (JSON) | baixada no dia da ingestão |
| Tabela CFOP | PDF da SEF-SC (Anexo II do Convênio s/nº/1970) | o próprio PDF diz "última atualização pelo Ajuste SINIEF 13/22"; CFOPs criados depois disso não aparecem |

**Fora da v1, de propósito:** Anexo 1 do RICMS (listas de mercadorias em
tabelas; precisa de um leitor de tabela próprio) e os anexos 4, 7, 8, 9 e
10. O assistente responde "não encontrei" quando o assunto está neles.

### 2. Dividir por unidade de sentido, não por tamanho fixo

- **Legislação:** um trecho por artigo. Artigo grande é subdividido
  (1.000 caracteres, sobreposição de 150), e cada pedaço repete
  "RICMS-SC, Anexo 2, art. 1º (CAPÍTULO I DAS ISENÇÕES / Seção I ...)".
  Assim o pedaço continua citável e com contexto.
- **NCM:** um trecho por código de 8 dígitos, com a hierarquia inteira
  ("Café... > Café torrado > Não descafeinado"). A folha sozinha ("-- Não
  descafeinado") não diz nada.
- **CFOP:** um trecho por código, com a nota explicativa ("Classificam-se
  neste código...") e o grupo.

Isso se chama *chunking contextual*: cada trecho leva o contexto de que
precisa para fazer sentido sozinho.

**Só a redação atual.** O HTML da SEF-SC marca cada parágrafo com uma
classe CSS (`redaoatual`, `notatexto`, `redaopassada`...). Notas e
redações revogadas ficam fora: elas contam a história do texto e fariam o
modelo citar regra que não vale mais.

### 3. Busca híbrida (vetorial + textual + código exato)

| Pergunta | Vetorial | Textual |
|---|---|---|
| "venda para outro estado" | entende o sentido | depende das palavras exatas |
| "carta de correção" | razoável | acha o termo exato |
| "0901.21.00" | fraca | acha |

- **Código exato:** NCM ou CFOP digitado na pergunta é buscado direto na
  coluna `codigo` e volta em 1º lugar.
- **Vetorial:** pgvector, distância de cosseno, índice HNSW.
- **Textual:** full-text search do Postgres com dicionário `portuguese`
  ("isentos" encontra "isentas").
- **Fusão por RRF** (*Reciprocal Rank Fusion*): cada trecho soma
  1/(60 + posição) em cada lista. Usa só a posição, então não é preciso
  normalizar pontuações de escalas diferentes.

- **Roteamento:** pergunta que fala em "NCM" busca só na tabela NCM; "CFOP",
  só na tabela CFOP. Sem isso, a pergunta "NCM do leite UHT" trazia artigos
  do RICMS que falam de leite.

Os números que justificam cada etapa estão em [avaliacao.md](avaliacao.md).

### 3b. Reordenação com cross-encoder (rerank)

A busca híbrida compara pergunta e trecho "de longe": cada vetor foi
calculado separadamente. O cross-encoder (`BAAI/bge-reranker-v2-m3`,
multilíngue, versão INT8, local) lê pergunta e trecho **juntos** e dá uma
nota de relevância. É caro demais para o banco inteiro, então reordena só
os 40 melhores candidatos da busca híbrida. Na avaliação foi a etapa que
mais ajudou, principalmente no CFOP, em que dezenas de códigos têm textos
quase iguais.

**Custo:** ~6 a 7 s por pergunta numa CPU de 2 núcleos (sem rerank: 0,1 s).
Pode ser desligado com `RAG_RERANK=0`. Numa máquina com mais núcleos ou com
GPU cai bastante. Os parâmetros (60 candidatos por estratégia, 40 para o
rerank, 600 caracteres por trecho) foram escolhidos medindo.

### 4. Embeddings locais (fastembed + paraphrase-multilingual-mpnet-base-v2)

- **Sem custo por chamada e sem enviar o texto para fora.** O modelo roda
  em ONNX na CPU.
- **Multilíngue:** modelos só em inglês vão mal em português jurídico.
- **128 tokens:** o modelo foi treinado com no máximo 128 tokens. O fastembed
  usa 512 por padrão, o que deixava a ingestão ~4x mais lenta sem ganho de
  qualidade. O que passa de 128 tokens fica fora do **vetor**, mas a busca
  textual continua vendo o trecho inteiro. A busca híbrida compensa isso.
- **Trade-off:** a 1ª ingestão leva de 20 a 40 minutos numa CPU comum (são
  cerca de 15 mil trechos). Um modelo pago (OpenAI, Voyage) indexaria em
  poucos minutos, com custo. A interface `Embedder` permite trocar.

### 5. Por que pgvector e não um banco vetorial dedicado?

Um banco só: os trechos, os metadados, a busca textual e a vetorial ficam no
mesmo PostgreSQL, com transação e backup normais. Para dezenas de milhares
de trechos, o pgvector com HNSW sobra. Um banco dedicado (Qdrant, Pinecone)
faz sentido com centenas de milhões de vetores.

### 6. A resposta só vale com citação, e o código confere

- O prompt manda usar só os trechos numerados e citar `[n]`.
- A saída é estruturada (Pydantic): `resposta`, `citacoes`, `encontrou`.
- O **código** descarta citações para trechos que não existem. Se não
  sobrar nenhuma citação válida, a resposta vira "Não encontrei isso nos
  documentos indexados". Melhor admitir que não sabe do que inventar uma
  regra fiscal.
- `temperature=0`: em consulta de legislação, consistência importa mais
  que criatividade.

### 7. LangChain onde agrega, SQL onde importa

O LangChain entra no divisor de texto, na interface `BaseRetriever` (o
recuperador pode virar ferramenta de qualquer agente LangChain ou LangGraph,
como o Auditor NF-e) e na cadeia prompt → modelo → saída estruturada. A
busca em si é SQL explícito: dá para ler, medir e ajustar. Abstração de
vector store esconderia exatamente a parte que mais precisa de ajuste.

### 8. Avaliar a busca separada da resposta

Se o trecho certo não chega ao LLM, nenhum prompt conserta. Por isso há um
conjunto de 40 perguntas com a resposta conferida à mão no texto oficial e
um script que mede Acerto@1, Acerto@5 e MRR **sem LLM e sem custo**. Toda
mudança de chunking, modelo ou peso da busca é medida com ele antes de
virar padrão.
