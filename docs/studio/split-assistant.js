'use strict';
const SplitAssistant = (() => {
  const {cents, major, moneyNumber, currencyToken, currencyCode} =
    typeof module==='undefined' ? SplitTools : require('./split-tools.js');
  const paidAmount=new RegExp('(?<![\\d.,−-])(?:(?<prefix>'+currencyToken+')\\s*(?<front>'+moneyNumber+
    ')(?![\\d.]|,\\d)|(?<back>'+moneyNumber+')\\s*(?<suffix>'+currencyToken+'))','gi');
  const currencyOnly=new RegExp('(?:'+currencyToken+')','gi');
  const discountPattern=/(?<![\d.])(\d{1,2}(?:\.\d)?)\s*折/g;
  const surchargePattern=/(?:加\s*)?(?:(\d{1,3}(?:\.\d{1,2})?)\s*%\s*(?:小费|服务费)|(?:小费|服务费)\s*(\d{1,3}(?:\.\d{1,2})?)\s*%)/g;
  const partyPattern=/(?<![\d.一二两三四五六七八九十百])([1-9]\d?|100|[一二两三四五六七八九十])\s*(?:个)?人/g;
  const headcounts={一:1,二:2,两:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9,十:10};

  function askedCurrency(question,fallback) {
    const mentioned=new Set(Array.from(question.matchAll(currencyOnly),m=>currencyCode(m[0])).filter(Boolean));
    return mentioned.size===1 ? [...mentioned][0] : mentioned.size>1 ? '' : fallback;
  }
  function exchangeTarget(question,base) {
    const direction=question.match(/(?:换(?:算)?[为成到]|折合(?:成|为)?|兑(?:成|为|换为)?|用)([^，。？?]{1,18})/);
    const directed=direction && askedCurrency(direction[1],'');
    if(directed) return directed;
    const other=new Set(Array.from(question.matchAll(currencyOnly),m=>currencyCode(m[0])).filter(code=>code && code!==base));
    return other.size===1?[...other][0]:askedCurrency(question,'');
  }
  function estimate(input) {
    const text=input.normalize('NFKC');
    if(/每人\s*(?:付|应付)?\s*[\d¥$]|另有|另加|满减|优惠券|再减|返现|退款|先加|汇率|换算|兑换|按份|按比例|不均分|不均摊/.test(text)) return null;
    const money=[...text.matchAll(paidAmount)];
    const discounts=[...text.matchAll(discountPattern)];
    const surcharges=[...text.matchAll(surchargePattern)];
    const parties=[...text.matchAll(partyPattern)];
    if(money.length!==1 || discounts.length>1 || surcharges.length>1 || parties.length>1) return null;
    if((text.includes('折') && !discounts.length) || (text.match(/%/g)||[]).length!==surcharges.length) return null;
    const match=money[0].groups;
    const currency=currencyCode(match.prefix || match.suffix);
    const original=cents((match.front||match.back).replaceAll(',',''));
    const count=parties[0]?.[1];
    const people=count ? (headcounts[count] || Number(count)) : 1;
    if(!currency || askedCurrency(text,currency)!==currency || !original ||
        (!count && /[\d一二两三四五六七八九十百]+\s*(?:个)?人|均分|平摊|均摊|人均|\bAA\b/i.test(text))) return null;
    const ratio=discounts.length?Math.round(Number(discounts[0][1])*100):1000;
    const tip=surcharges[0]?(surcharges[0][1] || surcharges[0][2]):'0';
    const tipPoints=tip==='0'?0:cents(tip)||0;
    if(ratio<0 || ratio>1000 || tipPoints>10000) return null;
    const discounted=Math.round(original*ratio/1000);
    const surcharge=Math.round(discounted*tipPoints/10000);
    const total=discounted+surcharge, lower=Math.floor(total/people);
    return {currency,original,discounted,surcharge,total,people,lower,extra:total%people};
  }
  function priceReply(price) {
    const money=value=>price.currency+' '+major(value);
    const parts=['原价 '+money(price.original)];
    if(price.original!==price.discounted) parts.push('折后 '+money(price.discounted));
    if(price.surcharge) parts.push('小费或服务费 '+money(price.surcharge)+'（按折后金额计）');
    parts.push('合计 '+money(price.total));
    if(price.people>1) {
      parts.push(price.extra
        ? price.people+' 人均分：'+price.extra+' 人付 '+money(price.lower+1)+'，其余 '+(price.people-price.extra)+' 人付 '+money(price.lower)
        : price.people+' 人均分，每人 '+money(price.lower));
    }
    return parts.join('\n');
  }
  function intent(text) {
    if(/汇率|换算|折合|兑换|换成(?:人民|澳|美|CNY|AUD|USD)|结算币种/i.test(text)) return 'exchange';
    // A question about how to share a cost is advice, even when it mentions an advance.
    if(/怎么|如何|应该|公平|合适|怎么办|可以吗/.test(text) && /垫付|代付|小费|服务费/.test(text)
        && !/谁|\d/.test(text)) return '';
    if(/(?:结算|转账给谁|谁.{0,8}(?:应收|应付|该付|该收|欠)|还给谁)/.test(text)) return 'settlement';
    if(/(?:草稿|这笔|这张小票).{0,12}(?:怎么分|预览|各付|各摊|每人多少|分摊)/.test(text)) return 'quote';
    if(/(?:打\s*[\d.]+\s*折|小费|服务费|优惠券|满减|折后|计算价格|平摊多少)/.test(text)) return 'price';
    if(/(?:垫付|付了|买单|生成草稿|记一笔|帮我记|由.+(?:均分|平摊|均摊))/.test(text)) return 'draft';
    if(estimate(text)) return 'price';
    return '';
  }
  return {estimate,priceReply,askedCurrency,exchangeTarget,intent};
})();
if(typeof module!=='undefined') module.exports=SplitAssistant;
