const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parse, quote} = require('../docs/studio/split-tools.js');

test('a new bill produces cent-exact shares in stable member order', () => {
  const parsed = parse('小陈垫了 100.01 元买食材，全组均分。');
  assert.equal(parsed.blocked, false);
  assert.equal(parsed.data.payer, 13);
  assert.equal(parsed.data.currency, 'CNY');
  assert.deepEqual(quote(parsed.data),{cents:10001,shares:[
    {id:11,cents:3334},{id:12,cents:3334},{id:13,cents:3333}
  ]});
});

test('an outside payer cannot become a member who was named as a beneficiary', () => {
  const {data} = parse('小吴替小林和小周支付了 19 澳元车费，两人平摊。');
  assert.equal(data.payer, null);
  assert.deepEqual(data.people,[11,12]);
  assert.equal(quote(data),null);
});

test('missing participants, non-even splits, conflicting currencies and refunds need clarification', () => {
  const missing = parse('小周付了 88 澳元的超市账单。参与人还没确定。');
  assert.deepEqual(missing.data.people,[]);
  assert.equal(quote(missing.data),null);
  for (const sentence of ['小林付了 90 澳元，小林承担 60、小周承担 30，不均摊。',
    '早餐 30 澳元，晚餐 60 澳元，分两笔。','小陈付了 10 港元买咖啡，全组均分。',
    '收到退款 -16 元。','小陈付 AUD 5 美元，全组均分。']) assert.equal(parse(sentence).blocked,true);
});
