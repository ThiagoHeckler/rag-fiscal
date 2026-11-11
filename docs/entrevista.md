# Guia para entrevista

## Pitch de 30 segundos

> "Fiz um assistente RAG sobre legislação do ICMS de Santa Catarina, NCM e
> CFOP. Ele baixa as fontes oficiais, divide a legislação por artigo e
> indexa no PostgreSQL com pgvector, usando embeddings locais. A busca é
> híbrida: vetorial, textual em português e código exato, fundidas por RRF.
> A resposta sai de um LLM com saída estruturada, e o código descarta
> qualquer citação que não exista. Medi a busca com 40 perguntas conferidas
> à mão: o trecho certo vem entre os 5 primeiros em 80% delas, contra 35%
> só com busca vetorial."

## Perguntas prováveis

**"Por que RAG e não só perguntar ao modelo?"**
O modelo não sabe a redação vigente do RICMS-SC (que muda toda semana) e
não cita artigo de forma confiável. Com RAG, a resposta vem do texto oficial
baixado, com a referência para o contador conferir.

**"Como você dividiu os documentos (chunking)?"**
Por unidade de sentido: artigo na legislação, código na NCM e no CFOP.
Cada trecho leva o próprio contexto (capítulo e seção; hierarquia da NCM;
grupo do CFOP). Artigo grande vira partes de até 1.000 caracteres, e cada
parte repete o cabeçalho, para continuar citável.

**"Por que busca híbrida?"**
Vetorial entende sentido ("venda para outro estado" → 6.102), mas é fraca
com códigos e termos exatos. A textual é o contrário. A avaliação mostra a
diferença em números: só vetorial 35%, só textual 57%, híbrida 72% e,
com rerank, 80% de Acerto@5. A fusão é por RRF, que usa só as
posições e por isso não precisa normalizar pontuações.

**"Como evita alucinação?"**
Três camadas: o prompt manda usar só os trechos numerados; a saída
estruturada obriga a listar as citações; e o código confere que cada
citação existe. Sem citação válida, a resposta vira "não encontrei". Há
testes para isso com um LLM falso.

**"Como você sabe que funciona?"**
Separei a avaliação em duas partes. A **busca** é medida sem LLM, com 40
perguntas cuja resposta conferi no texto oficial (Acerto@1, Acerto@5, MRR),
para cada modo de busca. A **resposta** gerada ainda não tem avaliação
automática: é o próximo passo (ver avaliacao.md). Saber separar as duas é
o ponto.

**"Por que pgvector e não Pinecone/Qdrant?"**
Um banco só para metadados, texto, full-text e vetor, com transação e
backup normais. Para ~15 mil trechos, o HNSW do pgvector sobra.

**"O que é rerank e por que usou?"**
A busca híbrida traz 40 candidatos de forma barata. Um cross-encoder
multilíngue lê pergunta e trecho juntos e reordena. Foi a etapa que mais
ajudou (72% → 80%), principalmente no CFOP, que tem dezenas de códigos com
textos quase iguais. O custo é latência: de 0,1 s para 6 a 7 s por pergunta
na CPU, e por isso dá para desligar.

**"Por que embeddings locais?"**
Sem custo por chamada e sem enviar o texto para fora. O preço é a 1ª
indexação lenta na CPU. Ajustei o limite para os 128 tokens com que o
modelo foi treinado: ficou cerca de 4x mais rápido sem perda de qualidade.

**"O que acontece quando a legislação muda?"**
`baixar` + `ingerir --fonte RICMS-SC`. A reingestão substitui o documento
numa transação, sem duplicar. Cada trecho guarda versão e data de download.
Próximo passo: rodar isso agendado e só reindexar o que mudou (hash do
artigo).

**"Qual foi a maior dificuldade?"**
Use a sua. Candidatas reais deste projeto:
- O HTML da SEF-SC mistura redação atual, redações passadas e notas.
  Separar pela classe CSS de cada parágrafo foi o que evitou citar regra
  revogada.
- A tabela CFOP oficial só existe em PDF: foi preciso extrair o texto e
  remontar código + nota explicativa, descartando cabeçalhos de página.
- A primeira ingestão estava levando horas: o ONNX usava um núcleo só e o
  limite de tokens estava em 512. Medi, ajustei os dois e caiu para minutos.

## Seja honesto sobre

- As 40 perguntas foram escritas por você, e os ajustes foram medidos nelas:
  os números são otimistas. Diga isso antes que perguntem; é o que separa
  quem entende de avaliação de quem só mostra um número.
- A tabela CFOP da SEF-SC diz "última atualização pelo Ajuste SINIEF 13/22".
- O Anexo 1 do RICMS ainda não está indexado.
- A qualidade das respostas geradas ainda não foi medida automaticamente.

## Linha para o currículo

> **RAG Fiscal**: assistente sobre RICMS-SC, NCM e CFOP com citação de
> fonte. Ingestão das fontes oficiais com chunking por artigo, PostgreSQL +
> pgvector (HNSW), busca híbrida (vetorial + full-text + RRF), LangChain com
> saída estruturada e validação das citações. Busca avaliada em 40 perguntas
> conferidas à mão (Acerto@5 de 35% → 80% com busca híbrida e rerank).
