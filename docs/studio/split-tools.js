'use strict';
const SplitTools = (() => {
  const members = [{id:11,name:'小林'},{id:12,name:'小周'},{id:13,name:'小陈'}];
  const currencies = ['AUD','CNY','USD'];
  const labels = {equal:'均分',exact:'按金额',percentage:'按百分比',ratio:'按份数'};
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
  function problem(d, roster=members) {
    if (!String(d.description || '').trim()) return '请填写费用说明。';
    if (!cents(d.amount)) return '总金额须大于零，最多两位小数。';
    if (!currencies.includes(d.currency)) return '请选择币种。';
    if (!roster.some(m=>m.id===d.payer)) return '请选择实际垫付的人。';
    if (!Array.isArray(d.people) || !d.people.length || new Set(d.people).size!==d.people.length ||
        d.people.some(id=>!roster.some(m=>m.id===id))) return '请选择参与这笔支出的组员。';
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
  function quote(d, roster=members) {
    if (problem(d,roster)) return null;
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
  // Replace literal names before parsing so punctuation and digits in a name
  // cannot become a money amount, a ratio, or part of a regex.
  const tokenPattern='[\\uE000-\\uF8FF]';
  function tagMembers(raw, roster) {
    const byName=new Map(), byToken=new Map();
    for (const member of roster) {
      const name=member.name.normalize('NFKC').trim().toLowerCase();
      if (!name) continue;
      if (byName.has(name)) { byName.set(name,'�'); continue; }
      const token=byName.size<6400 ? String.fromCharCode(0xE000+byName.size) : '�';
      byName.set(name,token);
      if (token!=='�') byToken.set(token,member.id);
    }
    const expressions=Array.from(byName.keys()).sort((a,b)=>b.length-a.length).map(name=>{
      const escaped=name.replace(/[$.*+?^{}()|[\]\\]/g,'\\$&');
      return (/^[a-z0-9_]/i.test(name)?'(?<![a-z0-9_])':'')+escaped+(/[a-z0-9_]$/i.test(name)?'(?![a-z_])':'');
    });
    const clean=raw.replace(/[\uE000-\uF8FF]/g,'�');
    const text=expressions.length?clean.replace(new RegExp(expressions.join('|'),'gi'),(name,at)=>{
      const left=clean.slice(0,at), right=clean.slice(at+name.length);
      if(/^[\u3400-\u9fff]/.test(name) && /[\u3400-\u9fff]$/.test(left) &&
          !/[和与及跟给由为替帮仅让向是人有上加请找同的了]$/.test(left)) return '�';
      if(/[\u3400-\u9fff]$/.test(name) && /^[\u3400-\u9fff]/.test(right) &&
          !/^(?:[和与及跟先来已替帮为把向给在共各按分付垫占出也应买结平均的不两二三四五六七八九十人]|支付|承担|负担|一起|一人|一份|参加|参与)/.test(right)) return '�';
      return byName.get(name.toLowerCase()) || '�';
    }):clean;
    return {text,byToken};
  }
  function orderedPeople(text, byToken) {
    return [...new Set(Array.from((text || '').matchAll(new RegExp(tokenPattern,'g')),m=>byToken.get(m[0])))];
  }
  function unknownMember(text) {
    return /�|[小老阿](?!组|计|票|吃|数)[\u3400-\u9fff]/.test(text || '');
  }
  const personPattern='(?:'+tokenPattern+'|[小阿老][\\u3400-\\u9fff])';
  const listPattern=personPattern+'(?:\\s*(?:、|和|与|及|跟|,|\\+)\\s*'+personPattern+')+';
  const countPattern='([一二两三四五六七八九十]+|\\d+)\\s*个?人';
  function countIn(text) {
    const count=(text || '').match(new RegExp(countPattern));
    if (!count) return null;
    if (/^\d+$/.test(count[1])) return Number(count[1]);
    const chars='一二三四五六七八九', parts=count[1].replace('两','二').split('十');
    if(parts.length===1 && parts[0].length===1) return chars.indexOf(parts[0])+1;
    if(parts.length===2 && parts.every(p=>p.length<=1)) return (parts[0]?chars.indexOf(parts[0])+1:1)*10+(parts[1]?chars.indexOf(parts[1])+1:0);
    return -1;
  }
  const whole=/全组|全员|全部成员|所有人|所有成员|大家/;
  function unsafeList(text) {
    const side='[\\u3400-\\u9fffA-Za-z�]+';
    return new RegExp(tokenPattern+'\\s*(?:、|和|与|及|跟|\\+)\\s*'+side+'|'+side+'\\s*(?:、|和|与|及|跟|\\+)\\s*'+tokenPattern).test(text);
  }
  function shareClause(text, marker) {
    const clauses=text.split(/[,。;!！]/).map(s=>s.trim()), end=clauses.findIndex(s=>marker.test(s));
    if(end<0) return '';
    let start=end;
    // A comma may separate two names or two clauses. Only collect standalone names.
    while(start>0 && new RegExp('^(?:'+tokenPattern+'|[A-Za-z\\u3400-\\u9fff]{1,10})$').test(clauses[start-1])) start--;
    return clauses.slice(start,end+1).join('、');
  }
  function validEqualNames(scope) {
    const group=scope.split(/均[分摊]|平[摊分]|各一半|一起分/)[0].trim()
      .replace(new RegExp(countPattern+'\\s*$'),'').replace(/(?:一起|共同|各自|平均|两人各)?\s*$/,'').trim();
    return !group || new RegExp('^'+tokenPattern+'(?:\\s*(?:、|,|和|与|及|跟|\\+)\\s*'+tokenPattern+')*$').test(group);
  }
  function splitDetails(text, roster, byToken) {
    const ratios=text.match(/\d+(?:\.\d+)?(?:\s*:\s*\d+(?:\.\d+)?)+/g) || [];
    const ratioTag=/按份|份数|[权份]重|份额|配比/.test(text);
    const percentTag=/百分|%/.test(text);
    const exactTag=/按(?:实际)?金额|各自金额|承担\s*\d|各付各|实付分摊/.test(text);
    const unevenTag=/不[均平][摊分]|非均[分摊]|不平均|不一样|[按分]比例|三七开|四六开|多[付款承担出]|少[付款承担出]/.test(text);
    const pairs=[];
    // Match an explicit member share, keeping payer phrases like 小林付了200元 outside.
    const pairRx=new RegExp('('+personPattern+')\\s*(承担|分[摊担]|负担|应[付出]|占比?|分到|出|各付)?\\s*('+numberPattern+')\\s*(%|份|'+currencyPattern+')?', 'gi');
    for (const m of text.matchAll(pairRx)) pairs.push({name:m[1],id:byToken.get(m[1]),verb:m[2],value:m[3],unit:m[4] || '',at:m.index,end:m.index+m[0].length});
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
      const group=before?.[1] || after?.[1], ids=orderedPeople(group,byToken);
      const parts=ratios[0].split(/\s*:\s*/);
      const vectorClause=shareClause(text,/\d+(?:\s*:\s*\d+)+/);
      if (!unknownMember(vectorClause) && !unsafeList(vectorClause) && ids.length===parts.length && !pairs.length) ids.forEach((id,i)=>assign(id,parts[i]));
      else ambiguous=true;
    } else if(mode!=='equal') {
      for(const pair of pairs) assign(pair.id,pair.value);
    }
    // A named pair can be only part of the party; keep unmatched members empty.
    const declared=text.match(new RegExp('('+listPattern+')\\s*(?:两人|三人)?\\s*(?:分[摊担]|按(?:金额|百分比|份数|比例)|共同承担)'));
    if (unknownMember(declared?.[1])) ambiguous=true;
    for(const id of orderedPeople(declared?.[1],byToken)) if (!people.includes(id)) people.push(id);
    const count=countIn(text);
    if(whole.test(text) || (count===roster.length && people.length!==count)) {
      for (const m of roster) if (!people.includes(m.id)) people.push(m.id);
    }
    if(count!==null && count!==people.length && mode!=='equal') ambiguous=true;
    if (ambiguous) mode='';
    // Mask member-specific figures before looking for the overall expense. Keep offsets stable.
    const chars=text.split('');
    for (const pair of pairs) for (let i=pair.at;i<pair.end;i++) chars[i]=' ';
    let totalText=chars.join('');
    for(const ratio of ratios) totalText=totalText.replace(ratio,' ');
    if(/\d\s*(?:%|份)|(?:承担|负担|应[付出]|占比?)\s*\d/.test(totalText) ||
        (pairs.length && totalText.split(/[,、。;]/).slice(1).some(c=>new RegExp('^\\s*[\\u3400-\\u9fffA-Za-z�]+\\s*'+numberPattern+'\\s*(?:'+currencyPattern+')\\s*$','i').test(c)))) {
      mode='';ambiguous=true;
    }
    return {mode,values:ambiguous?{}:values,people,totalText};
  }
  function parse(raw, roster=members) {
    roster=roster.filter(person=>person.active!==false);
    const original=raw.normalize('NFKC').trim()
      .replace(/(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d,])/g,number=>number.replaceAll(',',''));
    const {text,byToken}=tagMembers(original,roster);
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
    const spec=splitDetails(text,roster,byToken);
    draft.split_mode=spec.mode;
    const amountRx=new RegExp('(?:AUD|CNY|RMB|USD|A\\$|US\\$|¥|￥)\\s*('+numberPattern+')|('+numberPattern+')\\s*(?:'+currencyPattern+')','gi');
    const amounts=[...spec.totalText.matchAll(amountRx)];
    if(amounts.length>1) return stop('识别到多笔总金额，请分别录入。');
    const lone=spec.totalText.match(/\d+(?:\.\d+)?/g) || [];
    const amount=amounts[0]?.[1] || amounts[0]?.[2] || (lone.length===1 ? lone[0]:null);
    if(cents(amount)) draft.amount=major(cents(amount));
    const proxy=text.match(new RegExp('('+personPattern+'|[A-Za-z]+|[\\u3400-\\u9fff]{1,4})\\s*[替帮为](?='+personPattern+'|[A-Za-z])'));
    const payers=proxy ? [byToken.get(proxy[1])] : [...new Set(Array.from(text.matchAll(new RegExp('('+tokenPattern+')\\s*(?:先|来|已)?(?:垫[付了]?|支付|付[款了]?|买单|结账|出了)','g')),m=>byToken.get(m[1])))];
    if(payers.length===1 && payers[0]!=null && !/谁付|付款人不[明详]|不知.*付/.test(text)) draft.payer=payers[0];
    if (spec.mode!=='equal') {
      draft.split_values=spec.values;
      draft.people=[...spec.people].sort((a,b)=>a-b);
    } else if(!/还没确定|未确定|未说|不清楚|还不知道/.test(text)) {
      const clause=shareClause(text,/均[分摊]|平[摊分]|各一半|一起分/);
      const match=clause.match(/(?:只给|仅给|给|仅由|由|仅|替)(.+?)(?:均[摊分]|平[摊分]|各一半)/);
      const target=match?.[1] || clause || '', count=countIn(clause);
      let ids=orderedPeople(target,byToken);
      if(!ids.length && proxy && count!==null) ids=orderedPeople(text.split(proxy[0])[1],byToken);
      if(!ids.length && /^均[摊分]$/.test(clause || '') && orderedPeople(text,byToken).length===roster.length) ids=orderedPeople(text,byToken);
      if(!unknownMember(target) && !unsafeList(target)) {
        if(whole.test(target) || !ids.length && count===roster.length && validEqualNames(target)) draft.people=roster.map(m=>m.id);
        else if((count===null || count===ids.length) && validEqualNames(target)) draft.people=ids;
      }
    }
    const uncertain=/待定|待确认|不确[定认]|未(?:定|确[定认])|还没(?:定|确[定认])|还不知道|暂缓/.test(text);
    const exception=/不参加|不参与|不算|不包括|不承担|不分摊|除[去外了]|剩余|剩下|其余/.test(text);
    const revised=/(?:另有|还有|加上|另加)|(?:[小阿老][\u3400-\u9fff]|[\uE000-\uF8FF])\s*也(?:一起|参加|参与|要分)|改[为成]|重新分摊/.test(text);
    if (uncertain || exception || revised) {
      draft.split_mode='';draft.split_values={};draft.people=[];
    }
    const description=text.match(/晚[餐饭]|午[餐饭]|早[餐饭]|打车|车费|超市|食材|咖啡|住宿|房租|门票|电影|停车|奶茶|酒店|餐费|吃饭|水电|杂货|机票|民宿|打球/);
    draft.description=description?.[0] || (draft.split_mode!=='equal' && draft.amount ? original.split(/[,。;]/)[0].slice(0,100) : '');
    const issue=problem(draft,roster);
    return {data:draft,blocked:false,note:issue || '请核对各成员的分摊金额后入账。',trace:['识别原币总金额与付款人',draft.split_mode?'提取分摊方式：'+labels[draft.split_mode]:'分摊规则待说明',issue?'等待补全或更正字段':'按最小货币单位核对分摊总额']};
  }
  const samples=[
    {id:'example-taxi',description:'机场打车',amount:'37.50',currency:'AUD',payer:12,people:[12,13],split_mode:'exact',split_values:{12:'20.00',13:'17.50'},sample:true},
    {id:'example-breakfast',description:'出发前早餐',amount:'24.00',currency:'AUD',payer:11,people:[11,12,13],sample:true}
  ];
  return {members,currencies,labels,modeOf,cents,major,problem,quote,parse,samples};
})();
if (typeof module !== 'undefined') module.exports=SplitTools;
