const { test } = require('node:test');
const assert = require('node:assert/strict');
const { details } = require('../docs/studio/split-receipts.js');
const { estimate } = require('../docs/studio/split-assistant.js');
const { members, summarize } = require('../docs/studio/split-tools.js');

test('receipt intake uses an explicit total and preserves the evidence line', () => {
  const read = details('BAY CAFE\nSubtotal 56.73\nTOTAL GST 5.67\nTOTAL AUD 62.40\nCash 100.00\nChange 37.60');
  assert.equal(read.description, 'BAY CAFE');
  assert.equal(read.amount, '62.40');
  assert.equal(read.currency, 'AUD');
  assert.equal(read.source, 'TOTAL AUD 62.40');
  assert.equal(details('小馆\n税额 5.00\n应付金额\n￥1,230.50').amount, '1230.50');
  const chinese=details('海湾 小 馆\n消费 小 票\n餐 费 45.50\n实 付 金额 50.00 元');
  assert.equal(chinese.description, '海湾小馆');
  assert.equal(chinese.amount, '50.00');
  assert.equal(chinese.currency, 'CNY');
  assert.equal(chinese.source, '实 付 金额 50.00 元');
});

test('ambiguous totals, currency symbols and refunds stay in review', () => {
  assert.equal(details('TOTAL $62.40').currency, '');
  assert.equal(details('Subtotal AUD 20.00\nTotal tax 1.50\nTotal savings 3.00').amount, '');
  assert.equal(details('TOTAL AUD 62.40\nAMOUNT DUE AUD 72.40').amount, '');
  assert.equal(details('TOTAL PAID (10.00)').amount, '');
});

test('price estimate applies the discount before the tip and conserves cents', () => {
  assert.deepEqual(estimate('120 元打 8 折，加 10% 小费，三人均分'), {
    currency: 'CNY', original: 12000, discounted: 9600, surcharge: 960,
    total: 10560, people: 3, lower: 3520, extra: 0
  });
  const quote = estimate('AUD 100.01，三人 AA');
  assert.equal(quote.lower * quote.people + quote.extra, 10001);
  assert.equal(quote.extra, 2);
  assert.equal(estimate('每人 25 元，一共 3 人'), null);
  assert.equal(estimate('AUD 100，8 折，另有 10 元优惠券，3 人均分'), null);
  assert.equal(estimate('AUD 100，8 折，12.0001% 小费，3 人均分'), null);
});

test('settlement uses posted expenses in the requested currency', () => {
  const entry = { description:'晚餐', amount:'100.01', currency:'CNY', payer:11, people:[11,12,13] };
  const { total, transfers } = summarize([entry, {...entry,currency:'USD'}], members, 'CNY');
  assert.equal(total, 10001);
  assert.deepEqual(transfers, [{from:12,to:11,cents:3334}, {from:13,to:11,cents:3333}]);
});

test('the bundled phone model matches paraphrases and asks for clarification off topic', async () => {
  const {readFile} = require('node:fs/promises');
  const {join} = require('node:path');
  const {createEncoder, prepareIndex, matchTopic} = await import('../docs/studio/split-language.mjs');
  const studio = join(__dirname, '../docs/studio');
  const asset = name => readFile(join(studio, 'vendor/bge', name));
  const encode = await createEncoder((await asset('vocab.txt')).toString('utf8'),
    await asset('bge-small-zh-int8.onnx'), await asset('ort-wasm-simd-threaded.wasm'));
  const topics = prepareIndex(JSON.parse(await readFile(join(studio, 'split-language-index.json'), 'utf8')));
  const ask = async q => matchTopic(await encode(q), topics);
  assert.match((await ask('朋友到月底才搬来，只住了几天，水电账单怎么摊才好')).message, /天数/);
  assert.match((await ask('晚饭同桌有两个人点了红酒，其余人一口也没有喝，该怎么分')).message, /个人点单/);
  assert.equal((await ask('我需要向哪位伙伴转钱才能把之前的账清掉')).tool, 'settlement');
  assert.match((await ask('北京明天会下雨吗')).message, /你想算一笔/);
});
