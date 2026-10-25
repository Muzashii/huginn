// W2 — nó Code "Filtro de entrada" (modo: Run Once for All Items)
// Mesma lógica de huginn_rag/lgpd.py. Paridade testada em tests/test_paridade_js.py.
// Entrada: item do Telegram Trigger. Saída: chat_id, texto mascarado, comando e flags.

const TAMANHO_MAXIMO = 1000;
const COMANDOS = ['/start', '/humano', '/encerrar'];

const CARTAO = /\b(?:\d[ -]?){12,18}\d\b/g;
const CPF = /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b/g;
const INJECAO = new RegExp(
  'ignore (?:as |todas as )?(?:suas |minhas )?(?:regras|instru[cç][oõ]es)|' +
    'esque[cç]a (?:as |suas )?(?:regras|instru[cç][oõ]es)|' +
    'voc[eê] agora [eé]|modo desenvolvedor|prompt do sistema|system prompt',
  'i',
);

function luhnValido(digitos) {
  let soma = 0;
  [...digitos].reverse().forEach((c, i) => {
    let n = Number(c);
    if (i % 2 === 1) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    soma += n;
  });
  return soma % 10 === 0;
}

function mascarar(texto) {
  const encontrados = [];
  const novo = texto.replace(CARTAO, (m) => {
    const d = m.replace(/\D/g, '');
    return d.length >= 13 && d.length <= 19 && luhnValido(d) ? '[CARTAO]' : m;
  });
  if (novo !== texto) encontrados.push('cartao');
  const final = novo.replace(CPF, '[CPF]');
  if (final !== novo) encontrados.push('cpf');
  return [final, encontrados];
}

function detectarComando(texto) {
  const t = texto.trim();
  const primeiro = t ? t.split(/\s+/)[0].toLowerCase().split('@')[0] : '';
  return COMANDOS.includes(primeiro) ? primeiro : null;
}

function filtrarEntrada(texto) {
  texto = (texto || '').trim();
  const truncado = texto.length > TAMANHO_MAXIMO;
  if (truncado) texto = texto.slice(0, TAMANHO_MAXIMO);
  const [limpo, mascarados] = mascarar(texto);
  return {
    texto: limpo,
    comando: detectarComando(limpo),
    mascarados,
    truncado,
    suspeita_injecao: INJECAO.test(limpo),
    vazio: !limpo,
  };
}

// --- execução dentro do n8n ---
// Recebe dois gatilhos: mensagem privada do Telegram (via roteador) ou o webhook de avaliação.
if (typeof $input !== 'undefined') {
  return $input.all().map((item) => {
    const body = item.json.body;
    if (body && body.pergunta !== undefined) {
      // avaliação: chat_id reservado -1, memória isolada por `sessao`
      return {
        json: { canal: 'eval', chat_id: -1, sessao: String(body.sessao || Date.now()), message_id: null,
          nome: 'eval', tem_arquivo: false, arquivo_nome: null, inicio_ms: Date.now(), ...filtrarEntrada(body.pergunta) },
      };
    }
    const msg = item.json.message || {};
    return {
      json: {
        canal: 'telegram',
        chat_id: msg.chat?.id,
        sessao: String(msg.chat?.id),
        message_id: msg.message_id,
        nome: msg.from?.first_name || '',
        tem_arquivo: Boolean(msg.document),
        arquivo_nome: msg.document?.file_name || null,
        inicio_ms: Date.now(),
        ...filtrarEntrada(msg.text || msg.caption || ''),
      },
    };
  });
}

if (typeof module !== 'undefined') module.exports = { filtrarEntrada, luhnValido };
