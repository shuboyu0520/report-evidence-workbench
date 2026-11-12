'use strict';
const SplitTools = (() => {
  const members = [{id:11,name:'小林'},{id:12,name:'小周'},{id:13,name:'小陈'}];
  const currencies = ['AUD','CNY','USD'];
  const labels = {equal:'均分',exact:'按金额',percentage:'按百分比',ratio:'按份数'};
  const names = members.map(member=>member.name).join('|');
  const numberPattern = '\\d+(?:\\.\\d+)?';
  const currencyPattern = '元人民币|人民币|澳元|澳币|美元|美金|AUD|CNY|RMB|USD|元';
  function minor(value) {
    const match = /^(\d{1,8})(?:\.(\d{1,2}))?$/.exec(String(value ?? '').trim());
    return match ? Number(match[1]) * 100 + Number((match[2] || '').padEnd(2,'0')) : null;
  }
  function cents(text) { const value=minor(text); return value > 0 ? value : null; }
  function major(n) { return (n/100).toFixed(2); }
  function modeOf(d) { return d.split_mode === undefined ? 'equal' : d.split_mode; }
  function readValues(d) {
    const mode=modeOf(d), values=d.split_values || {};
    if (mode==='equal') return Object.keys(values).length ? null : d.people.map(()=>1);
    if (!Object.hasOwn(labels,mode) || typeof values!=='object' || Array.isArray(values) ||
        Object.keys(values).length!==d.people.length || d.people.some(id=>!Object.hasOwn(values,id))) return null;
    const result=d.people.map(id=>{
      const value=values[id];
      if (typeof value !== 'string') return null;
      if (mode==='ratio') return /^[1-9]\d{0,5}$/.test(value) ? Number(value) : null;
      const scaled=minor(value);
      return scaled!==null && (mode!=='percentage' || scaled<=10000) ? scaled : null;
    });
    return result.includes(null) ? null : result;
  }
  function problem(d) {
    if (!String(d.description || '').trim()) return '请填写费用说明。';
    if (!cents(d.amount)) return '总金额须大于零，最多两位小数。';
    if (!currencies.includes(d.currency)) return '请选择币种。';
    if (!members.some(m=>m.id===d.payer)) return '请选择实际垫付的人。';
    if (!Array.isArray(d.people) || !d.people.length || new Set(d.people).size!==d.people.length ||
        d.people.some(id=>!members.some(m=>m.id===id))) return '请选择参与这笔支出的组员。';
    const mode=modeOf(d);
    if (!Object.hasOwn(labels,mode)) return '请选择分摊方式，并核对每个人的份额。';
    const values=readValues(d);
    if (!values) {
      return {equal:'均分无需另填份额。',exact:'请填写每人的金额，最多两位小数。',percentage:'请填写每人的百分比（0–100），最多两位小数。',ratio:'每人的份数须为 1 至 999999 的整数。'}[mode];
    }
    const diff=(mode==='percentage'?10000:cents(d.amount))-values.reduce((a,b)=>a+b,0);
    if ((mode==='exact'||mode==='percentage') && diff!==0) {
      return (diff>0?'还差 ':'超出 ')+(mode==='exact'?d.currency+' ':'')+major(Math.abs(diff))+(mode==='percentage'?'%':'')+'，请调整后入账。';
    }
    return '';
  }
  function quote(d) {
    if (problem(d)) return null;
    const total=cents(d.amount), values=readValues(d);
    const shares=d.people.map((id,i)=>({id,cents:values[i]})).sort((a,b)=>a.id-b.id);
    if (modeOf(d)!=='exact') {
      const denominator=BigInt(values.reduce((a,b)=>a+b,0));
      const fractions=shares.map(share=>{
        const numerator=BigInt(total)*BigInt(share.cents);
        share.cents=Number(numerator / denominator);
        return {share,remainder:Number(numerator % denominator)};
      });
      const left=total-shares.reduce((sum,share)=>sum+share.cents,0);
      fractions.sort((a,b)=>b.remainder-a.remainder || a.share.id-b.share.id);
      for(let index=0;index<left;index++) fractions[index].share.cents++;
    }
    return {cents:total,shares};
  }
  function orderedPeople(text) {
    return [...new Set(Array.from((text || '').matchAll(new RegExp(names,'g')),m=>members.find(p=>p.name===m[0]).id))];
  }
  function unknownMember(text) {
    return Array.from((text || '').matchAll(/[小老阿][\u3400-\u9fff]/g),m=>m[0]).some(name=>
      !['小组','小计','小票'].includes(name) && !members.some(member=>member.name===name));
  }
  const personPattern='[小老阿][\\u3400-\\u9fff]';
  const listPattern=personPattern+'(?:\\s*(?:、|和|与|及|跟|,|\\+)\\s*'+personPattern+')+';
  function splitDetails(text) {
    const ratios=text.match(/\d+(?:\.\d+)?(?:\s*:\s*\d+(?:\.\d+)?)+/g) || [];
    const ratioTag=/按份|份数|[权份]重|份额|配比/.test(text);
    const percentTag=/百分|%/.test(text);
    const exactTag=/按(?:实际)?金额|各自金额|承担\s*\d|各付各|实付分摊/.test(text);
    const unevenTag=/不[均平][摊分]|非均[分摊]|不平均|不一样|[按分]比例|三七开|四六开|多[付款承担出]|少[付款承担出]/.test(text);
    const pairs=[];
    // Match an explicit member share, keeping payer phrases like 小林付了200元 outside.
    const pairRx=new RegExp('([小老阿][\\u3400-\\u9fff])\\s*(承担|分[摊担]|负担|应[付出]|占比?|分到|出|各付)?\\s*('+numberPattern+')\\s*(%|份|'+currencyPattern+')?', 'gi');
    for (const m of text.matchAll(pairRx)) pairs.push({name:m[1],id:members.find(p=>p.name===m[1])?.id,verb:m[2],value:m[3],unit:m[4] || '',at:m.index,end:m.index+m[0].length});
    const types=new Set();
    for(const pair of pairs) {
      if(pair.unit==='%') types.add('percentage');
      else if(pair.unit==='份') types.add('ratio');
      else if(pair.unit || exactTag) types.add('exact');
    }
    if (ratios.length || ratioTag) types.add('ratio');
    if (percentTag) types.add('percentage');
    if (exactTag && !percentTag && !ratios.length && !ratioTag && !pairs.some(p=>p.unit==='份')) types.add('exact');
    let mode=types.size===1 ? [...types][0] : (types.size || unevenTag ? '' : 'equal');
    const values={}, people=[];
    let ambiguous=types.size>1 || ratios.length>1;
    function assign(id,value) {
      if (!id || Object.hasOwn(values,id)) {ambiguous=true;return;}
      values[id]=value;people.push(id);
    }
    if (ratios.length===1) {
      const at=text.indexOf(ratios[0]);
      const before=text.slice(0,at).match(new RegExp('('+listPattern+')\\s*(?:(?:两|三|二)人)?\\s*(?:按(?:照)?|以)?\\s*(?:比例(?:为)?|份数(?:为)?)?\\s*$'));
      const after=text.slice(at+ratios[0].length).match(new RegExp('^\\s*(?:的?比例)?\\s*[,，]?\\s*(?:分别)?(?:由|给)?\\s*('+listPattern+')'));
      const group=before?.[1] || after?.[1], ids=orderedPeople(group);
      const parts=ratios[0].split(/\s*:\s*/);
      if (!unknownMember(group) && ids.length===parts.length && !pairs.length) ids.forEach((id,i)=>assign(id,parts[i]));
      else ambiguous=true;
    } else if(mode!=='equal') {
      for(const pair of pairs) assign(pair.id,pair.value);
    }
    // A named pair can be only part of the party; keep unmatched members empty.
    const declared=text.match(new RegExp('('+listPattern+')\\s*(?:两人|三人)?\\s*(?:分[摊担]|按(?:金额|百分比|份数|比例)|共同承担)'));
    if (unknownMember(declared?.[1])) ambiguous=true;
    for(const id of orderedPeople(declared?.[1])) if (!people.includes(id)) people.push(id);
    if(/全[组员部]|所有人|[三3]个人|[三3]人/.test(text)) {
      for (const m of members) if (!people.includes(m.id)) people.push(m.id);
    }
    if (ambiguous) mode='';
    // Mask member-specific figures before looking for the overall expense. Keep offsets stable.
    const chars=text.split('');
    for (const pair of pairs) for (let i=pair.at;i<pair.end;i++) chars[i]=' ';
    let totalText=chars.join('');
    for(const ratio of ratios) totalText=totalText.replace(ratio,' ');
    return {mode,values:ambiguous?{}:values,people,totalText};
  }
  function parse(raw) {
    const text=raw.normalize('NFKC').trim()
      .replace(/(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d,])/g,number=>number.replaceAll(',',''));
    const draft={description:'',amount:'',currency:'',payer:null,people:[],split_mode:'',split_values:{}};
    const stop=note=>({data:draft,blocked:true,note,trace:['校验费用笔数、币种与金额方向','需单独核对原始描述']});
    if (/\d\s*,\s*\d|\d+\.\d+\.|\d\s*(?:[万萬亿億千百]|[kmb](?![a-z]))/i.test(text))
      return stop('请将金额写成完整数字，例如 12000.00 澳元，并核对每人份额。');
    if (/分(?:成)?两笔|退款|退还|返现|不是|并非|没有付|没付|[−-]\s*\d/.test(text)) return stop('请分别录入单笔正向支出，核对付款人后重试。');
    const currencyHints=[
      ['AUD',/澳元|澳币|AUD|A\$/i],['USD',/美元|美金|USD|US\$/i],['CNY',/人民币|CNY|RMB|¥|￥/i]
    ].filter(([,rx])=>rx.test(text));
    if(currencyHints.length>1 || /港元|港币|日元|韩元|新西兰元|新加坡元|加元|欧元|英镑/.test(text))
      return stop('当前账本支持 AUD、CNY、USD。请用一种受支持的币种录入。');
    draft.currency=currencyHints[0]?.[0] || (/\d\s*元/.test(text)?'CNY':'');
    const spec=splitDetails(text);
    draft.split_mode=spec.mode;
    const amountRx=new RegExp('(?:AUD|CNY|RMB|USD|A\\$|US\\$|¥|￥)\\s*('+numberPattern+')|('+numberPattern+')\\s*(?:'+currencyPattern+')','gi');
    const amounts=[...spec.totalText.matchAll(amountRx)];
    if(amounts.length>1) return stop('识别到多笔总金额，请分别录入。');
    const lone=spec.totalText.match(/\d+(?:\.\d+)?/g) || [];
    const amount=amounts[0]?.[1] || amounts[0]?.[2] || (lone.length===1 ? lone[0]:null);
    if(cents(amount)) draft.amount=major(cents(amount));
    const proxy=text.match(/([小老阿][\u3400-\u9fff])\s*[替帮为]/);
    const payers=proxy ? members.filter(m=>m.name===proxy[1]) :
      members.filter(m=>new RegExp(m.name+'(?:先|来|已)?(?:垫[付了]?|支付|付[款了]?|买单|结账|出了)').test(text));
    if(payers.length===1 && !/谁付|付款人不[明详]|不知.*付/.test(text)) draft.payer=payers[0].id;
    if (spec.mode!=='equal') {
      draft.split_values=spec.values;
      draft.people=[...spec.people].sort((a,b)=>a-b);
    } else if(!/还没确定|未确定|未说|不清楚|还不知道/.test(text)) {
      const clause=text.split(/[,。;!！]/).map(c=>c.trim()).find(c=>/均[分摊]|平[摊分]|各一半|一起分/.test(c));
      const match=clause?.match(/(?:只给|仅给|给|仅由|由|仅|替)(.+?)(?:均[摊分]|平[摊分]|各一半)/);
      const ids=orderedPeople(match?.[1] || clause);
      if(unknownMember(match?.[1] || clause)) draft.people=[];
      else if(clause && (/全[组员部]|所有人|[三3](?:个)?人/.test(clause) || orderedPeople(text).length===3 && /^均[摊分]$/.test(clause))) draft.people=members.map(m=>m.id);
      else if(ids.length) draft.people=ids;
      else if(proxy && /^两人/.test(clause || '')) draft.people=orderedPeople(text.split(proxy[0])[1]);
    }
    const uncertain=/待定|待确认|不确[定认]|未(?:定|确[定认])|还没(?:定|确[定认])|还不知道|暂缓/.test(text);
    const exception=/不参加|不参与|不算|不包括|不承担|不分摊|除[去外了]|剩余|剩下|其余/.test(text);
    const revised=/(?:另有|还有|加上|另加)\s*[小阿老]|[小阿老][\u3400-\u9fff]\s*也(?:一起|参加|参与|要分)|改[为成]|重新分摊/.test(text);
    if (uncertain || exception || revised) {
      draft.split_mode='';draft.split_values={};draft.people=[];
    }
    const description=text.match(/晚[餐饭]|午[餐饭]|早[餐饭]|打车|车费|超市|食材|咖啡|住宿|房租|门票|电影|停车|奶茶|酒店|餐费|吃饭|水电|杂货|机票|民宿|打球/);
    draft.description=description?.[0] || (draft.split_mode!=='equal' && draft.amount ? text.split(/[,。;]/)[0].slice(0,100) : '');
    const issue=problem(draft);
    return {data:draft,blocked:false,note:issue || '请核对各成员的分摊金额后入账。',trace:['识别原币总金额与付款人',draft.split_mode?'提取分摊方式：'+labels[draft.split_mode]:'分摊规则待说明',issue?'等待补全或更正字段':'按最小货币单位核对分摊总额']};
  }
  const samples=[
    {id:'example-taxi',description:'机场打车',amount:'37.50',currency:'AUD',payer:12,people:[12,13],split_mode:'exact',split_values:{12:'20.00',13:'17.50'},sample:true},
    {id:'example-breakfast',description:'出发前早餐',amount:'24.00',currency:'AUD',payer:11,people:[11,12,13],sample:true}
  ];
  return {members,currencies,labels,modeOf,cents,major,problem,quote,parse,samples};
})();
if (typeof module !== 'undefined') module.exports=SplitTools;
