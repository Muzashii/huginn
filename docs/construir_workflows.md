# Construindo os workflows no n8n, passo a passo

O plano pede que os fluxos sejam montados à mão: na entrevista vão perguntar o que cada nó faz.
Este guia diz **o que** configurar em cada nó; o código dos nós Code está pronto em `n8n/code/`
(testado contra o Python em `tests/test_paridade_js.py`) e os prompts em `n8n/prompts/`.

Ao terminar cada workflow: **⋯ → Download** e salve em `n8n/workflows/` (ver o README de lá).

---

## Antes de tudo: credenciais (Settings → Credentials)

| Credencial | Tipo no n8n | Valor |
|---|---|---|
| `Huginn Postgres` | Postgres | host `postgres`, porta `5432`, banco/usuário/senha do `.env` |
| `Huginn Telegram` | Telegram API | token do @BotFather |
| `Huginn Anthropic` | Anthropic | sua API key |
| `Huginn Ollama` | Ollama | base URL `http://ollama:11434` |
| `Huginn Eval Token` | Header Auth | nome `X-Huginn-Token`, valor = `EVAL_TOKEN` do `.env` |
| `Huginn Drive` | Google Drive OAuth2 | só para o W1 automático (opcional) |

> Dentro do Docker os serviços se enxergam pelo nome (`postgres`, `ollama`, `brokk-mock`), nunca `localhost`.

## Uma regra do Telegram que molda a arquitetura

Um bot do Telegram tem **um único webhook**. Se W2, W3 e W4 tiverem cada um seu `Telegram Trigger`,
o último a ser ativado "rouba" o webhook dos outros. Por isso **só o W2 tem Telegram Trigger** e funciona
como roteador; W3 e W4 começam com `Execute Workflow Trigger` e são chamados pelo W2.
(Registrado em `docs/decisoes.md`.)

---

## Fase 0 — W0 "olá" (testa bot + túnel)

1. **Telegram Trigger** — credencial `Huginn Telegram`, Updates: `message`.
2. **Telegram → Send Message** — Chat ID `{{ $json.message.chat.id }}`, texto `Olá! Sou o Huginn 🐦‍⬛`.
3. Ative o workflow e mande "oi" ao bot. Funcionou? Desative o W0 (ele disputa o webhook com o W2).

Se nada chegar: o `N8N_WEBHOOK_URL` precisa ser HTTPS público (ver `docs/runbook.md`, seção túnel).

---

## W1 — Ingestão da base

Duas entradas que convergem no mesmo nó **"Seções e chunks"**:

**Entrada A (manual, recarga completa)**
1. **Manual Trigger**.
2. **Read/Write Files from Disk** — operação *Read*, File Selector `/base/*.md`
   (monte a pasta: acrescente `- ./base:/base:ro` aos volumes do serviço `n8n`).
3. **Extract from File** — operação *Extract From Text File*, campo de saída `conteudo`.
4. **Edit Fields (Set)** — `documento` = `{{ $binary.data.fileName }}` (ou `$json.fileName`, conforme a versão), mantenha `conteudo`.

**Entrada B (automática, Google Drive)**
1. **Google Drive Trigger** — *File Created* e *File Updated*, pasta `DRIVE_PASTA_BASE_ID`.
2. **Google Drive → Download** o arquivo → **Extract from File** → **Set** (`documento`, `conteudo`) como acima.

**Daqui em diante (comum):**
5. **Code "Hash"** (Run Once for Each Item):
   ```js
   const crypto = require('crypto');
   return { json: { ...$json, hash: crypto.createHash('sha256').update($json.conteudo, 'utf8').digest('hex') } };
   ```
6. **Postgres "Último hash"** — Execute Query, *Always Output Data* ligado:
   `SELECT hash FROM ingestoes WHERE documento = $1 ORDER BY id DESC LIMIT 1` com Query Parameters `{{ $json.documento }}`.
