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

test('missing participants, conflicting currencies and refunds need clarification', () => {
  const missing = parse('小周付了 88 澳元的超市账单。参与人还没确定。');
  assert.deepEqual(missing.data.people,[]);
  assert.equal(quote(missing.data),null);
  for (const sentence of ['早餐 30 澳元，晚餐 60 澳元，分两笔。','小陈付了 10 港元买咖啡，全组均分。',
    '收到退款 -16 元。','小陈付 AUD 5 美元，全组均分。']) assert.equal(parse(sentence).blocked,true);
});

test('parse handwritten prices, named percentages and ordered shares as a single expense', () => {
  for (const [sentence,mode,expected] of [
    ['晚餐共 96 澳元，小林垫付。小林承担 48 澳元、小周承担 30 澳元、小陈承担 18 澳元。','exact',[4800,3000,1800]],
    ['小林垫了 90 澳元，小林承担 60、小周承担 30，不均摊。','exact',[6000,3000]],
    ['小周付了 120 澳元房租，小林占 50%、小周占 30%、小陈占 20%。','percentage',[6000,3600,2400]],
    ['小陈垫了 100 元买食材，小林、小周、小陈按 2:1:1 分摊。','ratio',[5000,2500,2500]],
    ['小周垫了100.01元住宿，小周和小林按2：1分摊。','ratio',[3334,6667]],
    ['小周垫了100.01元住宿，小周2份、小林1份。','ratio',[3334,6667]]
  ]) {
    const result=parse(sentence);
    assert.equal(result.blocked,false,sentence);assert.equal(result.data.split_mode,mode,sentence);
    assert.deepEqual(quote(result.data)?.shares.map(s=>s.cents),expected,sentence);
  }
});

test('ambiguous or incomplete uneven requests never confirm as equal or the named subset', () => {
  for (const text of [
    '小林垫付90元晚餐，三人不均摊。','小林垫付90元晚餐，小林和小周按比例分摊。',
    '小林垫付90元晚餐，小林承担50元、小周承担30元。','小林垫付90元晚餐，三人按金额分摊，小林承担90元。',
    '小林垫付90元晚餐，小林占80%、小吴占20%。','小林垫付90元晚餐，三人按2:1分摊。',
    '小林垫付90元晚餐，小周和小陈按2:1:1分摊。','小林付了90元晚餐，小林占50%、小林占50%。'
  ]) {
    const result=parse(text);
    assert.equal(result.blocked,false,text);assert.notEqual(result.data.split_mode,'equal',text);
    assert.equal(quote(result.data),null,text);
  }
});

const manual={description:'房租',amount:'0.03',currency:'CNY',payer:13,people:[12,11]};
test('percentages, ratios and exact amounts conserve every cent and sort ties by member ID', () => {
  for(const mode of ['ratio','percentage']) {
    const value=mode==='ratio'?'3':'50';
    assert.deepEqual(quote({...manual,split_mode:mode,split_values:{11:value,12:value}})?.shares,
      [{id:11,cents:2},{id:12,cents:1}]);
  }
  for(const [mode,values] of [['exact',{11:'0.03',12:'0'}],['percentage',{11:'100',12:'0'}]]) {
    assert.deepEqual(quote({...manual,split_mode:mode,split_values:values})?.shares,
      [{id:11,cents:3},{id:12,cents:0}]);
  }
  const large=quote({...manual,amount:'99999999.99',split_mode:'ratio',split_values:{11:'999999',12:'999998'}});
  assert.equal(large.shares.reduce((sum,s)=>sum+s.cents,0),9999999999);
});

test('reject ill-formed values and do not inherit stale configuration for other members or modes', () => {
  for(const [mode,values] of [
    ['',{}],['equal',{11:'2'}],['exact',{11:'0.02',12:'0.02'}],
    ['percentage',{11:'50.001',12:'49.999'}],['percentage',{11:'20',12:'30'}],
    ['ratio',{11:'3',12:'0'}],['ratio',{11:'-1',12:'3'}],['ratio',{11:'1e2',12:'3'}],
    ['ratio',{11:'3',12:'1000000'}],['ratio',{11:'3'}],['ratio',{11:'3',12:'2',13:'1'}],
    ['exact',{11:'0.03',12:0}],['ratio',{11:1,12:2}]
  ]) assert.equal(quote({...manual,split_mode:mode,split_values:values}),null);
});

test('grouping and magnitude are never dropped from a monetary amount', () => {
  assert.equal(parse('小林垫付房租 1,200 澳元，小林承担60%，小周承担40%。').data.amount,'1200.00');
  const large=parse('小林垫付房租 1,200,000.75 澳元，小林承担60%，小周承担40%。');
  assert.deepEqual(quote(large.data).shares.map(s=>s.cents),[72000045,48000030]);
  for(const amount of ['1.2 万','1.2k','1,20','12,009,12','1.23.45'])
    assert.equal(parse('小林垫付房租 '+amount+' 澳元，全组均分。').blocked,true,amount);
});

test('unresolved participants, exclusions, and unknown group members need an explicit correction', () => {
  for(const text of ['小林付了100澳元晚餐，小周和小吴均分。','小林付了100澳元晚餐，全组均分，小陈不参加。',
    '小林垫付99澳元酒店，小周2份，小林1份，小陈的份额待定。','小林付了100元晚饭，小周和小陈按2:1分摊，但是小陈的份数待定。',
    '小林付了100元晚饭，小吴、小周和小陈按2:1分摊。','小林垫付 99 澳元酒店，小周1份，小林2份，另有小陈。',
    '小林付了 75 澳元晚餐，本来小周和小陈要均分，后来改为小林和小周均分。']) assert.equal(quote(parse(text).data),null,text);
});

test('a third guest with an undecided share cannot leave a confirmable subset of guests', () => {
  for(const wording of ['份数未定','份额还没定']) {
    const {data}=parse('小林垫付 99 澳元酒店，小周2份，小林1份，小吴也一起住，'+wording+'。');
    assert.equal(data.amount,'99.00');
    assert.equal(data.split_mode,'');
    assert.deepEqual(data.split_values,{});
    assert.deepEqual(data.people,[]);
    assert.equal(quote(data),null);
  }
});
