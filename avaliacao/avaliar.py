"""Avaliação da RECUPERAÇÃO (sem LLM, sem custo).

Para cada pergunta de `perguntas.jsonl` sabemos qual trecho deveria voltar
(verificado à mão no texto oficial). Medimos, para cada modo de busca:

- Acerto@1: o trecho certo veio em 1º lugar?
- Acerto@5: veio entre os 5 primeiros? (o LLM recebe os k primeiros)
- MRR@10: média de 1/posição do trecho certo (0 se não veio no top 10).

Por que medir a recuperação separada da resposta? Porque se o trecho certo
não chega ao LLM, nenhum prompt conserta. É a primeira coisa a otimizar.

    python avaliacao/avaliar.py                 # tabela no terminal
    python avaliacao/avaliar.py --json saida.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from rag_fiscal import banco, config  # noqa: E402
from rag_fiscal.embeddings import FastEmbedder  # noqa: E402
from rag_fiscal.rerank import CrossEncoderReranker  # noqa: E402

MODOS = ("vetorial", "textual", "hibrida", "hibrida+rerank")


def base(referencia: str) -> str:
    return re.sub(r"\s*\(parte \d+/\d+\)$", "", referencia)


def posicao(resultados: list[str], esperado: list[str]) -> int | None:
    for i, ref in enumerate(resultados, start=1):
        # igual, ou o esperado é um prefixo de código (ex.: "NCM 0713.33" aceita 0713.33.11 e 0713.33.19)
        if any(base(ref) == e or base(ref).startswith(e + ".") for e in esperado):
            return i
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="grava os resultados detalhados")
    args = ap.parse_args()

    perguntas = [json.loads(linha) for linha in (RAIZ / "avaliacao" / "perguntas.jsonl").read_text().splitlines()]
    cfg = config.carregar()
    conn = banco.conectar(cfg.database_url)
    emb = FastEmbedder(cfg.modelo_embeddings)
    rr = CrossEncoderReranker()

    detalhes = []
    placar: dict[tuple[str, str], list[int | None]] = defaultdict(list)
    for q in perguntas:
        linha = {"pergunta": q["pergunta"], "esperado": q["esperado"], "categoria": q["categoria"]}
        for modo in MODOS:
            if modo == "hibrida+rerank":
                achados = banco.buscar(conn, emb, q["pergunta"], k=10, modo="hibrida", reranker=rr)
            else:
                achados = banco.buscar(conn, emb, q["pergunta"], k=10, modo=modo)
            refs = [r.referencia for r in achados]
            pos = posicao(refs, q["esperado"])
            linha[modo] = {"posicao": pos, "top3": refs[:3]}
            placar[(modo, q["categoria"])].append(pos)
            placar[(modo, "TOTAL")].append(pos)
        detalhes.append(linha)

    categorias = sorted({q["categoria"] for q in perguntas}) + ["TOTAL"]
    print(f"\n{len(perguntas)} perguntas | modelo: {cfg.modelo_embeddings}\n")
    print(f"{'modo':15} {'categoria':8} {'n':>3} {'Acerto@1':>9} {'Acerto@5':>9} {'MRR@10':>7}")
    resumo = []
    for modo in MODOS:
        for cat in categorias:
            pos = placar[(modo, cat)]
            a1 = sum(p == 1 for p in pos) / len(pos)
            a5 = sum(p is not None and p <= 5 for p in pos) / len(pos)
            mrr = sum(1 / p for p in pos if p) / len(pos)
            resumo.append({"modo": modo, "categoria": cat, "n": len(pos), "acerto1": a1, "acerto5": a5, "mrr": mrr})
            print(f"{modo:15} {cat:8} {len(pos):3} {a1:9.0%} {a5:9.0%} {mrr:7.2f}")
        print()

    final = MODOS[-1]
    erros = [d for d in detalhes if not (d[final]["posicao"] or 99) <= 5]
    if erros:
        print(f"Perguntas em que '{final}' NÃO trouxe o trecho certo no top 5:")
        for d in erros:
            print(f"  - {d['pergunta']}\n    esperado {d['esperado']}, veio {d[final]['top3']}")

    if args.json:
        Path(args.json).write_text(json.dumps({"resumo": resumo, "detalhes": detalhes}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
