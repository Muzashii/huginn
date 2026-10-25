# Decisões de arquitetura

Cada decisão tem o contexto, a escolha e o que muda se ela for revista.

## 1. pgvector em vez de um banco vetorial dedicado
**Contexto:** precisamos de busca vetorial e também de tabelas relacionais (conversas, feedback, fila).
**Escolha:** PostgreSQL 16 + pgvector, um banco só, com índice HNSW e distância de cosseno.
**Por quê:** uma base de ~60 chunks não justifica Pinecone/Qdrant; um banco só simplifica backup, LGPD
(apagar dados num lugar) e consultas que cruzam métricas com conversas. O nó PGVector do n8n usa a tabela direto.
**Rever se:** a base passar de centenas de milhares de chunks ou precisar de filtros híbridos pesados.

## 2. Chunk = seção do documento, ~800 caracteres, sobreposição ~100
**Escolha:** cada título `##` vira uma seção; seções maiores são quebradas por parágrafo e frase.
Cada chunk leva no texto o cabeçalho `[fonte: arquivo.md#secao] Título`.
**Por quê:** a base foi escrita com "um assunto por seção", então a seção é a unidade natural de resposta.
O cabeçalho no texto faz o LLM sempre saber de onde veio o trecho (necessário para citar a fonte) e
melhora a busca, porque o título entra no embedding.
**Medido em:** `docs/experimentos.md` (tamanhos 400/800/1200).

## 3. top-k = 4
**Por quê:** com seções curtas, 4 chunks cabem folgados no contexto (< 1.500 tokens) e dão margem
para perguntas que tocam dois assuntos. Mais k = mais custo e mais chance do LLM misturar trechos.
**Medido em:** `docs/experimentos.md` (k = 2, 4, 6).

## 4. Embeddings locais (Ollama `nomic-embed-text`, 768 dimensões)
**Por quê:** custo zero e nenhum dado sai da máquina na ingestão. A troca para OpenAI
`text-embedding-3-small` é uma variável (`EMBEDDINGS_PROVIDER`) e muda a dimensão para 1536
(recriar a coluna `embedding`). **W1, W2 e o script precisam usar o mesmo modelo**, senão os vetores não são comparáveis.
**Ideia de experimento:** o `nomic-embed-text` foi treinado com prefixos `search_query:` / `search_document:`;
o nó do n8n não os adiciona. Testar o ganho de hit@4 com prefixos via script.

## 5. Claude Haiku no atendimento
**Por quê:** respostas curtas e baseadas em contexto não precisam de um modelo grande; Haiku tem latência baixa
(meta p95 < 6 s) e custo de centavos por mês no volume do portfólio. Trocar o modelo é um experimento:
rodar `eval/avaliar.py` e comparar fidelidade × custo.

## 6. Um único Telegram Trigger (W2 é o roteador)
**Contexto:** um bot do Telegram tem **um** webhook. Vários workflows com Telegram Trigger no mesmo bot
disputam esse webhook e só o último ativado recebe mensagens.
**Escolha:** só o W2 tem o gatilho; ele roteia mensagens privadas para o agente, mensagens do grupo para o W3
e cliques em botões para W3/W4 (`Execute Workflow`).
**Alternativa descartada:** um segundo bot só para o grupo de atendimento (mais um token para proteger).

## 7. Contrato JSON validado fora do LLM
**Escolha:** além do Structured Output Parser, o nó `w2_pos_agente.js` valida o contrato e aplica regras de segurança:
JSON inválido, confiança baixa ou fonte com formato estranho → `chamar_humano`.
**Por quê:** o parser do n8n falha com exceção; a regra de negócio "na dúvida, humano" fica num lugar testado
(`tests/test_paridade_js.py`), não no humor do modelo.

## 8. Código dos nós Code com espelho em Python
**Escolha:** chunking e filtro LGPD existem em Python (`huginn_rag/`) e em JS (`n8n/code/`), com teste que compara
os dois na base real.
**Por quê:** a avaliação de recuperação e a ingestão em lote rodam em Python; se o JS divergir, o hit@k medido
deixa de valer para o bot.

## 9. Tokens estimados (caracteres / 4)
**Contexto:** o AI Agent do n8n não expõe o `usage` do modelo de forma estável entre versões.
**Escolha:** estimar no `w2_pos_agente.js` (pergunta + ~1.500 tokens de prompt e chunks; resposta / 4).
**Rever:** quando a versão do n8n expor `tokenUsage` no output do agente, gravar o valor real.

## 10. LGPD por desenho
- O filtro mascara CPF e cartão (validado por Luhn, para não mascarar número de pedido) **antes** de gravar e antes do LLM.
- A avaliação usa `chat_id = -1` e sessões descartáveis; não mistura com dados reais.
- Retenção de 90 dias apaga mensagens, memória do agente, lacunas e tickets encerrados (W6).
- Segredos só nas Credentials do n8n e no `.env` (fora do Git).
