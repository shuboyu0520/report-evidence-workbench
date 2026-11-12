const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parse, quote} = require('../docs/studio/split-tools.js');
const {roster, cases} = require('./member_split_cases.json');

for (const [sentence, payer, amounts] of cases) {
  test(sentence, () => {
    const {data, blocked} = parse(sentence, roster);
    if (blocked) assert.equal(amounts, null);
    else assert.equal(data.payer, payer);
    const result = quote(data, roster);
    const actual = result && Object.fromEntries(result.shares.map(s => [s.id, s.cents]));
    assert.deepEqual(actual, amounts);
  });
}

test('archived and empty rosters, replays and duplicate display names', () => {
  const oldBill = parse(cases[0][0], roster).data;
  const archived = roster.map(m => ({...m, active:m.id !== 61}));
  assert.equal(quote(oldBill, archived).cents, 1001);
  const fresh = parse('Ann付了10.01元晚餐，全组均分。', archived).data;
  assert.deepEqual(fresh.people, [11, 18, 42, 86]);
  assert.equal(parse(cases[0][0], archived).data.payer, null);
  assert.deepEqual(parse(cases[0][0], []).data.people, []);
  assert.equal(quote(oldBill, []), null);
  const ambiguous = [...roster, {id:99, name:'ＡＮＮ'}];
  assert.equal(parse('Ann付了10.01元晚餐，全组均分。', ambiguous).data.payer, null);
});
