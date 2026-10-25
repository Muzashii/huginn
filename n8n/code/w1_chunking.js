// W1 — nó Code "Seções e chunks" (modo: Run Once for All Items)
// Port de huginn_rag/chunking.py. Paridade testada em tests/test_paridade_js.py.
// Entrada: itens { documento, conteudo }. Saída: um item por chunk { pageContent, metadata, hash }.
// O Default Data Loader seguinte usa pageContent como texto e metadata como metadados.

const TAMANHO = 800;
const SOBREPOSICAO = 100;

function slugify(titulo) {
  return titulo
    .normalize('NFD')
    .replace(/[^\x00-\x7f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function separarSecoes(documento, conteudo) {
  const m = conteudo.match(/^atualizado_em:\s*(\S+)/m);
  const atualizadoEm = m ? m[1] : null;
  const partes = conteudo.split(/^## +(.+)$/m);
  const secoes = [];
  for (let i = 1; i + 1 < partes.length; i += 2) {
    const titulo = partes[i].trim();
    const texto = partes[i + 1].trim();
    if (texto) secoes.push({ documento, titulo, slug: slugify(titulo), texto, atualizadoEm });
  }
  return secoes;
}

function quebrar(texto, tamanho, sobreposicao) {
  if (texto.length <= tamanho) return [texto];
  const unidades = [];
  for (const paragrafo of texto.split(/\n\s*\n/)) {
    if (paragrafo.length <= tamanho) unidades.push(paragrafo.trim());
    else
      unidades.push(
        ...paragrafo
          .split(/(?<=[.!?])\s+/)
          .map((s) => s.trim())
          .filter(Boolean),
      );
  }
  const pedacos = [];
  let atual = '';
  for (const unidade of unidades) {
    const candidato = atual ? `${atual} ${unidade}`.trim() : unidade;
    if (candidato.length <= tamanho) {
      atual = candidato;
      continue;
    }
    if (atual) {
      pedacos.push(atual);
      let cauda = sobreposicao ? atual.slice(-sobreposicao) : '';
      cauda = cauda.includes(' ') ? cauda.slice(cauda.indexOf(' ') + 1) : cauda;
      atual = `${cauda} ${unidade}`.trim();
    } else {
      atual = unidade;
    }
    while (atual.length > tamanho) {
      pedacos.push(atual.slice(0, tamanho));
      atual = atual.slice(tamanho - sobreposicao);
    }
  }
  if (atual) pedacos.push(atual);
  return pedacos;
}

function gerarChunks(secoes, tamanho = TAMANHO, sobreposicao = SOBREPOSICAO) {
  const chunks = [];
  for (const s of secoes) {
    const fonte = `${s.documento}#${s.slug}`;
    quebrar(s.texto, tamanho, sobreposicao).forEach((pedaco, i) => {
      chunks.push({
        texto: `[fonte: ${fonte}] ${s.titulo}\n${pedaco}`,
        metadata: {
          documento: s.documento,
          secao: s.slug,
          titulo: s.titulo,
          fonte,
          atualizado_em: s.atualizadoEm,
          chunk: i,
        },
      });
    });
  }
  return chunks;
}

// --- execução dentro do n8n ---
if (typeof $input !== 'undefined') {
  const crypto = require('crypto');
  const saida = [];
  for (const item of $input.all()) {
    const { documento, conteudo } = item.json;
    const hash = crypto.createHash('sha256').update(conteudo, 'utf8').digest('hex');
    for (const c of gerarChunks(separarSecoes(documento, conteudo))) {
      saida.push({ json: { pageContent: c.texto, metadata: c.metadata, documento, hash } });
    }
  }
  return saida;
}

if (typeof module !== 'undefined') module.exports = { slugify, separarSecoes, gerarChunks };
