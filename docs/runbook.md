# Runbook

## Subir do zero (meta: 10 minutos)

```bash
cp .env.example .env            # preencha senha, N8N_ENCRYPTION_KEY, EVAL_TOKEN e ajuste DATABASE_URL
docker compose up -d            # postgres + ollama (+ download do modelo) + n8n
docker compose logs -f ollama-pull   # espere "success"
python -m venv .venv && .venv/Scripts/pip install -e ".[dev,juiz]"   # Linux/Mac: .venv/bin/pip
.venv/Scripts/python scripts/ingestao_lote.py
.venv/Scripts/python eval/avaliar.py --modo recuperacao --rotulo "primeira carga"
```
n8n em http://localhost:5678 → crie o usuário dono → siga `docs/construir_workflows.md`
(ou importe os JSON de `n8n/workflows/` se já existirem).

## Túnel HTTPS para o Telegram

O Telegram só entrega webhooks em HTTPS público. Em desenvolvimento:

```bash
cloudflared tunnel --url http://localhost:5678
```
Copie a URL `https://….trycloudflare.com`, coloque em `N8N_WEBHOOK_URL` no `.env` (com `/` no final) e recrie o n8n:
```bash
docker compose up -d n8n
```
Depois **desative e ative** o W2 para o n8n registrar o webhook novo. A URL do túnel rápido muda a cada execução;
para algo estável use um túnel nomeado do Cloudflare ou ngrok com domínio fixo.

## Grupo de atendimento

1. Crie um grupo no Telegram e adicione o bot.
2. No @BotFather: `/setprivacy` → **Disable** (senão o bot não lê as respostas dos atendentes).
3. Descubra o id do grupo: mande uma mensagem no grupo e veja a execução do W2 no n8n (`message.chat.id`, negativo).
4. Ponha o id em `ATENDIMENTO_CHAT_ID` no `.env` e recrie o n8n.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Bot não responde nada | webhook não registrado ou outro workflow com Telegram Trigger ativo | Só o W2 pode ter Telegram Trigger; desative/ative o W2 |
| `different vector dimensions` | modelo de embeddings trocado sem recriar a coluna | Ajuste `vector(768/1536)` em `db/schema.sql`, recrie a tabela e reingira |
| Bot responde mas sem fontes | W1 gravou chunks sem metadados | Confira o Default Data Loader (metadados) e compare com o script |
| Respostas inventadas | prompt ou top-k | Rode `eval/avaliar.py`, veja as falhas de fidelidade no `eval/relatorio.md` |
| Cliente fica preso em "humano" | ticket não encerrado | No grupo, responda a mensagem do ticket com `/encerrar`, ou `UPDATE conversas SET modo='bot' WHERE chat_id=…` |
| Ollama lento na primeira chamada | modelo carregando na memória | Normal; as seguintes são rápidas |

## Backup e restauração

```bash
docker compose exec postgres pg_dump -U huginn huginn > backup.sql
docker compose exec -T postgres psql -U huginn huginn < backup.sql
```
Os workflows ficam versionados em `n8n/workflows/`; as credenciais **não** (recrie-as).

## Apagar dados de um cliente (pedido LGPD)

```sql
DELETE FROM n8n_chat_histories WHERE session_id = '<chat_id>';
DELETE FROM fila_humana WHERE chat_id = <chat_id>;
DELETE FROM conversas WHERE chat_id = <chat_id>;   -- mensagens e feedback vão junto (CASCADE)
```