7. **IF "Mudou?"** — `{{ $json.hash }}` *is not equal to* `{{ $('Hash').item.json.hash }}`. Falso → fim (não gasta embeddings).
8. **Postgres "Apagar chunks antigos"** — `DELETE FROM n8n_vectors WHERE metadata->>'documento' = $1`, parâmetro `{{ $('Hash').item.json.documento }}`.
9. **Code "Seções e chunks"** — Run Once for All Items, cole `n8n/code/w1_chunking.js`.
   A entrada precisa ter `documento` e `conteudo`: se o IF trocou o item, use antes um **Set** que recupere `{{ $('Hash').item.json }}`.
10. **PGVector Vector Store** — operação *Insert Documents*, credencial `Huginn Postgres`, Table Name `n8n_vectors`.
    - Sub-nó **Embeddings Ollama** — modelo `nomic-embed-text`.
    - Sub-nó **Default Data Loader** — Type of Data *JSON*, Mode *Load Specific Data*, Data `{{ $json.pageContent }}`;
      Options → Metadata: adicione `documento`, `secao`, `titulo`, `fonte`, `atualizado_em`, `chunk` lendo de `{{ $json.metadata.<campo> }}`.
      Text Splitting: *Custom* com **Recursive Character Text Splitter** chunk size `1000`, overlap `0`
      (nossos chunks já têm ≤ 800 caracteres; o splitter só não pode quebrar de novo).
11. **Postgres "Registrar ingestão"** — Execute Once ligado:
    `INSERT INTO ingestoes (documento, chunks, hash) VALUES ($1, $2, $3)`
    com `{{ $('Hash').item.json.documento }}`, `{{ $('Seções e chunks').all().length }}`, `{{ $('Hash').item.json.hash }}`.

**Teste:** rode o Manual Trigger e confira `SELECT metadata->>'fonte', left(text, 60) FROM n8n_vectors LIMIT 5;`.
O resultado deve ser idêntico ao de `python scripts/ingestao_lote.py --forcar`.

---

## W2 — Atendimento e roteador (o coração)

### Gatilhos e roteamento
1. **Telegram Trigger** — Updates: `message` **e** `callback_query`.
2. **Switch "Rotear update"** (Rules, saídas nomeadas):
   - `botao` — `{{ $json.callback_query }}` *exists*.
   - `grupo` — `{{ $json.message.chat.id }}` *equals* `{{ $env.ATENDIMENTO_CHAT_ID }}`.
   - `privado` — fallback.
3. Saída `botao` → **Switch** por `{{ $json.callback_query.data }}`: começa com `fb:` → **Execute Workflow** W4; começa com `assumir:` → **Execute Workflow** W3 (modo `assumir`).
   Depois, **Telegram → Answer Query** com o `callback_query.id` (tira o "relógio" do botão).
4. Saída `grupo` → **Execute Workflow** W3 (modo `grupo`).
5. Saída `privado` → **Code "Filtro de entrada"**.
6. **Webhook "Eval"** — POST, path `huginn-eval`, Authentication *Header Auth* (`Huginn Eval Token`),
   Respond *Using 'Respond to Webhook' Node* → também liga no **Filtro de entrada**.

### Pré-processamento
7. **Code "Filtro de entrada"** — Run Once for All Items, cole `n8n/code/w2_filtro_entrada.js`.
   **O nome do nó tem que ser exatamente `Filtro de entrada`** (o nó de validação lê dele).
8. **Postgres "Upsert conversa"** — Execute Query:
   ```sql
   INSERT INTO conversas (chat_id, ultima_msg_em) VALUES ($1, now())
   ON CONFLICT (chat_id) DO UPDATE SET ultima_msg_em = now()
   RETURNING modo
   ```
   parâmetro `{{ $json.chat_id }}`.
9. **Switch "Decidir"**:
   - `vazio` — `{{ $('Filtro de entrada').item.json.vazio }}` é true → fim.
   - `start` — comando = `/start` → **Telegram**: "Olá! Sou o Huginn, assistente automático da loja. Pergunte sobre prazos, materiais, pagamento… Digite /humano a qualquer momento."
   - `humano_pedido` — comando = `/humano` → **Execute Workflow** W3 (modo `abrir`, motivo `pedido_cliente`).
   - `em_humano` — `{{ $json.modo }}` = `humano` → **Execute Workflow** W3 (modo `repassar`): o bot fica calado.
   - `agente` — fallback.

