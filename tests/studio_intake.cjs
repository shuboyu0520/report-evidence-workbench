const { test } = require('node:test');
const assert = require('node:assert/strict');
const { details } = require('../docs/studio/split-receipts.js');
const { estimate, exchangeTarget } = require('../docs/studio/split-assistant.js');
const { members, summarize, quote, convertedCents } = require('../docs/studio/split-tools.js');

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

test('one receipt and a locked rate produce one settlement for precisely the selected people', () => {
  const receipt=details('BAY CAFE\nTOTAL AUD 62.41');
  const data={...receipt,receipt,description:'晚餐',payer:12,people:[13,11,12],
    fx:{currency:'CNY',rate:'4.70',source:'manual'}};
  const result=quote(data);
  assert.equal(result.cents,6241);
  assert.deepEqual(result.settlement,{currency:'CNY',cents:29333,shares:[
    {id:11,cents:9778},{id:12,cents:9778},{id:13,cents:9777}]});
  assert.equal(summarize([data],members,'AUD').entries.length,0);
  const two={...data,people:[11,13],split_mode:'exact',split_values:{11:'20.00',13:'42.41'}};
  assert.deepEqual(summarize([two],members,'CNY').transfers,[
    {from:11,to:12,cents:9400},{from:13,to:12,cents:19933}]);
});

test('FX rounds a single total in decimal arithmetic and splits by the original agreement', () => {
  assert.equal(exchangeTarget('这笔 AUD 换成 CNY 每人多少？','AUD'),'CNY');
  assert.equal(exchangeTarget('按美元换成澳元结算','AUD'),'AUD');
  assert.equal(convertedCents('1.00','1.005'),101);
  assert.equal(convertedCents('99999999.99','1.00000000'),9999999999);
  assert.equal(convertedCents('99999999.99','10'),null);
  for(const rate of ['0','-2','1e2','4.123456789','']) assert.equal(convertedCents('10',rate),null);
  const d={description:'晚餐',payer:11,people:[13,12,11],amount:'0.01',currency:'AUD',fx:{currency:'CNY',rate:'4.7'}};
  assert.deepEqual(quote(d).settlement.shares.map(s=>s.cents),[2,2,1]);
  for(const [mode,vals] of [['percentage',{11:'50',12:'50',13:'0'}],['ratio',{11:'1',12:'1',13:'2'}]]) {
    const q=quote({...d,split_mode:mode,split_values:vals}).settlement;
    assert.equal(q.shares.reduce((sum,s)=>sum+s.cents,0),5);
    assert.deepEqual(q.shares.map(s=>s.cents),mode==='ratio'?[1,1,3]:[3,2,0]);
  }
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
  assert.equal((await ask('这张外国小票按人民币结账每个人承担多少？')).tool, 'exchange');
  assert.match((await ask('北京明天会下雨吗')).message, /你想算一笔/);
});
