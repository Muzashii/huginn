"""Divide os documentos da base em seções e chunks.

Mesma regra do W1 no n8n: cada título `## ` vira uma seção, com metadados
`documento`, `secao` e `atualizado_em`. Seções maiores que `tamanho` são quebradas
em pedaços com sobreposição, preferindo parágrafos e depois frases.
O slug da seção precisa bater com o do W1 (testado em tests/test_paridade_js.py).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

TAMANHO_PADRAO = 800
SOBREPOSICAO_PADRAO = 100


@dataclass
class Secao:
    documento: str
    titulo: str
    slug: str
    texto: str
    atualizado_em: str | None = None

    @property
    def fonte(self) -> str:
        return f"{self.documento}#{self.slug}"


@dataclass
class Chunk:
    texto: str
    metadata: dict = field(default_factory=dict)


def slugify(titulo: str) -> str:
    sem_acento = unicodedata.normalize("NFD", titulo).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def hash_conteudo(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def separar_secoes(documento: str, conteudo: str) -> list[Secao]:
    atualizado = re.search(r"^atualizado_em:\s*(\S+)", conteudo, re.MULTILINE)
    atualizado_em = atualizado.group(1) if atualizado else None
    secoes: list[Secao] = []
    partes = re.split(r"^## +(.+)$", conteudo, flags=re.MULTILINE)
    # partes = [antes_do_primeiro_titulo, titulo1, corpo1, titulo2, corpo2, ...]
    for titulo, corpo in zip(partes[1::2], partes[2::2], strict=True):
        titulo = titulo.strip()
        texto = corpo.strip()
        if texto:
            secoes.append(Secao(documento, titulo, slugify(titulo), texto, atualizado_em))
    return secoes


def _quebrar(texto: str, tamanho: int, sobreposicao: int) -> list[str]:
    if len(texto) <= tamanho:
        return [texto]
    # unidades: parágrafos; se um parágrafo ainda for grande, frases
    unidades: list[str] = []
    for paragrafo in re.split(r"\n\s*\n", texto):
        if len(paragrafo) <= tamanho:
            unidades.append(paragrafo.strip())
        else:
            unidades.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", paragrafo) if s.strip())

    pedacos: list[str] = []
    atual = ""
    for unidade in unidades:
        candidato = f"{atual} {unidade}".strip() if atual else unidade
        if len(candidato) <= tamanho:
            atual = candidato
            continue
        if atual:
            pedacos.append(atual)
            cauda = atual[-sobreposicao:] if sobreposicao else ""
            # começa a sobreposição numa fronteira de palavra
            cauda = cauda[cauda.find(" ") + 1 :] if " " in cauda else cauda
            atual = f"{cauda} {unidade}".strip()
        else:
            atual = unidade
        while len(atual) > tamanho:  # frase única maior que o limite
            pedacos.append(atual[:tamanho])
            atual = atual[tamanho - sobreposicao :]
    if atual:
        pedacos.append(atual)
    return pedacos


def gerar_chunks(
    secoes: list[Secao], tamanho: int = TAMANHO_PADRAO, sobreposicao: int = SOBREPOSICAO_PADRAO
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for secao in secoes:
        for i, pedaco in enumerate(_quebrar(secao.texto, tamanho, sobreposicao)):
            # o cabeçalho com a fonte vai no texto: o LLM sempre vê de onde veio o trecho
            texto = f"[fonte: {secao.fonte}] {secao.titulo}\n{pedaco}"
            chunks.append(
                Chunk(
                    texto,
                    {
                        "documento": secao.documento,
                        "secao": secao.slug,
                        "titulo": secao.titulo,
                        "fonte": secao.fonte,
                        "atualizado_em": secao.atualizado_em,
                        "chunk": i,
                    },
                )
            )
    return chunks


def ler_base(pasta: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(pasta.glob("*.md"))}
