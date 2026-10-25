-- Consultas usadas pelos fluxos agendados. Copie cada bloco para um nó Postgres.

-- ===== W5: indicadores da semana (um nó Postgres, Execute Query) =====
WITH msgs AS (
  SELECT * FROM mensagens WHERE canal = 'telegram' AND em >= now() - interval '7 days'
)
SELECT
  (SELECT count(DISTINCT chat_id) FROM msgs)                                   AS conversas,
  (SELECT count(*) FROM msgs)                                                  AS mensagens,
  round(100.0 * (SELECT count(*) FROM msgs WHERE acao = 'responder')
        / NULLIF((SELECT count(*) FROM msgs), 0), 1)                           AS resolucao_sem_humano_pct,
  round(100.0 * (SELECT count(*) FROM feedback f JOIN msgs m ON m.id = f.mensagem_id WHERE f.nota = 1)
        / NULLIF((SELECT count(*) FROM feedback f JOIN msgs m ON m.id = f.mensagem_id), 0), 1) AS positivos_pct,
  (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY latencia_ms) FROM msgs)  AS latencia_p50_ms,
  (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latencia_ms) FROM msgs) AS latencia_p95_ms,
  -- preço do modelo do W2 em US$/milhão de tokens; ajuste se trocar de modelo
  round(((SELECT coalesce(sum(tokens_entrada), 0) FROM msgs) * 0.10
       + (SELECT coalesce(sum(tokens_saida), 0) FROM msgs) * 0.50) / 1e6, 4)   AS custo_usd,
  (SELECT round(avg(extract(epoch FROM encerrado_em - aberto_em) / 60)::numeric, 1)
     FROM fila_humana WHERE encerrado_em >= now() - interval '7 days')         AS atendimento_humano_min;

-- ===== W5: top 10 lacunas da semana (vira {{ $json.lacunas }} no prompt) =====
SELECT string_agg(pergunta, E'\n' ORDER BY n DESC) AS lacunas
FROM (
  SELECT pergunta, count(*) AS n
  FROM lacunas_base
  WHERE NOT resolvida AND em >= now() - interval '7 days'
  GROUP BY pergunta
  ORDER BY n DESC
  LIMIT 10
) t;

-- ===== Retenção LGPD (Schedule Trigger diário, 3h) =====
-- Vários comandos numa query não aceitam parâmetros ($1); a expressão do n8n entra direto.
-- Number() garante que só um número chega ao SQL.
DELETE FROM n8n_chat_histories h
USING conversas c
WHERE h.session_id = c.chat_id::text
  AND c.ultima_msg_em < now() - make_interval(days => {{ Number($env.RETENCAO_DIAS) || 90 }});
DELETE FROM mensagens WHERE em < now() - make_interval(days => {{ Number($env.RETENCAO_DIAS) || 90 }});
DELETE FROM lacunas_base WHERE em < now() - make_interval(days => {{ Number($env.RETENCAO_DIAS) || 90 }});
DELETE FROM fila_humana WHERE status = 'encerrado' AND encerrado_em < now() - make_interval(days => {{ Number($env.RETENCAO_DIAS) || 90 }});
DELETE FROM conversas WHERE ultima_msg_em < now() - make_interval(days => {{ Number($env.RETENCAO_DIAS) || 90 }});
