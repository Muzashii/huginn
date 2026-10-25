from pathlib import Path

from huginn_rag.chunking import gerar_chunks, ler_base, separar_secoes, slugify

BASE = Path(__file__).resolve().parents[1] / "base"


def test_slugify_remove_acentos():
    assert slugify("Prazo de produção em resina") == "prazo-de-producao-em-resina"
    assert slugify("  Sol & calor!  ") == "sol-calor"


def test_separa_secoes_com_metadados():
    doc = "# T\n\natualizado_em: 2026-01-02\n\n## Primeira\nTexto um.\n\n## Segunda seção\nTexto dois.\n"
    secoes = separar_secoes("x.md", doc)
    assert [s.slug for s in secoes] == ["primeira", "segunda-secao"]
    assert secoes[1].fonte == "x.md#segunda-secao"
    assert secoes[0].atualizado_em == "2026-01-02"


def test_chunk_carrega_fonte_no_texto_e_metadados():
    chunks = gerar_chunks(separar_secoes("x.md", "## Título\nCorpo curto."))
    assert len(chunks) == 1
    assert chunks[0].texto.startswith("[fonte: x.md#titulo] Título\n")
    assert chunks[0].metadata["documento"] == "x.md"


def test_secao_grande_quebra_com_sobreposicao():
    frases = " ".join(f"Frase número {i} sobre impressão." for i in range(80))
    chunks = gerar_chunks(separar_secoes("x.md", f"## Longa\n{frases}"), tamanho=300, sobreposicao=60)
    assert len(chunks) > 1
    for c in chunks:
        corpo = c.texto.split("\n", 1)[1]
        assert len(corpo) <= 300
    # o início do segundo pedaço repete o fim do primeiro
    fim_primeiro = chunks[0].texto.split("\n", 1)[1][-30:]
    assert fim_primeiro.split()[-1] in chunks[1].texto


def test_base_real_tem_uma_secao_por_assunto():
    docs = ler_base(BASE)
    assert len(docs) >= 8
    for nome, conteudo in docs.items():
        secoes = separar_secoes(nome, conteudo)
        assert secoes, f"{nome} sem seções ##"
        assert all(s.atualizado_em for s in secoes), f"{nome} sem atualizado_em"
        slugs = [s.slug for s in secoes]
        assert len(slugs) == len(set(slugs)), f"{nome} tem títulos repetidos"
