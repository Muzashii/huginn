"""Recarga da base fora do n8n (mesmo resultado do W1).

Uso:
  python scripts/ingestao_lote.py                 # só documentos que mudaram (hash)
  python scripts/ingestao_lote.py --forcar        # reprocessa tudo
  python scripts/ingestao_lote.py --tamanho 500 --sobreposicao 50   # experimento de chunk

Lê DATABASE_URL, EMBEDDINGS_PROVIDER/MODEL e OLLAMA_URL do ambiente (ou do .env).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from huginn_rag.chunking import (  # noqa: E402
    SOBREPOSICAO_PADRAO,
    TAMANHO_PADRAO,
    gerar_chunks,
    hash_conteudo,
    ler_base,
    separar_secoes,
)
from huginn_rag.embeddings import embed, vetor_sql  # noqa: E402


def carregar_env(caminho: Path = RAIZ / ".env") -> None:
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pasta", type=Path, default=RAIZ / "base")
    p.add_argument("--tamanho", type=int, default=TAMANHO_PADRAO)
    p.add_argument("--sobreposicao", type=int, default=SOBREPOSICAO_PADRAO)
    p.add_argument("--forcar", action="store_true", help="ignora o hash e reprocessa tudo")
    args = p.parse_args()
    carregar_env()

    documentos = ler_base(args.pasta)
    if not documentos:
        sys.exit(f"nenhum .md em {args.pasta}")
    # um experimento de chunk muda o resultado mesmo sem mudar o texto: entra no hash
    config = f"{args.tamanho}:{args.sobreposicao}:{os.getenv('EMBEDDINGS_MODEL', 'nomic-embed-text')}"

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for nome, conteudo in documentos.items():
            h = hash_conteudo(config + conteudo)
            ultimo = conn.execute(
                "SELECT hash FROM ingestoes WHERE documento = %s ORDER BY id DESC LIMIT 1", (nome,)
            ).fetchone()
            if ultimo and ultimo[0] == h and not args.forcar:
                print(f"= {nome} (sem mudança)")
                continue
            chunks = gerar_chunks(separar_secoes(nome, conteudo), args.tamanho, args.sobreposicao)
            vetores = embed([c.texto for c in chunks])
            with conn.transaction():
                conn.execute("DELETE FROM n8n_vectors WHERE metadata->>'documento' = %s", (nome,))
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO n8n_vectors (text, metadata, embedding) VALUES (%s, %s, %s::vector)",
                        [
                            (c.texto, json.dumps(c.metadata), vetor_sql(v))
                            for c, v in zip(chunks, vetores, strict=True)
                        ],
                    )
                conn.execute(
                    "INSERT INTO ingestoes (documento, chunks, hash, origem) VALUES (%s, %s, %s, 'script')",
                    (nome, len(chunks), h),
                )
            print(f"+ {nome}: {len(chunks)} chunks")

        # remove do banco documentos que saíram da pasta
        removidos = conn.execute(
            "DELETE FROM n8n_vectors WHERE NOT (metadata->>'documento' = ANY(%s)) RETURNING 1",
            (list(documentos),),
        ).fetchall()
        if removidos:
            print(f"- {len(removidos)} chunks de documentos removidos")


if __name__ == "__main__":
    main()
