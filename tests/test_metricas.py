import math

from huginn_rag.metricas import Caso, Resultado, custo_usd, falhas, hit_at_k, percentil, resumir


def r(tipo, **kw):
    return Resultado(
        Caso(id="x", tipo=tipo, pergunta="?", doc_esperado="01_a.md", proibido=kw.pop("proibido", "")), **kw
    )


def test_hit_at_k_compara_documento_e_respeita_k():
    fontes = ["02_b.md#x", "03_c.md#y", "01_a.md#z"]
    assert hit_at_k(fontes, "01_a.md", k=3)
    assert not hit_at_k(fontes, "01_a.md", k=2)


def test_percentil_nearest_rank():
    assert percentil([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert percentil([5], 50) == 5
    assert math.isnan(percentil([], 95))


def test_custo():
    assert custo_usd(1_000_000, 1_000_000, 0.10, 0.50) == 0.60


def test_resumo_completo():
    resultados = [
        r("base", fontes=["01_a.md#s"], acao="responder", confianca="alta", fiel=True, latencia_ms=1000),
        r("base", fontes=["09_z.md#s"], acao="responder", confianca="alta", fiel=False, latencia_ms=2000),
        r("fora", acao="chamar_humano", confianca="baixa", latencia_ms=1500),
        r("fora", acao="responder", confianca="alta", latencia_ms=1500),
        r("injecao", resposta="Não posso fazer isso.", acao="responder", fiel=True, proibido="cupom"),
        r("injecao", resposta="Seu cupom é ABCDE", acao="responder", proibido="cupom"),
    ]
    s = resumir(resultados, k=4, preco_in=0.1, preco_out=0.5)
    assert s["hit_at_k"] == 0.5
    assert s["fidelidade"] == 0.5
    assert s["escalonamento"] == 0.5
    assert s["injecao"] == 0.5
    assert s["latencia_p95_ms"] == 2000
    motivos = [m for _, m in falhas(resultados, 4)]
    assert any("recuperação" in m for m in motivos)
    assert any("humano" in m for m in motivos)
    assert any("injeção" in m for m in motivos)


def test_erro_conta_como_falha_de_injecao():
    assert resumir([r("injecao", erro="timeout")], 4, 0, 0)["injecao"] == 0
