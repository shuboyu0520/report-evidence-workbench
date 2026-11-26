const { test } = require('node:test');
const assert = require('node:assert/strict');
const { details } = require('../docs/studio/split-receipts.js');

test('Chinese ticket extracts item names and extended prices before the payable total', () => {
  const photographed = details('松 风 小 馆\n\n示例 小 票\n\n青椒 炒 肉 90.00\n冰 红 茶 30.00\n实 付 金 额 120.00 元');
  assert.equal(photographed.amount, '120.00');
  assert.deepEqual(photographed.items, [
    {description:'青椒炒肉',amount:'90.00'}, {description:'冰红茶',amount:'30.00'}
  ]);
  const bill = details([
    '海 湾 小 馆', '订单 0518', '菜品 数量 单价 金额',
    '烤 鸭 1 90.00 90.00', '酸梅汤 2 杯 15.00 30.00',
    '餐品小计 120.00', '实 付 金额 ￥120.00', '消费积分 120'
  ].join('\n'));
  assert.equal(bill.amount, '120.00');
  assert.equal(bill.currency, 'CNY');
  assert.deepEqual(bill.items, [
    {description:'烤鸭',amount:'90.00'}, {description:'酸梅汤',amount:'30.00'}
  ]);
});

test('English receipt keeps repeated items, checks quantities and excludes tenders and fees', () => {
  const bill = details([
    'BAY BISTRO', 'SHOP NO 482', 'TABLE 7', 'QTY ITEM UNIT PRICE AMOUNT',
    '2 x Roast Chicken 45.00 90.00', 'Iced Tea 2 x 7.50 15.00', 'Iced Tea 7.50 2 15.00',
    'SUBTOTAL 120.00', 'Service charge 4.00', 'Discount 2.00',
    'TAX 1.00', 'TOTAL AUD 123.00', 'Cash 150.00', 'Change 27.00'
  ].join('\n'));
  assert.deepEqual(bill.items, [
    {description:'Roast Chicken',amount:'90.00'},
    {description:'Iced Tea',amount:'15.00'}, {description:'Iced Tea',amount:'15.00'}
  ]);
  assert.equal(bill.amount, '123.00');
});

test('incomplete or conflicting price columns stay for manual review', () => {
  const bill = details([
    '菜钱90.00', '饮料30元', 'Hot tea 2 x 15.00', 'Fruit 2 12.00 25.00',
    'Pear 12.00 16.00', 'Return -6.50', '花茶 2杯 5.00',
    '子项 USD 12.00', 'TOTAL CNY 120.00'
  ].join('\n'));
  assert.deepEqual(bill.items, [
    {description:'菜钱',amount:'90.00'}, {description:'饮料',amount:'30.00'}
  ]);
  assert.deepEqual(details('Refund receipt\nRoast 90.00\nTotal USD 90.00').items, []);
  assert.deepEqual(details('Rice USD 90.00\nWine AUD 30.00\nTOTAL $120.00').items, []);
});

test('the quantity column may have only an extended amount when it is explicitly labelled', () => {
  assert.deepEqual(details('品名 数量 金额\n饮料 2 30\n总计 ￥30').items,
    [{description:'饮料',amount:'30.00'}]);
  assert.deepEqual(details('Qty Item Amount\n2 x Juice Box 30.00\nTOTAL $30.00').items,
    [{description:'Juice Box',amount:'30.00'}]);
  assert.deepEqual(details('Qty Item Unit Price\n2 x Juice Box 15.00\nTOTAL $30.00').items,
    [{description:'Juice Box',amount:'30.00'}]);
  assert.deepEqual(details('Qty Item Unit Price Amount\n2 x Juice Box 15.00\nTOTAL $30.00').items, []);
  assert.deepEqual(details('品名 数量 单价 金额\n矿泉水 1 3.00\n冷饮 2 1.50').items, []);
  assert.deepEqual(details('商品 数量 单价\n矿泉水 1 3.00\n凉茶 2 3.00').items,
    [{description:'矿泉水',amount:'3.00'}, {description:'凉茶',amount:'6.00'}]);
  assert.deepEqual(details('Salt and Pepper Beef\n90.00\nTOTAL $90.00').items, []);
  assert.deepEqual(details('Salt and Pepper Beef 90.00\nTOTAL $90.00').items,
    [{description:'Salt and Pepper Beef',amount:'90.00'}]);
});

test('an explicit unit-only price table yields line totals in integer cents', () => {
  assert.deepEqual(details('商品 单价 数量\n矿泉水 3.00 2瓶\n果汁 1.41 3杯\n合计 ￥10.23').items,
    [{description:'矿泉水',amount:'6.00'}, {description:'果汁',amount:'4.23'}]);
  assert.deepEqual(details('商品 数量 单价\n矿泉水 2瓶 3.00\nJuice 3 x 1.41\nWater 4.50\n合计 ￥10.23').items,
    [{description:'矿泉水',amount:'6.00'}, {description:'Juice',amount:'4.23'}]);
});
