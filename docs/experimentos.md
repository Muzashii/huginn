# Histórico de experimentos

Regra: **uma mudança por vez**, rodar a avaliação antes e depois, anotar aqui.
O `eval/avaliar.py` também acrescenta cada rodada em `eval/historico.csv` automaticamente.

```bash
# recuperação (grátis, segundos): chunk, top-k, embeddings
python scripts/ingestao_lote.py --forcar --tamanho 400 --sobreposicao 50
python eval/avaliar.py --modo recuperacao --k 4 --rotulo "chunk 400/50"

# completo (n8n + LLM + juiz): prompt, modelo, top-k do W2
python eval/avaliar.py --rotulo "prompt v2"
```

## Recuperação (hit@k, 25 perguntas da base)

| Data | Rótulo | Chunk / sobreposição | k | hit@k | Observação |
|---|---|---|---|---|---|
| 2026-10-25 | linha de base | 800 / 100 | 4 | **96%** | única falha: b16 ("copo ou prato" × seção "Contato com alimentos") |
| 2026-10-25 | chunk menor | 400 / 50 | 4 | 96% | nenhuma mudança: todas as seções têm < 400 caracteres |
| 2026-10-25 | chunk maior | 1200 / 150 | 4 | 96% | idem |
| 2026-10-25 | top-k menor | 800 / 100 | 2 | 88% | perde b02 (PLA) e b04 (retirada): o doc certo vinha em 3º/4º |
| 2026-10-25 | top-k maior | 800 / 100 | 6 | 96% | não recupera b16; só aumenta o contexto (custo) |

## Ponta a ponta

| Data | Rótulo | hit@4 | Fidelidade | Escalonamento | Injection | p95 | Custo/pergunta | Observação |
|---|---|---|---|---|---|---|---|---|
| | linha de base | | | | | | | |

## Aprendizados
- **Tamanho do chunk não importa nesta base.** O maior chunk tem 341 caracteres: como a base foi escrita com
  um assunto por seção e seções curtas, cada seção já é um chunk inteiro em qualquer configuração ≥ 400.
  O chunking por título fez o trabalho que um tamanho bem ajustado faria. (Volta a importar se entrarem PDFs longos.)
- **k = 4 é o ponto certo.** k = 2 derruba o hit para 88%; k = 6 não ganha nada e aumenta o contexto em 50%.
- **A falha que sobra é de vocabulário, não de tamanho.** "Copo ou prato" não se parece, para o embedding, com
  "contato com alimentos". Próximos experimentos: (1) escrever a seção com as palavras do cliente
  ("copo, caneca, prato, talher"); (2) prefixos `search_query:`/`search_document:` do nomic-embed-text;
  (3) busca híbrida (pgvector + full-text do Postgres).
