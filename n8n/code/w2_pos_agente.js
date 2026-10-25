// W2 — nó Code "Validar saída do agente" (modo: Run Once for All Items)
// Garante o contrato JSON { resposta, fontes, confianca, acao } mesmo se o LLM errar o formato.
// Regra de segurança: na dúvida, chama humano. Testado em tests/test_paridade_js.py.

const CONFIANCAS = ['alta', 'media', 'baixa'];
const ACOES = ['responder', 'chamar_humano'];
// fontes válidas têm o formato do W1: 01_prazos_e_entrega.md#prazo-de-producao-em-resina
const FONTE = /^\d{2}_[a-z0-9_]+\.md(#[a-z0-9-]+)?$/;
const MSG_HUMANO = 'Vou passar sua dúvida para uma pessoa da equipe. Já já respondem por aqui.';

function extrairJson(saida) {
  if (saida && typeof saida === 'object') return saida.output && typeof saida.output === 'object' ? saida.output : saida;
  if (typeof saida !== 'string') return null;
  const ini = saida.indexOf('{');
  const fim = saida.lastIndexOf('}');
  if (ini < 0 || fim <= ini) return null;
  try {
    return JSON.parse(saida.slice(ini, fim + 1));
  } catch {
    return null;
  }
}

function validarSaida(saida) {
  const j = extrairJson(saida);
  if (!j || typeof j.resposta !== 'string' || !j.resposta.trim()) {
    return { resposta: MSG_HUMANO, fontes: [], confianca: 'baixa', acao: 'chamar_humano', motivo: 'saida_invalida' };
  }
  const fontes = (Array.isArray(j.fontes) ? j.fontes : []).map(String).filter((f) => FONTE.test(f));
  const confianca = CONFIANCAS.includes(j.confianca) ? j.confianca : 'baixa';
  let acao = ACOES.includes(j.acao) ? j.acao : 'chamar_humano';
  let motivo = acao === 'chamar_humano' ? 'sem_base' : null;
  if (acao === 'responder' && confianca === 'baixa') {
    acao = 'chamar_humano';
    motivo = 'baixa_confianca';
  }
  return { resposta: j.resposta.trim(), fontes, confianca, acao, motivo };
}

// Estimativa grosseira (1 token ≈ 4 caracteres em português); ver docs/decisoes.md.
const estimarTokens = (texto) => Math.ceil((texto || '').length / 4);

// --- execução dentro do n8n ---
if (typeof $input !== 'undefined') {
  const filtro = $('Filtro de entrada').first().json;
  return $input.all().map((item) => {
    const v = validarSaida(item.json.output ?? item.json);
    return {
      json: {
        ...v,
        canal: filtro.canal,
        chat_id: filtro.chat_id,
        pergunta: filtro.texto,
        latencia_ms: Date.now() - filtro.inicio_ms,
        tokens_entrada: estimarTokens(filtro.texto) + 1500, // + prompt de sistema e chunks (média medida)
        tokens_saida: estimarTokens(v.resposta),
      },
    };
  });
}

if (typeof module !== 'undefined') module.exports = { validarSaida, estimarTokens };
