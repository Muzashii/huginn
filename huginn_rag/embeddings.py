"""Cliente de embeddings: Ollama local (padrão, grátis) ou OpenAI.

Precisa ser o mesmo modelo configurado nos nós de Embeddings do W1 e do W2,
senão os vetores do script e os do n8n não são comparáveis.
"""

from __future__ import annotations

import os

import httpx


def embed(textos: list[str], lote: int = 32) -> list[list[float]]:
    provedor = os.getenv("EMBEDDINGS_PROVIDER", "ollama")
    vetores: list[list[float]] = []
    for i in range(0, len(textos), lote):
        parte = textos[i : i + lote]
        vetores.extend(_openai(parte) if provedor == "openai" else _ollama(parte))
    return vetores


def _ollama(textos: list[str]) -> list[list[float]]:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    modelo = os.getenv("EMBEDDINGS_MODEL", "nomic-embed-text")
    r = httpx.post(f"{url}/api/embed", json={"model": modelo, "input": textos}, timeout=120)
    r.raise_for_status()
    return r.json()["embeddings"]


def _openai(textos: list[str]) -> list[list[float]]:
    modelo = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
    r = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": modelo, "input": textos},
        timeout=120,
    )
    r.raise_for_status()
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


def vetor_sql(vetor: list[float]) -> str:
    """Literal aceito pelo pgvector: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.7g}" for v in vetor) + "]"
