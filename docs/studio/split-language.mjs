import * as ort from './vendor/bge/ort.wasm.min.mjs';

const assets = new URL('./vendor/bge/', import.meta.url);
export const modelId = 'Xenova/bge-small-zh-v1.5@75c43b0/int8-cls-v1';

// The published Chinese BERT vocabulary uses basic tokenization and WordPiece.
function tokenIds(text, vocabulary) {
  const normalized = text.normalize('NFKC').toLowerCase().normalize('NFD')
    .replace(/\p{M}/gu, '').replace(/\p{Script=Han}/gu, ' $& ');
  const words = normalized.match(/[\p{L}\p{N}]+|[^\s\p{C}]/gu) || [];
  const ids = [vocabulary.get('[CLS]')];
  for (const word of words) {
    const pieces = [];
    for (let start = 0; start < word.length;) {
      let end = word.length;
      while (end > start) {
        const piece = (start ? '##' : '') + word.slice(start, end);
        if (vocabulary.has(piece)) { pieces.push(vocabulary.get(piece)); break; }
        end--;
      }
      if (end === start) { pieces.splice(0, pieces.length, vocabulary.get('[UNK]')); break; }
      start = end;
    }
    ids.push(...pieces);
    if (ids.length >= 127) break;
  }
  return [...ids.slice(0, 127), vocabulary.get('[SEP]')];
}

export async function createEncoder(vocabText, model = new URL('bge-small-zh-int8.onnx', assets).href, wasmBytes) {
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = assets.href;
  if (wasmBytes) ort.env.wasm.wasmBinary = wasmBytes;
  const session = await ort.InferenceSession.create(model, {executionProviders: ['wasm']});
  const vocabulary = new Map(vocabText.trimEnd().split(/\r?\n/).map((word, i) => [word, i]));
  return async text => {
    const ids = tokenIds(text, vocabulary);
    const shape = [1, ids.length];
    const feeds = {
      input_ids: new ort.Tensor('int64', BigInt64Array.from(ids, BigInt), shape),
      attention_mask: new ort.Tensor('int64', new BigInt64Array(ids.length).fill(1n), shape),
    };
    if (session.inputNames.includes('token_type_ids')) {
      feeds.token_type_ids = new ort.Tensor('int64', new BigInt64Array(ids.length), shape);
    }
    const output = session.outputNames.includes('last_hidden_state') ? 'last_hidden_state' : session.outputNames[0];
    const result = await session.run(feeds, [output]);
    const tensor = result[output];
    const vector = tensor.data.slice(0, tensor.dims.at(-1)); // BGE uses the CLS embedding.
    tensor.dispose();
    return vector;
  };
}

// Store normalized exemplars as signed bytes; compare by cosine, including after quantization.
export function packVector(vector) {
  const scale = Math.max(...vector.map(Math.abs)) || 1;
  return Int8Array.from(vector, value => Math.round(127 * value / scale));
}

export function prepareIndex(index) {
  if (index.model !== modelId) throw Error('模型索引版本不匹配，请重新打开应用。');
  return index.topics.map(({tool, message, examples}) => ({
    tool, message, vectors: examples.map(({embedding}) => {
      const bytes = Uint8Array.from(atob(embedding), char => char.charCodeAt(0));
      const values = new Int8Array(bytes.buffer);
      return {values, norm: Math.hypot(...values)};
    }),
  }));
}

export function matchTopic(vector, topics) {
  const norm = Math.hypot(...vector);
  const matches = topics.map(topic => {
    const score = Math.max(...topic.vectors.map(({values, norm: otherNorm}) => {
      let dot = 0;
      for (let i = 0; i < values.length; i++) dot += vector[i] * values[i];
      return dot / (norm * otherNorm);
    }));
    return {tool: topic.tool, message: topic.message, score};
  }).sort((a, b) => b.score - a.score);
  const best = matches[0];
  if (!best?.tool || best.score < 0.54 || best.score - matches[1].score < 0.018) {
    return {tool: 'guide', message: '你想算一笔费用、分配某项开销，还是查看已经记下的欠款？告诉我发生了什么，我可以帮你选分摊方式。'};
  }
  return {tool: best.tool, message: best.message};
}
