"""Avalia o Huginn com o conjunto de ouro (eval/perguntas.csv).

Modos:
  recuperacao  Só a busca vetorial, direto no pgvector (sem n8n, sem LLM, grátis).
               Mede hit@k. Use para experimentos de chunk, top-k e modelo de embeddings.
  completo     Envia cada pergunta ao webhook de avaliação do W2 e mede tudo da seção 8
               (hit@k, fidelidade com LLM-juiz, escalonamento, injection, latência, custo).

Exemplos:
  python eval/avaliar.py --modo recuperacao --rotulo "chunk 800/100"
  python eval/avaliar.py --rotulo "prompt v2"

Gera eval/relatorio.md, eval/respostas_<data>.jsonl e acrescenta uma linha em eval/historico.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from huginn_rag.avaliacao import carregar_casos, gerar_relatorio, resultado_do_webhook  # noqa: E402
from huginn_rag.metricas import Caso, Resultado, falhas, resumir  # noqa: E402
from scripts.ingestao_lote import carregar_env  # noqa: E402

PASTA = Path(__file__).resolve().parent
COLUNAS_HISTORICO = [
    "quando", "rotulo", "modo", "k", "hit_at_k", "fidelidade", "escalonamento",
    "injecao", "latencia_p95_ms", "custo_medio_usd",
]  # fmt: skip


def buscar(conn, pergunta: str, k: int) -> list[tuple[str, str]]:
    from huginn_rag.embeddings import embed, vetor_sql

    vetor = vetor_sql(embed([pergunta])[0])
    # mesma métrica do nó PGVector do n8n (distância de cosseno)
    return conn.execute(
        "SELECT metadata->>'fonte', text FROM n8n_vectors ORDER BY embedding <=> %s::vector LIMIT %s",
        (vetor, k),
    ).fetchall()


def avaliar_recuperacao(casos: list[Caso], k: int) -> list[Resultado]:
    import psycopg

    resultados = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for caso in (c for c in casos if c.tipo == "base"):
            t0 = time.perf_counter()
            achados = buscar(conn, caso.pergunta, k)
            ms = int((time.perf_counter() - t0) * 1000)
            resultados.append(
                Resultado(caso, fontes=[f for f, _ in achados], latencia_ms=ms, acao="responder")
            )
            print(f"{caso.id}: {'ok ' if caso.doc_esperado in ' '.join(r for r, _ in achados) else 'ERR'} "
                  f"{[f for f, _ in achados]}")  # fmt: skip
    return resultados


def trechos_das_fontes(fontes: list[str]) -> list[str]:
    """Texto dos chunks citados, para o juiz conferir a resposta."""
    if not fontes or not os.getenv("DATABASE_URL"):
        return []
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        linhas = conn.execute(
            "SELECT text FROM n8n_vectors WHERE metadata->>'fonte' = ANY(%s) ORDER BY metadata->>'fonte'",
            (fontes,),
        ).fetchall()
    return [t for (t,) in linhas]


def avaliar_completo(casos: list[Caso]) -> list[Resultado]:
    from huginn_rag.juiz import criar_juiz

    url = os.environ["EVAL_WEBHOOK_URL"]
    cabecalhos = {"X-Huginn-Token": os.getenv("EVAL_TOKEN", "")}
    juiz = criar_juiz()
    if not juiz:
        print("! sem ANTHROPIC_API_KEY (ou pacote anthropic): fidelidade fica n/d")
    resultados = []
    with httpx.Client(timeout=60) as http:
        for i, caso in enumerate(casos):
            # sessão única por pergunta: a memória de uma não vaza para a outra
            corpo = {"pergunta": caso.pergunta, "sessao": f"eval-{int(time.time())}-{i}"}
            t0 = time.perf_counter()
            try:
                r = http.post(url, json=corpo, headers=cabecalhos)
                r.raise_for_status()
                res = resultado_do_webhook(caso, r.json(), int((time.perf_counter() - t0) * 1000))
            except (httpx.HTTPError, ValueError) as e:
                res = Resultado(caso, erro=str(e)[:200])
            if (
                juiz
                and not res.erro
                and (caso.tipo == "injecao" or (caso.tipo == "base" and res.acao == "responder"))
            ):
                res.fiel, motivo = juiz.julgar(
                    caso.tipo, caso.pergunta, res.resposta, trechos_das_fontes(res.fontes)
                )
                if res.fiel is False:
                    res.resposta += f"  [juiz: {motivo}]"  # aparece na tabela de falhas
            print(f"{caso.id} [{caso.tipo}] {res.acao or 'ERRO'} {res.fontes} {res.latencia_ms} ms")
            resultados.append(res)
    return resultados


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modo", choices=["recuperacao", "completo"], default="completo")
    p.add_argument("--k", type=int, default=4, help="top-k (no modo completo, deve bater com o W2)")
    p.add_argument("--rotulo", default="", help="nome do experimento, vai para o histórico")
    p.add_argument("--casos", type=Path, default=PASTA / "perguntas.csv")
    p.add_argument("--min-hit", type=float, default=None, help="sai com erro se hit@k ficar abaixo (CI)")
    args = p.parse_args()
    carregar_env()

    casos = carregar_casos(args.casos)
    resultados = avaliar_recuperacao(casos, args.k) if args.modo == "recuperacao" else avaliar_completo(casos)
    resumo = resumir(
        resultados,
        args.k,
        float(os.getenv("PRECO_ENTRADA_MTOK", "0.10")),
        float(os.getenv("PRECO_SAIDA_MTOK", "0.50")),
    )
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    relatorio = gerar_relatorio(
        resumo, falhas(resultados, args.k), modo=args.modo, rotulo=args.rotulo, k=args.k, quando=quando
    )
    (PASTA / "relatorio.md").write_text(relatorio, encoding="utf-8")

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    with (PASTA / f"respostas_{carimbo}.jsonl").open("w", encoding="utf-8") as f:
        for r in resultados:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    historico = PASTA / "historico.csv"
    novo = not historico.exists()
    with historico.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_HISTORICO, extrasaction="ignore")
        if novo:
            w.writeheader()
        w.writerow({**resumo, "quando": quando, "rotulo": args.rotulo, "modo": args.modo, "k": args.k})

    print("\n" + relatorio)
    if args.min_hit is not None and (resumo["hit_at_k"] or 0) < args.min_hit:
        sys.exit(f"hit@{args.k} = {resumo['hit_at_k']:.0%} abaixo do mínimo {args.min_hit:.0%}")


if __name__ == "__main__":
    main()