### O agente
10. **AI Agent** (Tools Agent)
    - Source for Prompt: *Define below*, Prompt `{{ $('Filtro de entrada').item.json.texto }}`.
    - **Require Specific Output Format**: ligado. System Message: cole o bloco de `n8n/prompts/w2_sistema.md`.
    - Sub-nó **Anthropic Chat Model** — modelo Claude Haiku (o mais recente da lista; hoje `claude-haiku-5-5`), Max tokens 1024.
    - Sub-nó **Postgres Chat Memory** — Session ID *Define below* `{{ $('Filtro de entrada').item.json.sessao }}`,
      Table `n8n_chat_histories`, Context Window Length `10`.
    - Sub-nó **Structured Output Parser** — JSON Example:
      ```json
      {"resposta": "Peças em resina ficam prontas em 3 a 5 dias úteis.", "fontes": ["01_prazos_e_entrega.md#prazo-de-producao-em-resina"], "confianca": "alta", "acao": "responder"}
      ```
    - Ferramenta **PGVector Vector Store** — operação *Retrieve Documents (As Tool for AI Agent)*, Name `buscar_base`,
      Description da tabela em `w2_sistema.md`, Table `n8n_vectors`, Limit `4`, Include Metadata ligado.
      Sub-nó **Embeddings Ollama** `nomic-embed-text` (o **mesmo** modelo do W1!).
    - Ferramenta **HTTP Request Tool** — Name `orcamento`, POST `{{ $env.BROKK_API_URL }}/orcamento`, body JSON com
      `material`, `altura_cm`, `quantidade`, `acabamento` preenchidos por `{{ $fromAI('material') }}` etc.
    - Ferramenta **Call n8n Workflow Tool** — Name `chamar_humano`, workflow W3, campos fixos:
      `modo` = `abrir`, `chat_id` = `{{ $('Filtro de entrada').item.json.chat_id }}`, `canal` = `{{ $('Filtro de entrada').item.json.canal }}`,
      `motivo` = `sem_base`, `pergunta` = `{{ $('Filtro de entrada').item.json.texto }}`.
    - Settings do nó: **On Error → Continue (using error output)**; ligue a saída de erro no nó 11 também
      (o validador transforma erro em "chamar humano").
11. **Code "Validar saída do agente"** — cole `n8n/code/w2_pos_agente.js`.
12. **Postgres "Gravar mensagem"** — Insert em `mensagens` (chat_id, canal, pergunta, resposta, fontes, confianca, acao,
    tokens_entrada, tokens_saida, latencia_ms), *Return Fields* `id`. Em `fontes` use `{{ JSON.stringify($json.fontes) }}`.

### Saída
13. **IF "É avaliação?"** — `{{ $('Validar saída do agente').item.json.canal }}` = `eval`
    → **Respond to Webhook** com JSON `{{ $('Validar saída do agente').item.json }}`.
14. Senão, **Switch** por `acao`:
    - `responder` → **Telegram → Send Message** com `resposta` e **Inline Keyboard**:
      👍 callback data `fb:1:{{ $('Gravar mensagem').item.json.id }}`, 👎 `fb:-1:{{ ...id }}`.
    - `chamar_humano` → **Execute Workflow** W3 (modo `abrir`, `motivo` = `{{ $json.motivo }}`) e grava em `lacunas_base`
      (`origem` = `escalonamento`, `mensagem_id` = id) quando o motivo for `sem_base` ou `baixa_confianca`.

**Teste rápido** (com o W2 ativo):
```bash
curl -s -X POST http://localhost:5678/webhook/huginn-eval -H "X-Huginn-Token: SEU_TOKEN" -H "Content-Type: application/json" -d "{\"pergunta\":\"Qual o prazo da resina?\",\"sessao\":\"teste1\"}"
```

---

## W3 — Escalonamento humano

**Execute Workflow Trigger** (Accept all data) → **Switch** por `{{ $json.modo }}`:

