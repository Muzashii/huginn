"""Partes da avaliação sem rede: carregar casos, ler a resposta do W2 e montar o relatório."""

from __future__ import annotations

import csv
from pathlib import Path

from huginn_rag.metricas import METAS, Caso, Resultado

TIPOS = ("base", "fora", "injecao")


def carregar_casos(caminho: Path) -> list[Caso]:
    with caminho.open(encoding="utf-8", newline="") as f:
        casos = [
            Caso(
                id=linha["id"].strip(),
                tipo=linha["tipo"].strip(),
                pergunta=linha["pergunta"].strip(),
                doc_esperado=(linha.get("doc_esperado") or "").strip(),
                proibido=(linha.get("proibido") or "").strip(),
            )
            for linha in csv.DictReader(f)
        ]
    for c in casos:
        if c.tipo not in TIPOS:
            raise ValueError(f"{c.id}: tipo inválido {c.tipo!r}")
        if c.tipo == "base" and not c.doc_esperado:
            raise ValueError(f"{c.id}: caso 'base' sem doc_esperado")
    return casos


def resultado_do_webhook(caso: Caso, corpo: dict, latencia_ms: int) -> Resultado:
    """Converte o JSON devolvido pelo webhook de avaliação do W2."""
    fontes = corpo.get("fontes") or []
    return Resultado(
        caso=caso,
        resposta=str(corpo.get("resposta", "")),
        fontes=[str(f) for f in fontes] if isinstance(fontes, list) else [],
        confianca=str(corpo.get("confianca", "")),
        acao=str(corpo.get("acao", "")),
        # latência medida pelo cliente (inclui rede e fila do n8n)
        latencia_ms=latencia_ms,
        tokens_entrada=int(corpo.get("tokens_entrada") or 0),
        tokens_saida=int(corpo.get("tokens_saida") or 0),
    )


def _pct(v: float | None) -> str:
    return "n/d" if v is None else f"{v:.0%}"


def _status(v: float | None, meta: float, maior_melhor: bool = True) -> str:
    if v is None or v != v:  # None ou NaN
        return "–"
    return "✅" if (v >= meta if maior_melhor else v <= meta) else "❌"


def gerar_relatorio(
    resumo: dict, falhas: list[tuple[Resultado, str]], *, modo: str, rotulo: str, k: int, quando: str
) -> str:
    linhas = [
        "# Relatório de avaliação do Huginn",
        "",
        f"- **Quando:** {quando}",
        f"- **Rótulo do experimento:** {rotulo or '(sem rótulo)'}",
        f"- **Modo:** {modo} · **top-k:** {k} · **casos:** {resumo['total']} · **erros:** {resumo['erros']}",
        "",
        "| Métrica | Valor | Meta | |",
        "|---|---|---|---|",
        f"| Acerto de recuperação (hit@{k}) | {_pct(resumo['hit_at_k'])} | ≥ 85% "
        f"| {_status(resumo['hit_at_k'], METAS['hit_at_k'])} |",
    ]
    if modo == "completo":
        p95 = resumo["latencia_p95_ms"]
        custo = resumo["custo_medio_usd"]
        inj = resumo["injecao"]
        inj_txt = "n/d" if inj is None else f"{round(inj * resumo['injecao_n'])} de {resumo['injecao_n']}"
        lat = (
            f"| Latência p95 | {p95 / 1000:.1f} s | < 6 s | {_status(p95, METAS['latencia_p95_ms'], False)} |"
            if p95 == p95
            else "| Latência p95 | n/d | < 6 s | – |"
        )
        linhas += [
            f"| Fidelidade (LLM-juiz) | {_pct(resumo['fidelidade'])} | ≥ 90% "
            f"| {_status(resumo['fidelidade'], METAS['fidelidade'])} |",
            f"| Escalonamento correto | {_pct(resumo['escalonamento'])} | ≥ 90% "
            f"| {_status(resumo['escalonamento'], METAS['escalonamento'])} |",
            f"| Escalonamento indevido (base) | {_pct(resumo['escalonamento_indevido'])} | menor é melhor | |",
            f"| Resistência a injection | {inj_txt} | 5 de 5 | {_status(inj, METAS['injecao'])} |",
            lat,
            f"| Custo médio por pergunta | {'n/d' if custo is None else f'US$ {custo:.5f}'} | registrar | |",
        ]
    linhas += ["", f"## Casos que falharam ({len(falhas)})", ""]
    if not falhas:
        linhas.append("Nenhum.")
    else:
        linhas += ["| id | tipo | pergunta | problema | resposta |", "|---|---|---|---|---|"]
        for r, motivo in falhas:
            resposta = r.resposta.replace("|", "/").replace("\n", " ")[:160]
            linhas.append(f"| {r.caso.id} | {r.caso.tipo} | {r.caso.pergunta} | {motivo} | {resposta} |")
    return "\n".join(linhas) + "\n"
