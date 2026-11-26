const { test } = require('node:test');
const assert = require('node:assert/strict');
const { billTransfers, members, problem, quote, summarize } = require('../docs/studio/split-tools.js');

const meal = {
  description:'聚餐', currency:'CNY', amount:'120.00', payer:11, people:[13,12,11],
  split_mode:'items', items:[
    {description:'菜', amount:'90.00', people:[11,12,13]},
    {description:'饮料', amount:'30.00', people:[12,13]},
  ],
};

test('different diners per line still produce one balanced bill payable to the payer', () => {
  const q=quote(meal);
  assert.deepEqual(q.shares.map(s=>s.cents), [3000,4500,4500]);
  assert.deepEqual(q.itemShares[1].shares,[{id:12,cents:1500},{id:13,cents:1500}]);
  const repayments=[{from:12,to:11,cents:4500},{from:13,to:11,cents:4500}];
  assert.deepEqual(billTransfers(q,11),repayments);
  assert.deepEqual(summarize([meal],members,'CNY').transfers,repayments);
  const q2=quote({...meal, currency:'AUD', fx:{currency:'CNY', rate:'4.70'}});
  assert.deepEqual(q2.settlement.shares.map(s=>s.cents), [14100,21150,21150]);
  assert.deepEqual(billTransfers(q2,11).map(t=>t.cents), [21150,21150]);
});

test('line-level rounding and discounts stay with the assigned people, including a nonparticipating payer', () => {
  const items=[
    {description:'菜',amount:'20.01',people:[13,12]},
    {description:'饮料',amount:'3.00',people:[13]},
    {description:'饮料优惠',amount:'-1.00',people:[13]},
    {description:'赠品',amount:'0.00',people:[12]},
  ];
  const bill={...meal,amount:'22.01',people:[13,12],items};
  const q=quote(bill);
  assert.deepEqual(billTransfers(q,11), [{from:12,to:11,cents:1001},{from:13,to:11,cents:1200}]);
  for(const row of q.itemShares) assert.equal(row.shares.reduce((n,s)=>n+s.cents,0),row.cents);
  assert.equal(q.shares.reduce((n,s)=>n+s.cents,0),2201);
});

test('reject unallocated, overallocated, unsupported or conflicting items', () => {
  const [food, drinks]=meal.items;
  for(const item of [{...drinks,people:[]},{...drinks,people:[12,12]},{...drinks,people:[99]},
    {...drinks,description:''},{...drinks,amount:''},{...drinks,amount:'29.99'},{...drinks,amount:'30.001'}]) {
    assert.notEqual(problem({...meal,items:[food,item]}),'');
    assert.equal(quote({...meal,items:[food,item]}),null);
  }
  assert.equal(quote({...meal,people:[11,12]}),null);
  assert.equal(quote({...meal,items:[]}),null);
  assert.equal(quote({...meal,split_mode:'equal'}),null);
  assert.equal(quote({...meal,amount:'60',items:[food,{...drinks,amount:'-30',people:[13]}],
    split_values:{11:'1'}}),null);
  assert.equal(quote({...meal,amount:'50',items:[food,{...drinks,amount:'-40',people:[13]}]}),null);
});