**`abrir`**
1. IF `canal` = `eval` → fim (a avaliação não pode lotar o grupo).
2. **Postgres** — já existe ticket aberto? `SELECT id FROM fila_humana WHERE chat_id = $1 AND status <> 'encerrado'`
   (*Always Output Data*). Se existir, fim: a ferramenta `chamar_humano` e o Switch do W2 podem disparar juntos, e isso evita ticket duplicado.
3. **Postgres** — `UPDATE conversas SET modo = 'humano' WHERE chat_id = $1` e
   `INSERT INTO fila_humana (chat_id, motivo, pergunta) VALUES ($1, $2, $3) RETURNING id`.
4. **Telegram → cliente**: "Vou passar para uma pessoa da equipe, já já respondem por aqui."
5. **Telegram → grupo** (`{{ $env.ATENDIMENTO_CHAT_ID }}`):
   ```
   🎫 Ticket #{{id}} · motivo: {{motivo}}
   chat_id: {{chat_id}}
   Pergunta: {{pergunta}}
   Responda a ESTA mensagem (reply) para falar com o cliente. /encerrar (em reply) devolve ao bot.
   ```
   com botão inline **Assumir** (`assumir:{{id}}`). Grave o `message_id` retornado em `fila_humana.msg_grupo_id`.

**`repassar`** (cliente escreveu enquanto está com humano) → Telegram → grupo:
`💬 chat_id: {{chat_id}}\n{{texto}}`.

**`grupo`** (mensagem no grupo de atendimento)
1. IF não é reply (`message.reply_to_message` não existe) → fim (conversa interna da equipe).
2. **Code** — extrai o cliente do texto respondido: `/chat_id: (-?\d+)/.exec(reply_to_message.text)[1]`.
3. Se o texto é `/encerrar` → `UPDATE fila_humana SET status = 'encerrado', encerrado_em = now() WHERE chat_id = $1 AND status <> 'encerrado'`,
   `UPDATE conversas SET modo = 'bot' ...`, avisa o cliente ("Voltei! Se precisar de algo, é só perguntar.").
4. Senão → **Telegram → cliente** com o texto do atendente.

**`assumir`** → `UPDATE fila_humana SET status = 'em_atendimento', assumido_por = $2 WHERE id = $1`
(id vem de `callback_query.data`, nome de `callback_query.from.first_name`) e edite a mensagem do grupo com "assumido por Fulano".

---

## W4 — Feedback e lacunas

**Execute Workflow Trigger** →
1. **Code** — `const [, nota, id] = $json.callback_query.data.split(':'); return { json: { nota: Number(nota), mensagem_id: Number(id) } };`
2. **Postgres** — `INSERT INTO feedback (mensagem_id, nota) VALUES ($1, $2) ON CONFLICT (mensagem_id) DO UPDATE SET nota = EXCLUDED.nota`.
3. **IF** nota = -1 → **Postgres** — `INSERT INTO lacunas_base (pergunta, origem, mensagem_id) SELECT pergunta, 'feedback_negativo', id FROM mensagens WHERE id = $1`.

---

## W5 — Relatório semanal

1. **Schedule Trigger** — toda segunda, 8h.
2. **Postgres "Indicadores"** e **Postgres "Lacunas"** — consultas de `db/consultas_relatorio.sql`.
3. **AI Agent** sem ferramentas, prompt de `n8n/prompts/w5_relatorio.md`, mesmo Chat Model.
4. **Telegram → grupo** — junte indicadores + texto do agente:
   ```
   📊 Huginn — semana
   Conversas: {{conversas}} · Resolvidas sem humano: {{resolucao_sem_humano_pct}}%
   👍: {{positivos_pct}}% · p95: {{latencia_p95_ms}} ms · Custo: US$ {{custo_usd}}
   Atendimento humano médio: {{atendimento_humano_min}} min

   {{ texto do agente }}
   ```

## W6 — Retenção LGPD

**Schedule Trigger** diário às 3h → **Postgres** com o bloco "Retenção" de `db/consultas_relatorio.sql`,
(o número de dias vem de `{{ Number($env.RETENCAO_DIAS) }}`, já embutido no SQL).
