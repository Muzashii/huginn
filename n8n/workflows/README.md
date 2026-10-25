# Workflows exportados

Depois de montar cada fluxo seguindo `docs/construir_workflows.md`, exporte e salve aqui:

| Arquivo | Workflow |
|---|---|
| `w1_ingestao.json` | W1 — Ingestão da base |
| `w2_atendimento.json` | W2 — Atendimento e roteador |
| `w3_escalonamento.json` | W3 — Escalonamento humano |
| `w4_feedback.json` | W4 — Feedback e lacunas |
| `w5_relatorio.json` | W5 — Relatório semanal |
| `w6_retencao.json` | W6 — Retenção LGPD |

**Exportar** (no navegador): workflow aberto → ⋯ → *Download*. Ou pela CLI, todos de uma vez:
```bash
docker compose exec n8n n8n export:workflow --all --separate --output=/home/node/.n8n/export/
docker compose cp n8n:/home/node/.n8n/export/. n8n/workflows/
```

**Importar** numa instalação nova (esta pasta já está montada em `/workflows` no container):
```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
```

Antes de commitar, confira que nenhum JSON tem segredo: o export guarda só o **id** das credenciais, não o valor.
```bash
grep -iE "sk-ant|bot[0-9]+:|password" n8n/workflows/*.json
```
