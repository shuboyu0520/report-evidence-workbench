'use strict';
const SplitReceipts = (() => {
  const {cents, major, moneyNumber, currencyToken, currencyCode} =
    typeof module==='undefined' ? SplitTools : require('./split-tools.js');
  const label=/^(?:grand\s+total|total\s+due|total\s+paid|amount\s+due|amount\s+paid|total|实付金额|实付|支付金额|应付金额|应付|应收金额|价税合计|合计金额|金额合计|合计|总计)(?=$|[\s:¥$\d]|AUD|USD|CNY|RMB|澳元|美元|人民币)/i;
  const totalAmount=new RegExp(
    '^(?<prefix>'+currencyToken+')?\\s*(?<amount>'+moneyNumber+')\\s*(?<suffix>'+currencyToken+')?$','i'
  );
  const joinHan=s=>s.replace(/(?<=\p{Script=Han})\s+(?=\p{Script=Han})/gu,'');
  function details(text) {
    const lines=text.normalize('NFKC').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    const labels=lines.map(joinHan);
    if(labels.slice(0,5).some(s=>/^(?:credit note\b|refund (?:receipt|invoice)\b|退款(?:单|小票|凭证)|退货(?:单|小票))/i.test(s))) {
      return {description:'',amount:'',currency:'',source:'',issue:'这张票据标注为退款，请核对支出方向。'};
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
        return {description:'小票消费',amount:'',currency:'',source:'',issue:'票面币种有冲突，请核对后手动填写。'};
      }
      totals.push({amount:major(value),currency:prefix||suffix,source:trailing?lines[i]:lines[i]+' '+lines[i+1]});
    }
    const description=labels.slice(0,6).find(s=>/^[\p{L}][\p{L}\d .·’'&()/-]{1,59}$/u.test(s)
      && !label.test(s) && !/^(?:tax|subtotal|receipt|invoice|order|date|sale\b|单号|收据|发票|小票|退款|日期)/i.test(s))
      || '小票消费';
    const values=new Set(totals.map(row=>row.amount));
    const currencies=new Set(totals.map(row=>row.currency).filter(Boolean));
    if(values.size!==1 || currencies.size>1) {
      return {description,amount:'',currency:'',source:'',issue:totals.length
        ? '识别到不同的合计或币种，请按原票填写。' : '未找到清楚的实付或合计行，请按原票填写。'};
    }
    const row=totals.find(item=>item.currency) || totals[0];
    return {...row,description,issue:row.currency?'':'请在草稿里确认币种。'};
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
  async function recognize(file, onProgress) {
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
        logger:message=>onProgress(message.status==='recognizing text'?Math.round(message.progress*100):null),
        errorHandler:fail,
      });
      worker=await Promise.race([start,failed]);
      const {data}=await Promise.race([worker.recognize(canvas),failed]);
      return data.text.trim();
    } finally {
      URL.revokeObjectURL(source);
      if(worker) await worker.terminate();
    }
  }
  return {details,recognize};
})();
if(typeof module!=='undefined') module.exports=SplitReceipts;
