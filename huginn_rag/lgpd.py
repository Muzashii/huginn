"""Filtro de entrada do W2 (LGPD + comandos).

Mascara CPF e número de cartão antes de qualquer gravação, limita o tamanho
da mensagem e detecta comandos. A mesma lógica roda no nó Code do n8n
(n8n/code/w2_filtro_entrada.js); a paridade é testada em tests/test_paridade_js.py.
"""

from __future__ import annotations

import re

TAMANHO_MAXIMO = 1000
COMANDOS = ("/start", "/humano", "/encerrar")

_CARTAO = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
# Sinais comuns de prompt injection. Não bloqueia: só marca para log e avaliação.
_INJECAO = re.compile(
    r"ignore (?:as |todas as )?(?:suas |minhas )?(?:regras|instru[cç][oõ]es)|"
    r"esque[cç]a (?:as |suas )?(?:regras|instru[cç][oõ]es)|"
    r"voc[eê] agora [eé]|modo desenvolvedor|prompt do sistema|system prompt",
    re.IGNORECASE,
)


def luhn_valido(digitos: str) -> bool:
    soma = 0
    for i, c in enumerate(reversed(digitos)):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        soma += n
    return soma % 10 == 0


def _mascarar_cartao(m: re.Match) -> str:
    digitos = re.sub(r"\D", "", m.group(0))
    return "[CARTAO]" if 13 <= len(digitos) <= 19 and luhn_valido(digitos) else m.group(0)


def mascarar(texto: str) -> tuple[str, list[str]]:
    encontrados: list[str] = []
    novo = _CARTAO.sub(_mascarar_cartao, texto)
    if novo != texto:
        encontrados.append("cartao")
    texto, n = _CPF.subn("[CPF]", novo)
    if n:
        encontrados.append("cpf")
    return texto, encontrados


def detectar_comando(texto: str) -> str | None:
    primeiro = texto.strip().split(maxsplit=1)[0].lower() if texto.strip() else ""
    primeiro = primeiro.split("@", 1)[0]  # /humano@HuginnBot em grupos
    return primeiro if primeiro in COMANDOS else None


def filtrar_entrada(texto: str | None) -> dict:
    texto = (texto or "").strip()
    truncado = len(texto) > TAMANHO_MAXIMO
    if truncado:
        texto = texto[:TAMANHO_MAXIMO]
    limpo, mascarados = mascarar(texto)
    return {
        "texto": limpo,
        "comando": detectar_comando(limpo),
        "mascarados": mascarados,
        "truncado": truncado,
        "suspeita_injecao": bool(_INJECAO.search(limpo)),
        "vazio": not limpo,
    }
