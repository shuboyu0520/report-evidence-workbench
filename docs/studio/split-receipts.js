'use strict';
const SplitReceipts = (() => {
  const {cents, major, moneyNumber, currencyToken, currencyCode} =
    typeof module==='undefined' ? SplitTools : require('./split-tools.js');
  const label=/^(?:grand\s+total|total\s+due|total\s+paid|amount\s+due|amount\s+paid|total|实付金额|实付|支付金额|应付金额|应付|应收金额|价税合计|合计金额|金额合计|合计|总计)(?=$|[\s:¥$\d]|AUD|USD|CNY|RMB|澳元|美元|人民币)/i;
  const totalAmount=new RegExp(
    '^(?<prefix>'+currencyToken+')?\\s*(?<amount>'+moneyNumber+')\\s*(?<suffix>'+currencyToken+')?$','i'
  );
  const joinHan=s=>s.replace(/(?<=\p{Script=Han})\s+(?=\p{Script=Han})/gu,'');
  const nonItem=/^(?:sub[ -]?total|total\b|grand total|balance\b|amount\b|net\b|tax\b|gst\b|vat\b|incl(?:uded)?\b|service\b|surcharge\b|gratuity\b|tip\b|discount\b|savings\b|coupon\b|promotion\b|rounding\b|payment\b|paid\b|cash\b|change\b|tender\b|card\b|credit\b|debit\b|visa\b|mastercard\b|eftpos\b|order\b|receipt\b|invoice\b|table\b|staff\b|cashier\b|server\b|date\b|time\b|tel\b|abn\b|points\b|合计|小计|总计|折后|折扣|优惠|立减|满减|代金券|会员折|税|含税|未税|服务费|附加费|小费|抹零|实付|应付|应收|实收|现金|找零|支付|已付|刷卡|信用卡|银行卡|微信|支付宝|余额|积分|订单|流水|桌号|台号|单号|票号|收银|日期|时间|电话)/i;
  const priceAtEnd=new RegExp('(?<![\\d.,+\\-])(?<prefix>'+currencyToken+')?\\s*(?<number>'+moneyNumber+')\\s*(?<suffix>'+currencyToken+')?$','i');
  const quantity='[1-9]\\d{0,2}';
  const unitPrice='(?:'+currencyToken+')?\\s*('+moneyNumber+')\\s*(?:'+currencyToken+')?';
  const quantityAndPrice=new RegExp('^(.+?)\\s+('+quantity+')\\s*(?:份|杯|瓶|个|盒|pcs?)?\\s*(?:[x×*@]|\\s)\\s*'+unitPrice+'$','i');
  const priceAndQuantity=new RegExp('^(.+?)\\s+'+unitPrice+'\\s+(?:[x×*]\\s*)?('+quantity+')\\s*(?:份|杯|瓶|个|盒|pcs?)?$','i');
  const leadingQty=/^([1-9]\d{0,2})\s*(?:[x×*]\s*|\s+)(?=\p{L})/iu;
  const trailingQty=/\s+(?:[x×*]\s*)?([1-9]\d{0,2})\s*(?:份|杯|瓶|个|盒|pcs?)?\s*(?:[x×*])?$/i;
  function itemRows(lines, currency) {
    const items=[];
    const itemCurrencies=new Set();
    let layout='';
    for(const raw of lines) {
      let line=raw.replace(/[|¦]/g,' ').trim();
      const qtyHeading=/\b(?:qty|quantity)\b|数量/i.exec(line);
      if(!/\d/.test(line) && qtyHeading) {
        const unitHeading=/\bunit\s+price\b|单价/i.exec(line);
        if(/\b(?:amount|total)\b|金额|小计/i.test(line)) layout=/\bprice\b|单价/i.test(line)?'unit-and-amount':'amount';
        else if(unitHeading) layout=qtyHeading.index<unitHeading.index?'qty-unit':'unit-qty';
        else layout='unknown-price';
        continue;
      }
      if(label.test(line) && items.length) break;
      if(line.length>240 || nonItem.test(line) || label.test(line) ||
          /(?:商品|菜品|餐品|菜金|金额)(?:小计|合计)|优惠券|\b(?:terminal|merchant|register|location|shop)\s+(?:id|no\.?|number)\b|\bno\.?\s*\d+$|^(?:POS|authorization|reference|store id)\b|^(?:商户|门店|机具|终端|凭证|授权|卡号|地址|门牌)/i.test(line) ||
          /[−-]\s*(?:[$¥]|[A-Z]{3}\s*)?\d/.test(line)) continue;
      let unitCount;
      if(layout==='unit-qty') {
        const qty=trailingQty.exec(line);
        if(!qty) continue;
        unitCount=Number(qty[1]);
        line=line.slice(0,qty.index).trim();
      }
      const match=priceAtEnd.exec(line);
      if(!match || !match.index) continue;
      const before=line[match.index-1];
      const {prefix,number,suffix}=match.groups;
      const joinedChinesePrice=/\p{Script=Han}/u.test(before) && (suffix||number.includes('.'));
      if(!/^\s/.test(match[0]) && !/\s/.test(before) && !prefix && !joinedChinesePrice) continue;
      const codes=[currencyCode(prefix),currencyCode(suffix),currency].filter(Boolean);
      if(new Set(codes).size>1) continue;
      let amount=cents(number.replaceAll(',',''));
      let name=line.slice(0,match.index).trim().replace(/(?:\s*[:·]|\.{2,})$/,'').trim();
      if(!amount || !name) continue;

      const leading=leadingQty.exec(name);
      if(layout==='qty-unit' || layout==='unit-qty') {
        if(layout==='qty-unit') {
          const qty=leading || trailingQty.exec(name);
          if(!qty) continue;
          unitCount=Number(qty[1]);
          name=(leading?name.slice(qty[0].length):name.slice(0,qty.index)).trim();
        }
        amount*=unitCount;
        if(amount>9999999999) continue;
      } else if(leading && (layout || /[x×*]/i.test(leading[0]) || /\s\d+\.\d{1,2}$/.test(name))) {
        name=name.slice(leading[0].length);
        const unit=priceAtEnd.exec(name);
        if(unit) {
          if(!unit.index || Number(leading[1])*cents(unit.groups.number.replaceAll(',',''))!==amount) continue;
          name=name.slice(0,unit.index).trim();
        } else if(layout==='unit-and-amount' || (Number(leading[1])!==1 && layout!=='amount')) continue;
      } else {
        const forward=quantityAndPrice.exec(name), reverse=priceAndQuantity.exec(name);
        if(forward || reverse) {
          const [count,price]=forward?[forward[2],forward[3]]:[reverse[3],reverse[2]];
          if(Number(count)*cents(price.replaceAll(',',''))!==amount) continue;
          name=(forward||reverse)[1].trim();
        } else {
          if(layout==='unit-and-amount') continue;
          const qtyOnly=trailingQty.exec(name);
          if(qtyOnly) {
            if(Number(qtyOnly[1])!==1 && layout!=='amount') continue;
            name=name.slice(0,qtyOnly.index).trim();
          }
        }
      }
      if(!/\p{L}/u.test(name) || name.length>80 || nonItem.test(name) ||
         /(?:\d[.,]\d|\s\d+(?:\s|$)|[×*@\-]$|(?:\s|\d)x$|[$¥%])/i.test(name)) continue;
      for(const code of codes) itemCurrencies.add(code);
      items.push({description:name,amount:major(amount)});
    }
    return itemCurrencies.size>1 ? [] : items;
  }
  function details(text) {
    const lines=text.normalize('NFKC').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    const labels=lines.map(joinHan);
    if(labels.slice(0,5).some(s=>/^(?:credit note\b|refund (?:receipt|invoice)\b|退款(?:单|小票|凭证)|退货(?:单|小票))/i.test(s))) {
      return {description:'',amount:'',currency:'',source:'',items:[],issue:'这张票据标注为退款，请核对支出方向。'};
    }
    const totals=[];
    for(const [i,line] of labels.entries()) {
      if(!label.test(line)) continue;
      const trailing=line.replace(label,'').replace(/^[\s:]+/,'');
      const match=totalAmount.exec(trailing || labels[i+1] || '');
      if(!match) continue;
      const value=cents(match.groups.amount.replaceAll(',',''));
      if(!value) continue;
      const prefix=currencyCode(match.groups.prefix), suffix=currencyCode(match.groups.suffix);
      if(prefix && suffix && prefix!==suffix) {
        return {description:'小票消费',amount:'',currency:'',source:'',items:[],issue:'票面币种有冲突，请核对后手动填写。'};
      }
      totals.push({amount:major(value),currency:prefix||suffix,source:trailing?lines[i]:lines[i]+' '+lines[i+1]});
    }
    const description=labels.slice(0,6).find(s=>/^[\p{L}][\p{L}\d .·’'&()/-]{1,59}$/u.test(s)
      && !label.test(s) && !/^(?:tax|subtotal|receipt|invoice|order|date|sale\b|单号|收据|发票|小票|退款|日期)/i.test(s))
      || '小票消费';
    const values=new Set(totals.map(row=>row.amount));
    const currencies=new Set(totals.map(row=>row.currency).filter(Boolean));
    const items=currencies.size>1?[]:itemRows(labels,[...currencies][0]);
    if(values.size!==1 || currencies.size>1) {
      return {description,amount:'',currency:'',source:'',items,issue:totals.length
        ? '识别到不同的合计或币种，请按原票填写。' : '未找到清楚的实付或合计行，请按原票填写。'};
    }
    const row=totals.find(item=>item.currency) || totals[0];
    return {...row,description,items,issue:row.currency?'':'请在草稿里确认币种。'};
  }

  let loading;
  function loadEngine(base) {
    if(globalThis.Tesseract) return Promise.resolve(globalThis.Tesseract);
    if(!loading) loading=new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      script.src=new URL('tesseract.min.js',base);
      script.onload=()=>resolve(globalThis.Tesseract);
      script.onerror=()=>{script.remove();loading=null;reject(Error('识别组件未加载。'));};
      document.head.append(script);
    });
    return loading;
  }
  function thumbnail(canvas) {
    const small=document.createElement('canvas');
    for(let side=960;side>=120;side=Math.floor(side/2)) {
      const scale=Math.min(1,side/Math.max(canvas.width,canvas.height));
      small.width=Math.max(1,Math.round(canvas.width*scale));
      small.height=Math.max(1,Math.round(canvas.height*scale));
      small.getContext('2d').drawImage(canvas,0,0,small.width,small.height);
      const image=small.toDataURL('image/jpeg',0.76);
      if(image.length<=100000 && image.startsWith('data:image/jpeg;base64,')) return image;
    }
    return '';
  }
  async function recognize(file, onProgress, {withImage=false}={}) {
    if(!file.size || file.size>15*1024*1024) throw Error('请选择一张 15 MB 以内的账单。');
    const source=URL.createObjectURL(file);
    let worker;
    try {
      const image=new Image();
      image.src=source;
      try { await image.decode(); }
      catch { throw Error('图片无法读取，请换成 JPG、PNG 或 WebP。'); }
      const scale=Math.min(1,2200/Math.max(image.naturalWidth,image.naturalHeight));
      const canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));
      canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
      const ctx=canvas.getContext('2d',{alpha:false});
      ctx.fillStyle='#fff';
      ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(image,0,0,canvas.width,canvas.height);
      const base=new URL('studio/vendor/ocr/',document.baseURI);
      const engine=await loadEngine(base);
      let fail;
      const failed=new Promise((_, reject)=>{ fail=reject; });
      const start=engine.createWorker(['eng','chi_sim'],1,{
        workerPath:new URL('worker.min.js',base).href,
        corePath:new URL('tesseract-core-lstm.wasm.js',base).href,
        langPath:base.href.slice(0,-1),
        workerBlobURL:false,
        // The service worker already caches both language files for offline use.
        cacheMethod:'none',
        logger:message=>onProgress(message.status==='recognizing text'?Math.round(message.progress*100):null),
        errorHandler:fail,
      });
      worker=await Promise.race([start,failed]);
      const {data}=await Promise.race([worker.recognize(canvas),failed]);
      const text=data.text.trim();
      return withImage ? {text,image:thumbnail(canvas)} : text;
    } finally {
      URL.revokeObjectURL(source);
      if(worker) await worker.terminate();
    }
  }
  return {details,recognize};
})();
if(typeof module!=='undefined') module.exports=SplitReceipts;
