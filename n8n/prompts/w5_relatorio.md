# Prompt do AI Agent do relatório semanal (W5)

Nó AI Agent **sem ferramentas**. O campo *Prompt (User Message)* recebe a lista de lacunas
da semana (saída da consulta `lacunas` de `db/consultas_relatorio.sql`).

```text
Abaixo estão perguntas de clientes que o assistente da loja não conseguiu responder nesta semana
(ou que receberam avaliação negativa). Cada linha é uma pergunta.

{{ $json.lacunas }}

Tarefa:
1. Agrupe as perguntas por tema (no máximo 5 temas), com a contagem de cada tema.
2. Para cada tema, sugira o título de uma nova seção da base de conhecimento e em qual arquivo ela entraria
   (01_prazos_e_entrega.md, 02_materiais_resina_vs_fdm.md, 03_cores_e_acabamento.md, 04_pintura_de_colecionaveis.md,
   05_cuidados_com_a_peca.md, 06_arquivos_aceitos_stl.md, 07_trocas_e_defeitos.md, 08_pagamento.md, 09_faq_geral.md, ou um arquivo novo).
3. Não invente respostas para as perguntas: só sugira o que precisa ser escrito.
Responda em português, em texto simples para Telegram, no máximo 15 linhas.
```
