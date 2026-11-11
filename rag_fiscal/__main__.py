"""Linha de comando.

    python -m rag_fiscal baixar              # baixa as fontes para dados/brutos/
    python -m rag_fiscal ingerir             # cria o schema e indexa tudo (gera embeddings)
    python -m rag_fiscal fontes              # o que está indexado
    python -m rag_fiscal buscar "pergunta"   # só a busca (sem LLM)
    python -m rag_fiscal perguntar "pergunta"   # resposta com citações (precisa de ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from rag_fiscal import banco, config
from rag_fiscal.fontes import catalogo, cfop, legislacao, ncm

BRUTOS = Path(__file__).resolve().parents[1] / "dados" / "brutos"


def baixar() -> None:
    BRUTOS.mkdir(parents=True, exist_ok=True)
    alvos = {f"{a}.htm": f"{catalogo.BASE_RICMS}/{a}.htm" for a in catalogo.RICMS_SC}
    alvos["ncm.json"] = catalogo.NCM_URL
    alvos["cfop_sef.pdf"] = catalogo.CFOP_URL
    for nome, url in alvos.items():
        print(f"baixando {url}")
        with urllib.request.urlopen(url, timeout=120) as resp:
            (BRUTOS / nome).write_bytes(resp.read())
    if not shutil.which("pdftotext"):
        sys.exit("instale o pdftotext (pacote poppler-utils) para extrair a tabela CFOP")
    subprocess.run(["pdftotext", "-layout", BRUTOS / "cfop_sef.pdf", BRUTOS / "cfop_sef.txt"], check=True)


def documentos():
    for arquivo, (titulo, prefixo) in catalogo.RICMS_SC.items():
        caminho = BRUTOS / f"{arquivo}.htm"
        yield legislacao.ler(caminho.read_bytes(), titulo, prefixo, f"{catalogo.BASE_RICMS}/{arquivo}.htm")
    yield ncm.ler((BRUTOS / "ncm.json").read_bytes(), catalogo.NCM_URL)
    yield cfop.ler_texto_oficial((BRUTOS / "cfop_sef.txt").read_text(), catalogo.CFOP_URL, catalogo.CFOP_VERSAO)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rag_fiscal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baixar")
    ing = sub.add_parser("ingerir")
    ing.add_argument("--fonte", choices=["RICMS-SC", "NCM", "CFOP"], help="reindexa só uma fonte")
    ing.add_argument("--so-novos", action="store_true", help="pula documentos que já estão no banco")
    sub.add_parser("fontes")
    b = sub.add_parser("buscar")
    b.add_argument("pergunta")
    b.add_argument("-k", type=int, default=6)
    b.add_argument("--modo", choices=["hibrida", "vetorial", "textual"], default="hibrida")
    p = sub.add_parser("perguntar")
    p.add_argument("pergunta")
    args = ap.parse_args(argv)

    if args.cmd == "baixar":
        baixar()
        return 0

    cfg = config.carregar()
    conn = banco.conectar(cfg.database_url)

    if args.cmd == "fontes":
        for fonte, titulo, versao, n, quando in banco.estatisticas(conn):
            print(f"{fonte:9} {n:6} trechos  {titulo}  [{versao or 's/ versão'}]  {quando:%d/%m/%Y}")
        return 0

    from rag_fiscal.embeddings import FastEmbedder

    embedder = FastEmbedder(cfg.modelo_embeddings)
    reranker = None
    if args.cmd in ("buscar", "perguntar") and cfg.rerank:
        from rag_fiscal.rerank import CrossEncoderReranker

        reranker = CrossEncoderReranker()

    if args.cmd == "ingerir":
        banco.criar_schema(conn)
        for doc in documentos():
            if args.fonte and doc.fonte != args.fonte:
                continue
            if args.so_novos and banco.existe(conn, doc):
                print(f"{doc.titulo}: já indexado, pulando", flush=True)
                continue
            inicio = time.time()
            n = banco.gravar(conn, doc, embedder)
            print(f"{doc.titulo}: {n} trechos em {time.time() - inicio:.0f}s", flush=True)
        return 0

    if args.cmd == "buscar":
        resultados = banco.buscar(conn, embedder, args.pergunta, k=args.k, modo=args.modo, reranker=reranker)
        for i, r in enumerate(resultados, start=1):
            marca = " (código exato)" if r.exato else ""
            posicoes = f"vet={r.posicao_vetor} txt={r.posicao_texto}"
            print(f"[{i}] {r.referencia}{marca}  nota={r.pontuacao:.3f} {posicoes}")
            print("    " + r.texto[:220].replace("\n", " "))
        return 0

    from rag_fiscal.resposta import criar_llm, criar_recuperador, responder

    resp = responder(args.pergunta, criar_recuperador(conn, embedder, cfg.k, reranker), criar_llm(cfg.modelo_llm))
    print(resp.resposta)
    for f in resp.fontes:
        print(f"  [{f['n']}] {f['referencia']} — {f['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
