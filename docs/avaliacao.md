# Avaliação

## O que é medido

A **recuperação**: o trecho certo chega ao LLM? São 40 perguntas escritas
como um contador perguntaria (18 de RICMS-SC, 12 de NCM, 10 de CFOP), cada
uma com a referência certa **conferida à mão no texto oficial**
([avaliacao/perguntas.jsonl](../avaliacao/perguntas.jsonl)).

| Métrica | Significado |
|---|---|
| Acerto@1 | o trecho certo veio em 1º lugar |
| Acerto@5 | veio entre os 5 primeiros (o LLM recebe os 6 primeiros) |
| MRR@10 | média de 1/posição do trecho certo; 0 se ficou fora do top 10 |

Rodar: `make avaliar` (não usa LLM, não tem custo). O resultado bruto da
última execução fica em [avaliacao/resultado.txt](../avaliacao/resultado.txt).

## Resultado (10/11/2026, ~15 mil trechos indexados)

| Modo | Acerto@1 | Acerto@5 | MRR@10 |
|---|---|---|---|
| só vetorial | 20% | 35% | 0,27 |
| só textual (full-text pt) | 28% | 57% | 0,40 |
| híbrida (RRF + roteamento) | 45% | 72% | 0,58 |
| **híbrida + rerank (padrão)** | **52%** | **80%** | **0,65** |

Por fonte, no modo padrão: RICMS 83% · NCM 83% · CFOP 70% (Acerto@5).

## Como chegou aqui (cada mudança foi medida)

| Mudança | Acerto@5 | MRR |
|---|---|---|
| Ponto de partida: híbrida (vetorial + textual + RRF) | 60% | 0,46 |
| + roteamento ("NCM"/"CFOP" na pergunta) e palavras vazias na busca textual | 65% | 0,50 |
| + rerank com cross-encoder (30 candidatos) | 78% | 0,62 |
| + 60 candidatos por estratégia e desempate estável na ordenação | 85% | 0,67 |
| rerank limitado a 40 candidatos de até 600 caracteres (**padrão**) | 80% | 0,65 |

O último passo **troca 5 pontos de acerto por latência**: o rerank caiu de
~20 s para ~6 a 7 s por pergunta numa CPU de 2 núcleos. Numa máquina melhor
dá para voltar aos parâmetros maiores (`REORDENAR` em `banco.py` e
`max_caracteres` em `rerank.py`).

## Onde ainda erra (e por quê)

- **CFOPs quase iguais.** "Vender mercadoria comprada de terceiros dentro do
  estado" deveria dar 5.102, mas o 5.117 ("... originada de encomenda para
  entrega futura") tem quase o mesmo texto. Quem pergunta não diz a palavra
  que diferencia.
- **Sinônimos populares.** "Xampu" não aparece na tabela NCM com a grafia da
  pergunta; "smartphone" volta como outros aparelhos da posição 8517.
- **Pergunta genérica contra artigo genérico.** "Alíquota interna geral"
  perde para artigos de benefício que citam alíquotas específicas.
- **Assunto espalhado.** "Carta de correção" aparece em vários anexos (NF-e,
  transporte, regimes especiais).

## Limitações desta avaliação (leia antes de citar os números)

1. **As perguntas foram escritas por quem construiu o sistema**, e os
   ajustes (roteamento, número de candidatos) foram medidos neste mesmo
   conjunto. Os números tendem a ser otimistas. O certo é criar um
   conjunto separado, de preferência com perguntas reais do escritório,
   e só olhar para ele no fim.
2. **40 perguntas é pouco:** um acerto a mais ou a menos muda 2,5 pontos.
   Diferenças pequenas entre configurações não são conclusivas.
3. **A resposta gerada não foi avaliada**, só a busca. Uma busca certa com
   uma resposta errada ainda é possível.

## Próximos passos

- **Conjunto de validação separado** com 20 a 30 perguntas reais.
- **Avaliar a resposta:** para cada pergunta, conferir se a resposta (a)
  cita o trecho certo, (b) não afirma nada que não está no trecho
  (fidelidade) e (c) responde o que foi perguntado. Dá para automatizar com
  um LLM como juiz (ex.: RAGAS) e revisar uma amostra à mão.
- **Sinônimos do domínio** na busca textual (xampu/shampoo, celular/telefone).
- **Anexo 1 do RICMS** (listas de mercadorias em tabela).
