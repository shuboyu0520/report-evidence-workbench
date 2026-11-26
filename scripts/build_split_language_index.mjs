// Rebuild after changing the examples: node scripts/build_split_language_index.mjs
import {readFile, writeFile} from 'node:fs/promises';
import {createEncoder, modelId, packVector} from '../docs/studio/split-language.mjs';

const topics = [
  ['guide', '先选这笔费用覆盖的日期，数出每个人实际住了几天。在草稿中选择「按份数」，把各自的天数填为份数。若房东另收固定费用，可把固定部分单独记一笔，按大家约好的比例分。', [
    '室友月中才搬进来，水电费怎么算公平？', '旅行中途加入的人房费按住宿天数怎么分？', '合租有人只住一周，电费要按实际住的天数摊吗？']],
  ['guide', '在这一张账单选择「指定金额」。先分共同消费，再把个人点单加到对应的人名下。例如三人共点 90 元的菜，另有 30 元的酒只有一人喝，可以分别填 30、30、60 元，合计应与小票实付一致。', [
    '聚餐有人单独点了酒，其他人没喝，怎么分才合适？', '每个人点的餐价钱不一样，同桌怎么按各自消费付钱？', '外卖有人点了额外的菜，共用和自用的东西如何拆开？']],
  ['guide', '付款人选实际掏钱的那位。参与分摊只勾选真正消费的人，代付的人可以不参与。若对方还不在组里，先到「管理成员」添加，再核对草稿。', [
    '有人帮忙付钱但是没有参加活动怎么办？', '组外朋友替我们先刷卡了，应该把谁记成付款人？', '付款的人不吃饭不参与均摊可以吗？']],
  ['guide', '账本精确到分。均分或按份数分出尾数时，先给每人分配整数分，再把剩余的一两分钱分配出去，让所有人的份额相加刚好等于总额。可以在草稿的「每人应摊」里看明细。', [
    '除不尽的几分钱给谁？', '三个人均分为什么有人比别人多一分钱？']],
  ['exchange', '', [
    '旅途既花了美元又花澳元怎么办？', '不同币种的开销能一起换汇算吗？', '这张外国小票按人民币结账每个人承担多少？']],
  ['guide', '点「拍照读账单」，把小票拍清楚或从相册选图。对照识别出的实付行，检查总额和币种，再选付款人和参与者。若看到几个不同的合计，可以按原票填入。', [
    '怎么把收银条扫进账本？', '上传发票照片后金额识别不清该怎么改？']],
  ['guide', '在「成员余额」旁点「管理成员」，可以添加、改名、移出或恢复。有人临时不参加某笔消费时，只需在那笔草稿里取消勾选，这样会保留其他账单的成员记录。', [
    '新加入的小伙伴怎么加进这个小组？', '怎么删掉已经退组的成员，历史账单怎么办？']],
  ['guide', '在草稿下点「保存草稿」，下次从「已保存草稿」继续。确认前它不会计入余额。已经入账的费用也可以从「账单明细」展开后点「编辑账单」修改。', [
    '没商量好怎么先存起来下次继续填？', '之前已经记错的消费记录还能修改吗？']],
  ['guide', '如果大家已经讲好比例，在草稿的「分摊方式」选「按百分比」并填满 100%。如果只约好了谁出双份，就选「按份数」，例如两人出 2 份和 1 份。', [
    '我想让一个人承担两份，不均分怎么录？', '按照各自约定的百分比来承担怎么操作？']],
  ['settlement', '', ['最后我应该把钱打给哪位朋友？', '我们之前的账还没清，我想看小组转款清单', '已经记下的费用还有谁没还钱？']],
  ['quote', '', ['想看刚才这笔还没有确认的费用每人得出多少钱', '请展示目前草稿中每个人的份额']],
  ['price', '', ['帮忙算算优惠之后的实付和每人价格', '能帮我算折扣和餐厅小费吗？']],
  ['draft', '', ['我想把刚花的钱记录下来', '请把这笔开销整理成待确认的账单']],
  [null, '', ['明天上海天气怎么样？', '写一首关于月亮的诗', '能推荐股票或者预测行情吗？', '怎么制作蛋糕？', '你最喜欢哪个电影明星？']],
];

const studio = new URL('../docs/studio/', import.meta.url);
const asset = name => readFile(new URL('vendor/bge/' + name, studio));
const embed = await createEncoder((await asset('vocab.txt')).toString('utf8'), await asset('bge-small-zh-int8.onnx'), await asset('ort-wasm-simd-threaded.wasm'));
const index = {model: modelId, topics: []};
for (const [tool, message, questions] of topics) {
  const examples = [];
  for (const question of questions) {
    const bytes = packVector(await embed(question));
    examples.push({question, embedding: Buffer.from(bytes.buffer).toString('base64')});
  }
  index.topics.push({tool, message, examples});
}
await writeFile(new URL('split-language-index.json', studio), JSON.stringify(index, null, 2) + '\n');
console.log('Saved ' + topics.length + ' topics for ' + modelId);
