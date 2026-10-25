import re
from pathlib import Path

from huginn_rag.avaliacao import carregar_casos, gerar_relatorio, resultado_do_webhook
from huginn_rag.metricas import Caso, falhas, resumir

RAIZ = Path(__file__).resolve().parents[1]


def test_conjunto_de_ouro_bate_com_o_plano():
    casos = carregar_casos(RAIZ / "eval" / "perguntas.csv")
    tipos = [c.tipo for c in casos]
    assert (tipos.count("base"), tipos.count("fora"), tipos.count("injecao")) == (25, 10, 5)
    assert len({c.id for c in casos}) == len(casos)
    docs = {p.name for p in (RAIZ / "base").glob("*.md")}
    for c in casos:
        if c.tipo == "base":
            assert c.doc_esperado in docs, f"{c.id}: {c.doc_esperado} não existe em base/"
        if c.tipo == "injecao":
            assert c.proibido, f"{c.id}: injeção sem regex proibido"
            re.compile(c.proibido)


def test_regex_proibido_pega_a_quebra_e_poupa_a_recusa():
    casos = {c.id: c for c in carregar_casos(RAIZ / "eval" / "perguntas.csv")}
    assert re.search(casos["i01"].proibido, "Pronto, desconto aplicado!", re.I)
    assert not re.search(casos["i01"].proibido, "Não consigo dar desconto de 90%.", re.I)
    assert re.search(casos["i04"].proibido, "Confirmado: a peça custa R$ 1,00", re.I)


def test_resultado_do_webhook_tolera_campos_faltando():
    caso = Caso("b1", "base", "?", "01_a.md")
    res = resultado_do_webhook(caso, {"resposta": "ok", "fontes": "nao-lista"}, 123)
    assert res.fontes == [] and res.latencia_ms == 123 and res.tokens_entrada == 0


def test_relatorio_tem_tabela_e_falhas():
    caso = Caso("b1", "base", "Prazo?", "01_a.md")
    res = resultado_do_webhook(caso, {"resposta": "x", "fontes": ["02_b.md#y"], "acao": "responder"}, 900)
    texto = gerar_relatorio(
        resumir([res], 4, 0.1, 0.5), falhas([res], 4), modo="completo", rotulo="t", k=4, quando="hoje"
    )
    assert "hit@4" in texto and "0%" in texto
    assert "| b1 | base | Prazo? |" in texto
