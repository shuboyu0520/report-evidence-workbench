import {createEncoder, matchTopic, prepareIndex} from './split-language.mjs';

let resources;
async function load() {
  const [vocab, index] = await Promise.all([
    fetch(new URL('./vendor/bge/vocab.txt', import.meta.url)),
    fetch(new URL('./split-language-index.json', import.meta.url)),
  ]);
  if (!vocab.ok || !index.ok) throw Error('中文模型文件尚未就绪。');
  return {embed: await createEncoder(await vocab.text()), topics: prepareIndex(await index.json())};
}
self.onmessage = async ({data: question}) => {
  try {
    resources ||= load();
    const {embed, topics} = await resources;
    self.postMessage({plan: matchTopic(await embed(question), topics)});
  } catch {
    resources = null;
    self.postMessage({error: '设备暂时无法载入中文模型，请联网重试。'});
  }
};
