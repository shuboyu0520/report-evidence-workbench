'use strict';
const SplitTools = (() => {
  const members = [{id:11,name:'小林'},{id:12,name:'小周'},{id:13,name:'小陈'}];
  const currencies = ['AUD','CNY','USD'];
  function cents(text) {
    const m = /^(\d{1,8})(?:\.(\d{1,2}))?$/.exec(String(text ?? '').trim());
    if (!m) return null;
    const n = Number(m[1])*100 + Number((m[2] || '').padEnd(2,'0'));
    return n>0 ? n : null;
  }
  function major(n) { return (n/100).toFixed(2); }
  function quote(d) {
    const n = cents(d.amount);
    if (!n || !currencies.includes(d.currency) || !members.some(m=>m.id===d.payer) ||
        !Array.isArray(d.people) || !d.people.length || new Set(d.people).size!==d.people.length ||
        d.people.some(id=>!members.some(m=>m.id===id)) || !String(d.description || '').trim()) return null;
    const people = [...d.people].sort((a,b)=>a-b);
    const shares = people.map((id,i)=>({id,cents:Math.floor(n/people.length)+(i < n%people.length ? 1:0)}));
    return {cents:n,shares};
  }
  function parse(raw) {
    const text = raw.normalize('NFKC').trim();
    const draft = {description:'',amount:'',currency:'',payer:null,people:[]};
    const blocked = /不均[摊分]|不平[分摊]|[按分]比例|承担\s*\d|分别[付支]|分两笔|分成两笔|各付各|退款|退还|返现|不是|并非|没有付|没付|[−-]\s*\d/.test(text);
    const numerals = [...text.matchAll(/(?<![\d.])\d+(?:\.\d+)?(?![\d.])/g)];
    const values = [...text.matchAll(/(?:AUD|CNY|RMB|USD|A\$|US\$|¥|￥)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:元人民币|人民币|澳元|澳币|美元|美金|AUD|CNY|RMB|USD|元)/gi)];
    if (blocked || values.length>1 || numerals.length>1)
      return {data:draft,blocked:true,note:'请改写为一笔正金额的均摊支出，单独说明付款人和参与人。',trace:['检查费用笔数、分摊方式与金额方向','该描述需要拆分或澄清']};
    const currencyHints = [
      ['AUD',/澳元|澳币|\bAUD\b|A\$/i], ['USD',/美元|美金|\bUSD\b|US\$/i], ['CNY',/人民币|\bCNY\b|\bRMB\b|¥|￥/i]
    ].filter(([,rx])=>rx.test(text));
    const otherCurrency = /港元|港币|日元|韩元|新西兰元|新加坡元|加元|欧元|英镑/i.test(text);
    if (currencyHints.length>1 || otherCurrency) return {data:draft,blocked:true,note:'当前账本支持 AUD、CNY、USD。请用一种受支持的币种录入。',trace:['检查原币币种','币种不支持或存在冲突']};
    draft.currency = currencyHints[0]?.[0] || (/\d\s*元/.test(text)?'CNY':'');
    const amount = values[0]?.[1] || values[0]?.[2] || numerals[0]?.[0];
    if (cents(amount)) draft.amount = major(cents(amount));
    const known = members.filter(m=>text.includes(m.name));
    const proxy = text.match(/([小老阿][\u3400-\u9fff])\s*[替帮为]/);
    const payers = proxy ? members.filter(m=>m.name===proxy[1]) :
      members.filter(m=>new RegExp(m.name+'(?:先|来|已)?(?:垫[付了]?|支付|付[款了]?|买单|结账|出了)').test(text));
    if (payers.length===1 && !/谁付|付款人不[明详]|不知.*付/.test(text)) draft.payer=payers[0].id;
    const clauses = text.split(/[，,。；;!！]/).map(t=>t.trim()).filter(Boolean);
    const splitClause = clauses.find(c=>/均[分摊]|平[摊分]|各一半|一起分/.test(c));
    const namesIn = t=>members.filter(m=>t?.includes(m.name)).map(m=>m.id);
    if (splitClause && !/还没确定|未确定|未说|不清楚|还不知道/.test(text)) {
      const explicit = splitClause.match(/(?:只给|仅给|给|仅由|由|仅|替)(.+?)(?:均[摊分]|平[摊分]|各一半)/);
      const within = namesIn(explicit?.[1] || splitClause.replace(/^.*?(?:垫付|付了|支付了?)\s*[\d.]+[^，,。]{0,5}?(?:给|由)/,''));
      if (/全[组员部]|所有人|三个人|三人/.test(splitClause) || known.length===3 && /^均[摊分]$/.test(splitClause)) draft.people=members.map(m=>m.id);
      else if (within.length) draft.people=within;
      else if (proxy && /^两人/.test(splitClause)) draft.people=namesIn(text.split(proxy[0])[1]);
    }
    const label = text.match(/晚[餐饭]|午[餐饭]|早[餐饭]|打车|车费|超市|食材|咖啡|住宿|房租|门票|电影|停车|奶茶|酒店|早餐/);
    draft.description = label?.[0] || '';
    const missing = [!draft.description&&'费用说明',!draft.amount&&'金额',!draft.currency&&'币种',!draft.payer&&'付款人',!draft.people.length&&'分摊人'].filter(Boolean);
    return {data:draft,blocked:false,note:missing.length?'请补充'+missing.join('、')+'后核对。':'请核对每个人的分摊金额。',trace:['识别单笔费用与原币','与当前小组成员核对付款人和分摊人',missing.length?'等待补全字段':'按最小货币单位计算均摊']};
  }
  const samples = [
    {id:'example-taxi',description:'机场打车',amount:'37.50',currency:'AUD',payer:12,people:[12,13],sample:true},
    {id:'example-breakfast',description:'出发前早餐',amount:'24.00',currency:'AUD',payer:11,people:[11,12,13],sample:true}
  ];
  return {members,currencies,cents,major,quote,parse,samples};
})();
if (typeof module !== 'undefined') module.exports = SplitTools;
