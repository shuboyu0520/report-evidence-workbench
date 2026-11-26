'use strict';
(() => {
  const {byId:$, el, api, service} = Studio;
  const {labels, modeOf, major, problem, quote, summarize, parse, samples} = SplitTools;
  let members=[], names={}, records=[], saved={version:0,draft:null};
  const draftKey = 'split-studio-draft-v1-' + (service?'api':'device');
  const fallbackExamples = {
    dinner:'晚饭共 90.00 澳元，小林垫付，小林、小周和小陈三人均摊。',
    exact:'晚餐共 96 澳元，小林垫付。小林承担 48 澳元、小周承担 30 澳元、小陈承担 18 澳元。',
    percentage:'小周付了 120 澳元晚餐，小林占 50%、小周占 30%、小陈占 20%。',
    shares:'小陈垫了 100 元买食材，小林、小周、小陈按 2:1:1 分摊。',
    no_payer:'三个人小林、小周、小陈一起吃饭，花了 66 澳元，均摊。',
    outside:'朋友小吴替小林和小周支付了 19.00 澳元车费，两人平摊。'
  };
  let draft=null, shareInputs={}, archive=[], modelName=null, ready=false, working=false, committing=false, refreshSerial=0;
  let ledgerAccessMessage='账本正在打开，请稍后再试。';
  let rateRequest=null, rateSource='manual', rateDate=null, rateMessage='';
  function id() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes=crypto.getRandomValues(new Uint8Array(16)); bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
    const s=Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');
    return [s.slice(0,8),s.slice(8,12),s.slice(12,16),s.slice(16,20),s.slice(20)].join('-');
  }
  const active=()=>members.filter(m=>m.active!==false);
  const button=(label,cls,action)=>{
    const b=el('button',label,cls);b.type='button';b.onclick=action;return b;
  };
  const historyName=m=>(names[m] || '未知成员')+(members.find(p=>p.id===m)?.active===false?'（已移出）':'');
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('split-studio-'+(service?'api':'device')) : null;
  function status(message, error=false) {
    $('split-status').classList.toggle('error',error);
    $('split-status').textContent=message;
  }
  function avatar(m) {
    const x=el('span',[...(names[m] || '？')].at(-1),'avatar');x.dataset.person=m;x.setAttribute('aria-hidden','true');return x;
  }
  async function refresh() {
    const serial=++refreshSerial;
    const [roster,own,stored]=await Promise.all(service?[api('members'),api('entries'),api('draft')]:
      [SplitDevice.list('members'),SplitDevice.list('entries'),SplitDevice.getDraft()]);
    if(serial!==refreshSerial)return;
    const changed=JSON.stringify(members)!==JSON.stringify(roster);
    members=roster;names=Object.fromEntries(members.map(m=>[m.id,m.name]));saved=stored;
    own.sort((a,b)=>String(b.created).localeCompare(String(a.created)));
    records=own;
    const rosterNow=active();
    $('crew-faces').replaceChildren(...rosterNow.slice(0,3).map(m=>el('i',[...m.name].at(-1))));
    $('crew-names').textContent=rosterNow.length ? rosterNow.slice(0,3).map(m=>m.name).join('、')+(rosterNow.length>3?' 等 '+rosterNow.length+' 人':''):'尚未添加成员';
    $('member-count').textContent=rosterNow.length+' 人';
    $('empty-roster').hidden=Boolean(rosterNow.length);
    for(const chip of document.querySelectorAll('[data-example]'))chip.disabled=!rosterNow.length;
    if(changed && $('member-dialog').open) renderRoster();
    if(changed && draft) {
      renderPeople(draft.data);renderValueFields(draft.data);renderItems(readItems());updatePreview();
    }
    showSaved();
    renderLedger();
  }
  function renderLedger() {
    const currency=$('currency-view').value, all=$('show-samples').checked?[...records,...samples]:records;
    const {entries,balances,transfers,total}=summarize(all,members,currency);
    const expanded=new Set([...$('ledger').querySelectorAll('details[open]')].map(row=>row.dataset.id));
    $('ledger').replaceChildren();
    for (const {entry:r,allocation:q} of entries) {
      const entry=el('details',null,'ledger-entry'), line=el('summary',null,'ledger-row'), copy=el('div',null,'row-copy');
      entry.dataset.id=r.id;entry.open=expanded.has(r.id);
      copy.append(el('strong',r.description),el('small',historyName(r.payer)+'垫付 · '+labels[modeOf(r)]+' · '+r.people.length+'人'+(r.sample?' · 示例':'')));
      line.append(avatar(r.payer),copy,el('span',major(q.cents),'amt'));
      const detail=el('div',null,'entry-allocations');
      if(r.fx) detail.append(el('p','票面 '+r.currency+' '+r.amount+' · '+exchangeLabel(r),'bill-exchange'));
      if(r.receipt) detail.append(receiptEvidence(r.receipt));
      if(modeOf(r)==='items') {
        const lines=el('ul',null,'entry-items');
        for(const item of r.items) {
          const line=el('li');
          line.append(el('strong',item.description),el('span',r.currency+' '+item.amount),
            el('small',item.people.map(historyName).join('、')));
          lines.append(line);
        }
        detail.append(lines);
      }
      for (const share of q.shares) detail.append(shareLine(share,r,r.fx?.currency||r.currency));
      if(modeOf(r)==='items') {
        const transfers=el('div',null,'entry-transfers');
        renderBillTransfers(transfers,q,r);detail.append(transfers);
      }
      const action=button(r.sample?'以此新建':'编辑账单',r.sample?'copy-example':'edit-entry',()=>openEntry(r));
      detail.append(action);
      entry.append(line,detail);$('ledger').append(entry);
    }
    if (!entries.length) $('ledger').append(el('p','这个币种还没有账单。','hint'));
    $('total').replaceChildren(el('i',currency+' '),document.createTextNode(major(total)));
    const sampleCount=entries.filter(({entry})=>entry.sample).length;
    $('entry-count').textContent=entries.length+' 笔支出'+(sampleCount?' · 含 '+sampleCount+' 笔示例':'');
    $('ledger-unit').textContent=currency;
    $('balances').replaceChildren();
    const absMax=Math.max(1,...Object.values(balances).map(Math.abs));
    for (const m of members.filter(m=>m.active!==false || balances[m.id])) {
      const v=balances[m.id], row=el('div',null,'balance-row'), copy=el('div',null,'row-copy'), bar=el('div',null,'bar'), fill=el('span');
      fill.style.width=(Math.abs(v)/absMax*100)+'%';bar.append(fill);
      copy.append(el('strong',historyName(m.id)),bar);
      row.append(avatar(m.id),copy,el('span',v===0?'已结清':(v>0?'应收 ':'应付 ')+major(Math.abs(v)),v>0?'credit':'debit'));
      $('balances').append(row);
    }
    const lines=transfers.length?transfers.map(t=>transferLine(t,currency)):['当前币种已结清。'];
    $('settlement').replaceChildren(...lines.map(t=>el('span',t,'transfer')));
  }
  function transferLine(transfer,currency) {
    return historyName(transfer.from)+' → '+historyName(transfer.to)+' '+currency+' '+major(transfer.cents);
  }
  function readForm() {
    const items=$('split-mode').value==='items'?readItems():null;
    const people=items?[...new Set(items.flatMap(item=>item.people))].sort((a,b)=>a-b):
      [...document.querySelectorAll('#participants input:checked')].map(box=>Number(box.value));
    const values=Object.fromEntries([...$('split-values').querySelectorAll('input[data-person]')]
      .filter(input=>people.includes(Number(input.dataset.person)))
      .map(input=>[input.dataset.person,input.value.trim()]));
    const data={description:$('description').value.trim(),amount:$('amount').value.trim(),currency:$('currency').value,
      payer:Number($('payer').value)||null,people,split_mode:$('split-mode').value,split_values:values};
    if(items) {data.items=items;data.split_values={};}
    if(draft?.data.receipt) data.receipt=draft.data.receipt;
    if($('fx-currency').value) data.fx={currency:$('fx-currency').value,rate:$('fx-rate').value.trim(),source:rateSource,date:rateDate};
    return data;
  }
  function exchangeLabel(d) {
    return '1 '+d.currency+' = '+d.fx.rate+' '+d.fx.currency+'（'+(d.fx.source==='frankfurter'?'Frankfurter 参考汇率 · '+d.fx.date:'约定汇率')+'）';
  }
  function receiptEvidence(receipt) {
    const details=el('details',null,'bill-evidence');
    details.append(el('summary','查看小票'+(receipt.amount?' · '+[receipt.currency,receipt.amount].filter(Boolean).join(' '):'')));
    if(receipt.source) details.append(el('p',receipt.source));
    if(receipt.image?.startsWith('data:image/jpeg;base64,')) {
      const img=el('img');img.src=receipt.image;img.alt='本账单的小票缩略图';img.loading='lazy';details.append(img);
    }
    return details;
  }
  function resetExchange(base,fx) {
    rateRequest?.abort();rateRequest=null;rateMessage='';
    rateSource=fx?.source||'manual';rateDate=fx?.date||null;
    const select=$('fx-currency');
    for(const option of select.options) option.disabled=Boolean(option.value && option.value===base);
    select.disabled=!base;select.value=fx?.currency && fx.currency!==base ? fx.currency : '';
    $('fx-rate').value=select.value ? fx.rate : '';
    $('fetch-fx').disabled=false;
  }
  function refreshExchange(d) {
    $('fx-fields').hidden=!d.fx;
    if(!d.fx) return;
    $('fx-label').textContent='1 '+d.currency+' 等于多少 '+d.fx.currency+'？';
    const converted=SplitTools.convertedCents(d.amount,d.fx.rate);
    const source=rateSource==='frankfurter'?'Frankfurter · '+rateDate:'约定汇率';
    const total=converted===null?'':source+' · 换算合计 '+d.fx.currency+' '+major(converted);
    $('fx-note').textContent=[rateMessage,total].filter(Boolean).join('　') || '可填银行卡实际汇率，或联网取参考汇率。';
  }
  $('fetch-fx').onclick=async()=>{
    if(!draft||committing) return;
    const base=$('currency').value,target=$('fx-currency').value;
    if(!base||!target||base===target) return;
    rateRequest?.abort();
    const request=new AbortController();rateRequest=request;
    const timeout=setTimeout(()=>request.abort(),10000);
    $('fetch-fx').disabled=true;rateMessage='正在获取参考汇率…';updatePreview();
    try {
      const response=await fetch('https://api.frankfurter.dev/v2/rate/'+base+'/'+target,{signal:request.signal,credentials:'omit',referrerPolicy:'no-referrer'});
      if(!response.ok) throw Error();
      const value=await response.json(), rate=String(value.rate);
      if(value.base!==base||value.quote!==target||!/^\d{4}-\d{2}-\d{2}$/.test(value.date)||
          !/^\d{1,6}(?:\.\d{1,8})?$/.test(rate)||Number(rate)<=0) throw Error();
      if(request!==rateRequest) return;
      $('fx-rate').value=rate;rateSource='frankfurter';rateDate=value.date;rateMessage='';draft.dirty=true;
    } catch {
      if(request===rateRequest) rateMessage='暂时取不到参考汇率，可填写实际汇率。';
    } finally {
      clearTimeout(timeout);
      if(request===rateRequest) {rateRequest=null;$('fetch-fx').disabled=false;updatePreview();}
    }
  };
  function shareLine(share,d,unit=d.currency) {
    const row=el('div',null,'quote-line'), mode=modeOf(d), value=d.split_values?.[share.id];
    const suffix=mode==='ratio'?' · '+value+' 份':mode==='percentage'?' · '+value+'%':'';
    row.append(el('span',historyName(share.id)+suffix),el('strong',unit+' '+major(share.cents)));
    return row;
  }
  function renderBillTransfers(container,allocation,data) {
    const unit=data.fx?.currency||data.currency;
    const payments=SplitTools.billTransfers(allocation,data.payer);
    container.replaceChildren(el('h4','本单应付给垫付人'),
      ...(payments.length?payments.map(t=>el('p',transferLine(t,unit))):[el('p','本单无需相互付款。')]));
  }
  function readItems() {
    return [...$('item-rows').children].map(row=>({
      description:row.querySelector('.item-description').value.trim(),amount:row.querySelector('.item-amount').value.trim(),
      people:[...row.querySelectorAll('input:checked')].map(box=>Number(box.value))
    }));
  }
  function itemRow(item) {
    const row=el('div',null,'item-row'), fields=el('div',null,'item-fields');
    const description=el('input',null,'item-description'), amount=el('input',null,'item-amount');
    description.value=item.description||'';description.maxLength=100;description.placeholder='菜品或费用名称';
    amount.value=item.amount||'';amount.type='text';amount.inputMode='text';amount.maxLength=13;amount.placeholder='0.00';
    const nameLabel=el('label','名称','field'), amountLabel=el('label','该项总价','field');
    nameLabel.append(description);amountLabel.append(amount);
    fields.append(nameLabel,amountLabel,button('移除','remove-item',()=>{
      row.remove();draft.dirty=true;updatePreview();
    }));
    const checks=el('fieldset',null,'checks item-people');checks.append(el('legend','谁分这项'));
    for(const member of members) {
      if(member.active===false && !item.people.includes(member.id) && !draft.original?.people.includes(member.id)) continue;
      const label=el('label'),box=el('input');
      box.type='checkbox';box.value=member.id;box.checked=item.people.includes(member.id);
      label.append(box,document.createTextNode(historyName(member.id)));checks.append(label);
    }
    if(active().length>1) checks.append(button('选全组','choose-all item-all',()=>{
      const current=new Set(active().map(m=>m.id));
      for(const box of checks.querySelectorAll('input')) if(current.has(Number(box.value)))box.checked=true;
      checks.dispatchEvent(new Event('input',{bubbles:true}));
    }));
    row.append(fields,checks);return row;
  }
  function renderItems(items) {
    $('item-rows').replaceChildren(...items.map(itemRow));
  }
  $('add-item').onclick=()=>{
    if($('item-rows').childElementCount>=200)return;
    const row=itemRow({description:'',amount:'',people:[]});
    $('item-rows').append(row);draft.dirty=true;updatePreview();row.querySelector('.item-description').focus();
  };
  function itemReconciliation(d) {
    const amounts=d.items.map(item=>SplitTools.lineCents(item.amount));
    if(amounts.includes(null)) return '请核对每一项的票面总价。';
    const sum=amounts.reduce((a,b)=>a+b,0), total=SplitTools.cents(d.amount);
    const summary='明细合计 '+d.currency+' '+major(sum);
    if(!total) return summary+' · 请填写实付总额';
    const difference=total-sum;
    if(!difference) return summary+' · 与实付总额一致';
    return summary+' · '+(difference>0?'还差 ':'超出 ')+major(Math.abs(difference))+'。请对照原票补录或调整明细。';
  }
  function renderValueFields(d) {
    const box=$('split-values'), mode=modeOf(d);
    box.replaceChildren();box.hidden=!d.people.length || !['percentage','exact','ratio'].includes(mode);
    if(box.hidden) return;
    const unit={exact:d.currency || '金额',percentage:'%',ratio:'份'}[mode];
    for(const person of d.people) {
      const row=el('label',null,'split-value-row'), name=el('span',names[person],'name'), input=el('input');
      input.dataset.person=String(person);
      input.type='text';input.inputMode=mode==='ratio'?'numeric':'decimal';input.autocomplete='off';
      input.placeholder=mode==='exact'?'0.00':'—';
      input.setAttribute('aria-label',names[person]+({exact:'分摊金额',percentage:'的百分比',ratio:'的份数'}[mode]));
      input.value=d.split_values?.[person] ?? '';
      row.append(name,input,el('span',unit,'value-unit'));box.append(row);
    }
  }
  function renderPeople(d) {
    const payer=$('payer'), checks=$('participants'), original=draft?.original;
    payer.replaceChildren(new Option('选择付款人',''));checks.replaceChildren(el('legend','参与分摊的成员'));
    for (const m of members) {
      if (m.active!==false || m.id===original?.payer || m.id===d.payer) payer.add(new Option(historyName(m.id),m.id));
      if (m.active===false && !original?.people.includes(m.id) && !d.people.includes(m.id)) continue;
      const label=el('label'), box=el('input');
      box.type='checkbox';box.value=m.id;box.checked=d.people.includes(m.id);
      label.append(box,document.createTextNode(historyName(m.id)));checks.append(label);
    }
    const activeIds=new Set(active().map(m=>m.id));
    if(activeIds.size>1) checks.append(button('选全组','choose-all',()=>{
      for(const box of checks.querySelectorAll('input[type=checkbox]')) {
        if(activeIds.has(Number(box.value))) box.checked=true;
      }
      checks.dispatchEvent(new Event('input',{bubbles:true}));
    }));
    payer.value=d.payer || '';
  }
  function remember() {
    if(service)return;
    try {if(draft)sessionStorage.setItem(draftKey,JSON.stringify(draft));else sessionStorage.removeItem(draftKey);}catch{}
  }
  function updatePreview(event) {
    if (!draft) return;
    const changed=event?.target.id;
    if(changed==='currency') resetExchange($('currency').value);
    if(changed==='fx-currency') resetExchange($('currency').value,{currency:$('fx-currency').value,rate:''});
    if(changed==='fx-rate'){
      rateRequest?.abort();rateRequest=null;$('fetch-fx').disabled=false;
      rateMessage='';rateSource='manual';rateDate=null;
    }
    let d=readForm();
    const changedMode=event?.target.id==='split-mode';
    if(changedMode && draft.data.split_mode==='items') {
      draft.parkedItems=readItems();
      delete draft.parkedFromScan;
      renderPeople({...d,people:draft.data.people});
      d=readForm();
    }
    if(changedMode && d.split_mode==='items' && !$('item-rows').childElementCount) {
      renderItems([{description:'',amount:'',people:[]}]);d=readForm();
    }
    if(changedMode) shareInputs={};
    else Object.assign(shareInputs,d.split_values);
    if(changedMode || ['currency','participants'].includes(event?.target.id) || event?.target.type==='checkbox') {
      renderValueFields({...d,split_values:shareInputs});d=readForm();
    }
    if(d.split_mode==='items'){delete draft.parkedItems;delete draft.parkedFromScan;}
    draft.data=d;if(event)draft.dirty=true;remember();refreshExchange(d);
    const itemized=d.split_mode==='items';
    $('participants').hidden=itemized;$('item-editor').hidden=!itemized;
    if(itemized) {
      $('item-reconciliation').textContent=itemReconciliation(d);
      $('add-item').disabled=d.items.length>=200;
    }
    const corrected=d.receipt?.amount && (SplitTools.cents(d.amount)!==SplitTools.cents(d.receipt.amount)||
      d.receipt.currency && d.currency!==d.receipt.currency);
    $('receipt-difference').hidden=!corrected;
    if(corrected) $('receipt-difference').textContent='小票识别为 '+[d.receipt.currency,d.receipt.amount].filter(Boolean).join(' ')+'。请核对手动填写的票面金额和币种。';
    $('participants').querySelector('legend').textContent='参与分摊的成员 · 已选 '+d.people.length+' 人';
    const issue=SplitDevice.eligibility(d,members,draft.original) || (itemized && d.payer && !d.people.length?
      '请在各项明细下面勾选参与分摊的人。':problem(d,members));
    const q=issue?null:quote(d,members);
    const settlement=q?.settlement||q, unit=d.fx?.currency||d.currency;
    $('split-feedback').textContent=issue || '各成员分摊合计 '+unit+' '+major(settlement.cents);
    $('split-feedback').classList.toggle('invalid',Boolean(issue));
    $('allocation').replaceChildren();$('confirm').disabled=!ready||committing||Boolean(rateRequest)||!q;
    $('save-draft').disabled=committing||Boolean(rateRequest);
    $('draft-state').textContent=q?(draft.entryVersion?'编辑中':'待确认'):'待补充';
    if (settlement) for(const s of settlement.shares) $('allocation').append(shareLine(s,d,unit));
    $('bill-transfers').hidden=!itemized||!q;
    if(itemized&&q)renderBillTransfers($('bill-transfers'),q,d);
  }
  function showDraft(item) {
    draft=item;const d=item.data;
    shareInputs={...d.split_values};
    draft.baseDraftVersion ??= saved.version;
    $('review-title').textContent=item.entryVersion?'编辑已入账费用':'核对分账草稿';
    $('confirm').textContent=item.entryVersion?'保存修改':'确认入账';
    $('expense-text').value=item.text;$('description').value=d.description||'';$('amount').value=d.amount||'';$('currency').value=d.currency||'';
    resetExchange(d.currency,d.fx);
    $('draft-evidence').replaceChildren(...(d.receipt?[receiptEvidence(d.receipt)]:[]));
    $('draft-receipt').textContent=d.receipt?'更换小票':'拍照或选图';
    renderPeople(d);$('split-mode').value=modeOf(d);renderItems(d.items||item.parkedItems||[]);
    renderValueFields(d);
    $('draft-hint').textContent=item.note;$('draft-trace').replaceChildren(...item.trace.map(s=>el('li',s)));
    $('draft').hidden=false;updatePreview();
  }
  function clearDraft() {rateRequest?.abort();rateRequest=null;draft=null;remember();$('draft').hidden=true;}
  function mayReplace() {
    return !committing && !working && (!draft?.dirty || window.confirm('放弃当前表单里尚未保存的修改？'));
  }
  function openEntry(r) {
    if(!mayReplace())return;
    const {description,amount,currency,payer,people,split_values}=r;
    const data={description,amount,currency,payer,people:[...people],split_mode:modeOf(r),split_values:{...split_values},
      ...(r.items?{items:structuredClone(r.items)}:{}),
      ...(r.fx?{fx:{...r.fx}}:{}),...(r.receipt?{receipt:{...r.receipt}}:{})};
    const meta=r.sample?{}:{entryVersion:r.version||1,original:{payer,people:[...people]}};
    showDraft({id:r.sample?id():r.id,text:'',data,...meta,
      note:r.sample?'已复制示例，可修改后作为新费用入账。':'可修改付款人、分摊成员和金额，保存后会重新计算余额。',
      trace:[r.sample?'从示例复制费用字段':'读取原账单和分摊明细','按币种重新计算每人份额']});
    $('description').focus();
  }
  function showSaved() {
    $('saved-strip').hidden=!saved.draft;
    if(saved.draft)$('saved-title').textContent=saved.draft.data?.description || saved.draft.text || '未命名费用';
  }
  function persistDraft(version,item) {
    if(!service)return SplitDevice.writeDraft(version,item);
    return item?api('draft',{version,draft:item},'PUT'):api('draft?version='+version,null,'DELETE');
  }
  async function saveWorkingDraft() {
    if(!draft||committing||working||rateRequest)return;
    if(saved.draft && saved.draft.id!==draft.id && !window.confirm('用当前草稿替换之前保存的草稿？'))return;
    committing=true;$('draft').inert=true;$('save-draft').disabled=true;$('confirm').disabled=true;
    try {
      const item={...draft,dirty:false};
      delete item.baseDraftVersion;
      saved=await persistDraft(draft.baseDraftVersion,item);
      draft.baseDraftVersion=saved.version;draft.dirty=false;remember();showSaved();
      channel?.postMessage('refresh');status('草稿已保存，稍后可以继续编辑。');
    } catch(err){status(err.message,true);await refresh();}
    finally {committing=false;$('draft').inert=false;$('save-draft').disabled=false;updatePreview();}
  }
  $('save-draft').onclick=saveWorkingDraft;
  $('restore-draft').onclick=()=>{
    if(saved.draft && mayReplace()){showDraft({...structuredClone(saved.draft),baseDraftVersion:saved.version});$('description').focus();}
  };
  $('delete-draft').onclick=async()=>{
    if(!saved.draft||committing||!window.confirm('删除已保存的这份草稿？'))return;
    committing=true;
    try {
      const old=saved.draft;saved=await persistDraft(saved.version,null);
      if(draft?.id===old.id){draft.baseDraftVersion=saved.version;remember();}
      showSaved();channel?.postMessage('refresh');status('已删除保存的草稿。');
    } catch(err){status(err.message,true);await refresh();}
    finally {committing=false;updatePreview();}
  };
  function recorded(text) {
    const c=archive.find(row=>row.text===text);
    if (!c || active().length!==3 || !SplitTools.members.every(m=>active().some(a=>a.id===m.id && a.name===m.name))) return null;
    const a=c.replay;
    const d={description:a.description||'',amount:a.amount||'',currency:a.currency||'',payer:a.payer_user_id,people:a.participant_ids||[]};
    const blocked=!a.description&&!a.amount&&!a.currency;
    return {data:d,blocked,note:blocked?'该样例需要补充，请核对原始账单。':'这是 Qwen 对此固定样例的存档输出，请核对后入账。',trace:['匹配固定评测输入','读取 Qwen 复测字段','根据成员与金额校验草稿']};
  }
  async function prepareDraft(text, {useArchive=false}={}) {
    const result=parse(text,active());
    if(result.blocked) return result;
    if(service) return api('drafts/parse',{text,proposal:result.data});
    if(useArchive && result.data.split_mode==='equal') return recorded(text)||result;
    return result;
  }
  async function createDraft(e) {
    e.preventDefault();if(!mayReplace())return;
    const text=$('expense-text').value.trim();if(text.length<2){status('请先输入一笔费用。',true);return;}
    working=true;$('draft').inert=true;$('parse').disabled=true;status('');
    try {
      const result=await prepareDraft(text,{useArchive:true});
      if(result.blocked){status(result.note);return;}
      showDraft({id:id(),text,...result});
      $('draft').tabIndex=-1;$('draft').focus({preventScroll:true});$('draft').scrollIntoView({block:'nearest'});
    } catch(err) {
      status(err.message,true);
      const manual=parse(text,active());
      if (!manual.blocked) showDraft({id:id(),text,...manual,note:'模型未完成提取。请手动核对以下本地预填字段。'});
    } finally {working=false;$('draft').inert=false;$('parse').disabled=!ready;}
  }
  $('compose').addEventListener('submit',createDraft);
  $('manual').addEventListener('click',()=>{
    if(!ready || !mayReplace()) return;
    status('');
    showDraft({id:id(),text:'',data:{description:'',amount:'',currency:$('currency-view').value,
      payer:null,people:[],split_mode:'',split_values:{}},note:'填写支出并选择分摊方式。',trace:['手动录入','确认前逐人核对金额']});
    $('description').focus();
  });
  $('draft').addEventListener('input',updatePreview);
  $('discard').onclick=()=>{if(!committing&&!working){clearDraft();status('已取消本次编辑。');}};
  $('draft').addEventListener('submit',async e=>{
    e.preventDefault();if(!draft||!ready||committing||rateRequest)return;
    const d=readForm(), q=quote(d,members);if(!q||SplitDevice.eligibility(d,members,draft.original))return;
    d.amount=major(q.cents);const item=draft;
    committing=true;$('draft').inert=true;$('confirm').disabled=true;$('parse').disabled=true;$('discard').disabled=true;
    try {
      if(service && item.entryVersion) await api('entries/'+item.id,{version:item.entryVersion,data:d},'PUT');
      else if(service) await api('entries',{id:item.id,data:d});
      else await SplitDevice.saveEntry(item.id,d,item.entryVersion);
      let cleanup='';
      if(saved.draft?.id===item.id && saved.version===item.baseDraftVersion) {
        try {saved=await persistDraft(item.baseDraftVersion,null);}
        catch {cleanup=' 已保存的草稿仍在，请检查后清理。';}
      }
      clearDraft();$('expense-text').value='';$('currency-view').value=d.fx?.currency||d.currency;
      const converted=q.settlement?'，结算 '+q.settlement.currency+' '+major(q.settlement.cents):'';
      await refresh();channel?.postMessage('refresh');status((item.entryVersion?'已更新账单：':'已入账：')+d.description+'，'+d.currency+' '+d.amount+converted+'。'+cleanup);
    } catch(err){status(err.message,true);await refresh();} finally {committing=false;$('draft').inert=false;$('discard').disabled=false;$('parse').disabled=!ready;updatePreview();}
  });
  function applyDraft(dialog,result,text='') {
    if(!ready || !mayReplace()) return false;
    dialog.close();
    showDraft({id:id(),text,...result,dirty:true});
    $('description').focus({preventScroll:true});
    $('draft').scrollIntoView({block:'nearest'});
    return true;
  }

  const receiptDialog=$('receipt-dialog');
  let readingReceipt=false, receiptImageURL='', receiptThumbnail='', scanVersion=0;
  function openReceipt() {
    const old=draft?.data.receipt, preview=$('receipt-preview');
    if(receiptImageURL) URL.revokeObjectURL(receiptImageURL);
    receiptImageURL='';receiptThumbnail=old?.image||'';readingReceipt=false;scanVersion++;
    if(receiptThumbnail) preview.src=receiptThumbnail; else preview.removeAttribute('src');
    preview.hidden=!receiptThumbnail;
    $('receipt-text').readOnly=false;$('receipt-text').value=old?.source||'';
    $('use-receipt-items').checked=!(draft?.entryVersion||draft?.data.items?.length||draft?.data.people?.length||
      (draft?.parkedItems?.length&&!draft.parkedFromScan)||
      ['exact','ratio','percentage'].includes(draft?.data.split_mode));
    $('receipt-status').textContent='';$('receipt-status').classList.remove('error');
    $('take-photo').disabled=false;$('choose-image').disabled=false;
    $('receipt-to-draft').textContent=draft?'应用到当前账单':'填入分账草稿';
    previewReceipt();receiptDialog.showModal();
  }
  $('open-receipt').onclick=$('draft-receipt').onclick=openReceipt;
  $('close-receipt').onclick=()=>receiptDialog.close();
  $('take-photo').onclick=()=>$('receipt-camera').click();
  $('choose-image').onclick=()=>$('receipt-image').click();
  function previewReceipt() {
    const text=$('receipt-text').value.trim();
    const info=SplitReceipts.details(text);
    $('receipt-evidence').hidden=!info.source;
    $('receipt-source').textContent=info.source;
    $('receipt-amount').textContent=info.amount ? [info.currency,info.amount].filter(Boolean).join(' ') : '';
    const items=info.items||[];
    $('receipt-items').hidden=!items.length;
    $('receipt-no-items').hidden=Boolean(items.length || readingReceipt || (!text && !receiptThumbnail));
    $('receipt-manual-items').disabled=!ready||readingReceipt;
    $('receipt-item-list').replaceChildren(...items.map(item=>{
      const row=el('li');row.append(el('span',item.description),el('strong',item.amount));return row;
    }));
    const existingItems=draft?.data.items?.length || (draft?.parkedItems?.length && !draft.parkedFromScan);
    $('receipt-item-notice').textContent=existingItems?
      '勾选后将用这份识别结果替换现有明细，并重新选择每项参与人。':'可稍后在本单切换为「按小票明细」，再核对价格和参与人。';
    $('receipt-issue').textContent=text ? [info.issue,ready?'':ledgerAccessMessage].filter(Boolean).join(' ') : '';
    $('receipt-to-draft').disabled=!ready||readingReceipt||(!text&&!receiptThumbnail);
    return info;
  }
  $('receipt-text').addEventListener('input',previewReceipt);
  async function readReceipt(event) {
    const file=event.target.files[0];
    event.target.value='';
    if(!file || readingReceipt) return;
    const version=++scanVersion;
    readingReceipt=true;
    for(const id of ['take-photo','choose-image','receipt-to-draft']) $(id).disabled=true;
    $('receipt-text').readOnly=true;
    const statusEl=$('receipt-status'), image=$('receipt-preview');
    if(receiptImageURL) URL.revokeObjectURL(receiptImageURL);
    receiptImageURL=URL.createObjectURL(file);image.src=receiptImageURL;image.hidden=false;
    receiptThumbnail='';$('receipt-text').value='';previewReceipt();
    statusEl.textContent='正在加载识别组件…';
    statusEl.classList.remove('error');
    try {
      const {text,image:thumbnail}=await SplitReceipts.recognize(file,percent=>{
        if(version===scanVersion) statusEl.textContent=percent===null?'正在准备识别…':'正在识别文字 · '+percent+'%';
      },{withImage:true});
      if(version!==scanVersion) return;
      receiptThumbnail=thumbnail;
      $('receipt-text').value=text;
      statusEl.textContent=text?'识别完成，请与照片核对。':'没读到文字。可以重新拍照，或直接粘贴票面文字。';
    } catch(err) {
      if(version!==scanVersion) return;
      statusEl.textContent=(err.message||'图片识别出错。')+' 也可以粘贴票面文字。';
      statusEl.classList.add('error');
    } finally {
      if(version===scanVersion) {
        readingReceipt=false;
        for(const id of ['take-photo','choose-image']) $(id).disabled=false;
        $('receipt-text').readOnly=false;previewReceipt();
      }
    }
  }
  $('receipt-image').onchange=readReceipt;
  $('receipt-camera').onchange=readReceipt;
  function importReceipt(manualItems) {
    if(!ready||committing||working||readingReceipt)return;
    const info=previewReceipt();
    const data=draft?readForm():{payer:null,people:[],split_mode:'equal',split_values:{}};
    if(data.currency!==info.currency) delete data.fx;
    data.description=data.description||info.description;
    data.amount=info.amount;data.currency=info.currency;
    data.receipt={source:info.source.slice(0,300),amount:info.amount,currency:info.currency,image:receiptThumbnail};
    const detected=(info.items||[]).map(({description,amount})=>({description,amount,people:[]}));
    const useDetected=detected.length && $('use-receipt-items').checked;
    if(useDetected || manualItems) {
      data.items=useDetected?detected:data.items||(!draft?.parkedFromScan && draft?.parkedItems)||[];
      if(!data.items.length)data.items=[{description:'',amount:'',people:[]}];
      data.people=[...new Set(data.items.flatMap(line=>line.people))];
      data.split_mode='items';data.split_values={};
    }
    const item={...(draft||{id:id(),text:''}),data,dirty:true,
      note:info.issue||(data.split_mode==='items'?'核对明细价格，并在每一项下面勾选实际参与人。':'核对票面合计、付款人与分摊名单后确认。'),
      trace:[info.source?'识别到原票行 '+data.receipt.source:'票面金额等待人工核对','按本单选定的成员和结算币种分摊']};
    if(data.split_mode!=='items' && (!item.parkedItems?.length || item.parkedFromScan)) {
      if(detected.length){item.parkedItems=detected;item.parkedFromScan=true;}
      else {delete item.parkedItems;delete item.parkedFromScan;}
    }
    receiptDialog.close();showDraft(item);$('draft').scrollIntoView({block:'nearest'});
  }
  $('receipt-to-draft').onclick=()=>importReceipt(false);
  $('receipt-manual-items').onclick=()=>importReceipt(true);

  const assistantDialog=$('assistant-dialog');
  let assisting=false, languageWorker=null, pendingField=null;
  function releaseLanguageModel() {
    languageWorker?.terminate();
    languageWorker=null;
  }
  assistantDialog.addEventListener('close',()=>{if(!assisting) releaseLanguageModel();});
  async function devicePlan(question) {
    const progress=$('assistant-progress');
    progress.textContent=languageWorker?'正在理解你的问题…':'正在打开设备端中文模型，首次使用需下载约 35 MB…';
    try {
      languageWorker ||= new Worker(new URL('studio/split-language-worker.mjs',document.baseURI), {type:'module'});
      const worker=languageWorker;
      const plan=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('模型加载超时')),120000);
        worker.onmessage=({data})=>{
          clearTimeout(timer);
          if(data.plan) resolve(data.plan); else reject(Error(data.error));
        };
        worker.onerror=()=>{clearTimeout(timer);reject(Error('模型无法载入'));};
        worker.postMessage(question);
      });
      return {...plan,engine:'bge'};
    } catch {
      releaseLanguageModel();
      return {tool:'guide',message:'中文模型暂时无法加载。联网后可以再问一次，也可以点「看结算」「看草稿」或「试算价格」继续。'};
    } finally { progress.textContent=''; }
  }
  function openAssistant() {
    const context=$('assistant-context');
    context.hidden=!draft;
    if(draft) {
      const d=draft.data;
      context.textContent=['当前账单',d.description,[d.currency,d.amount].filter(Boolean).join(' '),
        d.payer?historyName(d.payer)+'垫付':'待选付款人','已选 '+d.people.length+' 人分摊'].filter(Boolean).join(' · ');
    }
    if(!assistantDialog.open) assistantDialog.showModal();
  }
  $('open-assistant').onclick=$('draft-assistant').onclick=openAssistant;
  $('assistant-tab').onclick=openAssistant;
  $('close-assistant').onclick=()=>assistantDialog.close();
  for(const button of assistantDialog.querySelectorAll('[data-assistant]')) {
    button.onclick=()=>{
      $('assistant-question').value=button.dataset.assistant;
      $('assistant-form').requestSubmit();
    };
  }
  function assistantMessage(text, kind, heading) {
    const log=$('assistant-log'), row=el('div',null,'assistant-message '+kind);
    if(heading) row.append(el('small',heading));
    row.append(el('div',text));
    log.append(row);
    if(log.children.length>20) log.firstElementChild.remove();
    log.scrollTop=log.scrollHeight;
    return row;
  }
  function billChange(fields,heading) {
    const key=draft.id, current=draft.data, changes={};
    const summary=[];
    if(fields.payer) {changes.payer=fields.payer;summary.push('付款人 '+historyName(fields.payer));}
    if(current.split_mode!=='items' && fields.people?.length && fields.split_mode!==undefined) {
      Object.assign(changes,{people:fields.people,split_mode:fields.split_mode,split_values:fields.split_values||{}});
      summary.push('分摊成员 '+fields.people.map(historyName).join('、')+' · '+(labels[fields.split_mode]||'待选分摊方式'));
    }
    if(fields.amount) {
      changes.amount=fields.amount;changes.currency=fields.currency||current.currency;
      summary.push('票面金额 '+changes.currency+' '+changes.amount);
    }
    if(!current.description && fields.description) changes.description=fields.description;
    if(!Object.keys(changes).length) return {heading,text:current.split_mode==='items'?'请在各项明细下面勾选参与的人，勾好后就能试算每人应付给垫付人的金额。':'还缺少可确认的信息。可以告诉我「小周垫付，小林和小陈均分」，或在当前账单选择成员。'};
    return {heading,text:summary.join('\n'),actionLabel:'应用到当前账单',action:()=>{
      if(!draft||draft.id!==key||committing)return;
      const data=readForm();
      if(changes.currency && changes.currency!==data.currency) delete data.fx;
      Object.assign(data,changes);
      assistantDialog.close();showDraft({...draft,data,dirty:true,note:'已更新本单，请核对后确认。'});
      $('draft').scrollIntoView({block:'nearest'});
    }};
  }
  async function assistantReply(question) {
    const {intent,estimate,priceReply,askedCurrency}=SplitAssistant;
    if(pendingField && pendingField.id===draft?.id) {
      const name=question.trim().replace(/[。！]$/,'');
      const field=pendingField.field;pendingField=null;
      const exact=active().find(person=>person.name===name);
      if(field==='payer' && exact) return billChange({payer:exact.id},'账本工具');
      if(field==='people') {
        const people=exact?[exact]:name.split(/[、，,和与]/).map(n=>active().find(m=>m.name===n.trim()));
        if(people.every(Boolean)) {
          const ids=[...new Set(people.map(p=>p.id))];
          const mode=modeOf(draft.data);
          return billChange({people:ids,split_mode:mode,split_values:draft.data.split_values},'账本工具');
        }
      }
    }
    const asksAboutThisBill=draft?.data.split_mode==='items' && /(?:这(?:笔|张|单)|当前).*(?:给谁|给.*多少|该付|应付)|每个?人.*给.*垫付人/.test(question);
    const local=asksAboutThisBill?'quote':intent(question);
    let plan=local?{tool:local}:null;
    if(!plan && modelName) {
      try {plan=await api('assistant',{question,has_draft:Boolean(draft)});} catch {}
      if(plan?.engine!=='ollama') plan=null;
    }
    if(!plan) plan=await devicePlan(question);
    const heading=plan.engine==='ollama'?'Ollama · '+modelName:plan.engine==='bge'?'设备端 AI · BGE':'账本工具';
    if(!ready && ['draft','quote','exchange','settlement'].includes(plan.tool)) return {heading,text:ledgerAccessMessage};
    if(plan.tool==='exchange') {
      if(!draft) return {heading,text:'请先拍小票或创建账单，再选要结算的币种。每张账单都能按约定汇率或参考汇率换算。'};
      const data=readForm();
      if(!data.currency) return {heading,text:'请先核对小票，用「票面币种」标明原币，再换算。'};
      const target=SplitAssistant.exchangeTarget(question,data.currency);
      if(target && target!==(data.fx?.currency||data.currency)) {
        const key=draft.id;
        const original=target===data.currency;
        return {heading,text:original?'可以恢复按票面币种 '+target+' 分摊。':'可以按 '+target+' 结算。选好汇率后，这张账单会列出每个人应摊多少。',
          actionLabel:'用 '+target+' 结算',action:()=>{
            if(!draft||draft.id!==key||$('currency').value!==data.currency)return;
            assistantDialog.close();$('fx-currency').value=original?'':target;
            $('fx-currency').dispatchEvent(new Event('input',{bubbles:true}));$(original?'fx-currency':'fx-rate').focus();
          }};
      }
      if(!data.fx) return {heading,text:'本单使用票面币种 '+(data.currency||'（待选择）')+'。在「结算币种」中可改选人民币、澳元或美元。'};
      const converted=SplitTools.convertedCents(data.amount,data.fx.rate);
      if(converted===null) return {heading,text:'请在本单填写约定汇率，或点击「取参考汇率」，再计算每个人的金额。'};
      const q=quote(data,members), lines=q?.settlement?.shares.map(s=>historyName(s.id)+' '+data.fx.currency+' '+major(s.cents));
      return {heading,text:exchangeLabel(data)+'\n结算合计 '+data.fx.currency+' '+major(converted)+'\n'+(lines?.join('\n')||problem(data,members))};
    }
    if(plan.tool==='price') {
      const price=estimate(question);
      return {heading,text:price?priceReply(price):'请给出原价、币种和要分的人数。可以加一项折扣和一项小费，例如「120 元打 8 折，加 10% 小费，3 人均分」。'};
    }
    if(plan.tool==='settlement') {
      const currency=askedCurrency(question,$('currency-view').value);
      if(!currency) return {heading,text:'请指定这次只看哪种币种：澳元、人民币或美元。'};
      const {total,entries,transfers}=summarize(records,members,currency);
      if(!entries.length) return {heading,text:currency+' 暂无已入账的费用。'};
      const detail=transfers.length?transfers.map(t=>transferLine(t,currency)).join('\n'):'组内余额已结清。';
      return {heading,text:entries.length+' 笔已入账，共 '+currency+' '+major(total)+'。\n'+detail};
    }
    if(plan.tool==='quote') {
      if(!draft) return {heading,text:'请先说一笔费用或拍照创建草稿，再来看每个人怎么分。'};
      const data=readForm();
      const issue=SplitDevice.eligibility(data,members,draft.original)||problem(data,members);
      if(issue) {
        if(!data.payer || (!data.people.length && data.split_mode!=='items')) {
          const field=data.payer?'people':'payer';
          pendingField={id:draft.id,field};
          const prompt=field==='payer'?'这笔是谁垫付的？可以直接回复姓名。':'这笔由哪几位分摊？可以用顿号隔开姓名。';
          return {heading,text:prompt+'\n本组成员：'+active().map(m=>m.name).join('、')};
        }
        return {heading,text:data.split_mode==='items' && data.items.some(item=>!item.people.length)?
          '请为每一项勾选参与人，还待分配的有 '+data.items.filter(item=>!item.people.length).map(i=>i.description||'未命名明细').join('、')+'。':issue};
      }
      const q=quote(data,members), split=q.settlement||q, unit=data.fx?.currency||data.currency;
      const transfers=data.split_mode==='items'?SplitTools.billTransfers(q,data.payer).map(t=>transferLine(t,unit)):[];
      return {heading,text:'草稿预览 · '+data.description+'\n'+(data.fx?exchangeLabel(data)+'\n':'')+split.shares.map(share=>
        historyName(share.id)+'  '+unit+' '+major(share.cents)).join('\n')+
        (transfers.length?'\n本单应付给垫付人\n'+transfers.join('\n'):'')};
    }
    if(plan.tool==='draft') {
      let result;
      try { result=await prepareDraft(question); }
      catch {
        result=parse(question,active());
        result.note='模型当前不可用。'+result.note;
      }
      const {data,blocked,note}=result;
      if(blocked) return {heading,text:note};
      if(draft && !/另(?:外)?(?:记|一笔)|新建.{0,3}(?:费用|账单|一笔)/.test(question)) return billChange(data,heading);
      const summary=[data.description,data.currency,data.amount].filter(Boolean).join(' ');
      return {heading:result.engine==='ollama'?'Ollama · '+modelName:heading,
        text:[summary,note].filter(Boolean).join('\n'),result};
    }
    return {heading,text:plan.message||'可以问「谁该付款」「这笔草稿怎么分」，或试算一笔费用：120 元打 8 折，3 人均分。'};
  }
  $('assistant-form').onsubmit=async event=>{
    event.preventDefault();
    const input=$('assistant-question'), question=input.value.trim();
    if(assisting||question.length<2) return;
    assisting=true;$('send-assistant').disabled=true;$('send-assistant').textContent='处理中';
    assistantMessage(question,'user');
    input.value='';
    try {
      const {text,heading,result,action,actionLabel}=await assistantReply(question);
      const row=assistantMessage(text,'answer',heading);
      if(result) row.append(button('填入草稿','secondary',()=>applyDraft(assistantDialog,result,question)));
      if(action) row.append(button(actionLabel,'secondary',action));
    } catch {
      assistantMessage('助手暂时无法连接。仍可试算折扣、查看草稿分摊和已入账结算。','answer','账本工具');
    } finally {
      assisting=false;$('send-assistant').disabled=false;$('send-assistant').textContent='发送';
      if(!assistantDialog.open) releaseLanguageModel();
    }
  };

  let installPrompt;
  const syncInstall=()=>{$('install-app').hidden=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;};
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;});
  window.addEventListener('appinstalled',()=>{installPrompt=null;$('install-app').hidden=true;});
  $('close-install').onclick=()=>$('install-dialog').close();
  $('install-app').onclick=async()=>{
    if(!installPrompt){$('install-dialog').showModal();return;}
    const prompt=installPrompt;installPrompt=null;
    try {
      const choice=await prompt.prompt();
      if(choice?.outcome==='accepted') $('install-app').hidden=true;
    }
    catch { $('install-dialog').showModal(); }
  };
  syncInstall();

  function exampleText(kind) {
    const group=active().slice(0,3), n=group.length;
    if (!n) return '';
    if(n===3) {
      const replacements=Object.fromEntries(SplitTools.members.map((m,i)=>[m.name,group[i].name]));
      return fallbackExamples[kind].replace(/小林|小周|小陈/g,s=>replacements[s]);
    }
    const a=group[0].name, b=group[1]?.name, who=group.map(m=>m.name).join('、');
    const rule={dinner:who+'均摊',exact:b?a+'承担 40 澳元、'+b+'承担 20 澳元':a+'承担 60 澳元',
      percentage:b?a+'占 60%、'+b+'占 40%':a+'占 100%',shares:b?who+'按 2:1 分摊':a+'承担 1 份'};
    return '晚餐共 60 澳元，'+a+'垫付，'+rule[kind]+'。';
  }
  for(const b of document.querySelectorAll('[data-example]')) b.onclick=()=>{
    const text=exampleText(b.dataset.example);
    if(!text){status('请先在成员管理中添加组员。',true);return;}
    $('expense-text').value=text;$('expense-text').focus();
  };
  let editingMember=null, changingMember=false;
  function renderRoster() {
    const list=$('member-list');list.replaceChildren();
    for(const member of [...members].sort((a,b)=>Number(b.active)-Number(a.active)||a.id-b.id)) {
      const row=el('div',null,'roster-row');
      row.dataset.id=member.id;
      if(member.active===false)row.classList.add('removed');
      row.append(avatar(member.id));
      if(editingMember?.member.id===member.id) {
        const form=el('form',null,'rename-form'), input=el('input');
        input.value=editingMember.name;input.required=true;input.setAttribute('aria-label','新姓名');
        input.oninput=()=>{editingMember.name=input.value;};
        const save=el('button','保存');save.type='submit';
        form.append(input,save,button('取消','roster-link',()=>{editingMember=null;renderRoster();}));
        form.onsubmit=e=>{e.preventDefault();changeMember(editingMember.member,{name:input.value});};
        row.append(form);list.append(row);input.focus();input.select();continue;
      }
      const copy=el('span',member.name,'roster-name');
      if(member.active===false)copy.append(el('small','已移出'));
      row.append(copy,button('改名','roster-link',()=>{editingMember={member,name:member.name};renderRoster();}));
      row.append(button(member.active===false?'恢复':'移出','roster-link',()=>changeMember(member,{active:member.active===false})));
      list.append(row);
    }
  }
  async function changeMember(member,changes) {
    if(changingMember)return;
    changingMember=true;$('member-feedback').textContent='';
    try {
      if(service && member) await api('members/'+member.id,{version:member.version,...changes},'PUT');
      else if(service) await api('members',changes);
      else await SplitDevice.saveMember(member,changes);
      editingMember=null;if(!member)$('member-name').value='';
      await refresh();renderRoster();channel?.postMessage('refresh');
      $('member-feedback').textContent=member?(changes.name?'姓名已保存。':changes.active?'已恢复成员。':'已移出成员。'):'已添加成员。';
    } catch(err){$('member-feedback').textContent=err.message;await refresh();}
    finally {changingMember=false;}
  }
  $('draft-members').onclick=$('add-first-member').onclick=$('manage-members').onclick=()=>{
    editingMember=null;$('member-feedback').textContent='';renderRoster();$('member-dialog').showModal();
  };
  $('close-members').onclick=()=>$('member-dialog').close();
  $('member-form').onsubmit=e=>{e.preventDefault();changeMember(null,{name:$('member-name').value});};
  $('currency-view').onchange=renderLedger;
  const sampleKey='split-studio-show-samples';
  try {$('show-samples').checked=localStorage.getItem(sampleKey)!=='false';}catch{}
  $('show-samples').onchange=()=>{
    try {localStorage.setItem(sampleKey,String($('show-samples').checked));}catch{}
    renderLedger();
  };
  if (channel) channel.onmessage=()=>refresh().catch(err=>status(err.message,true));
  window.addEventListener('split-storage-blocked',()=>status('请关闭仍开着的旧版账本窗口，随后会自动打开新账本。'));
  window.addEventListener('focus',()=>{if(ready)refresh().catch(err=>status(err.message,true));});
  function openShortcut() {
    const target=location.hash==='#scan'?receiptDialog:location.hash==='#assistant'?assistantDialog:null;
    if(!target || target.open) return;
    document.querySelector('dialog[open]')?.close();
    if(target===receiptDialog) openReceipt(); else openAssistant();
  }
  window.addEventListener('hashchange',openShortcut);
  openShortcut();
  async function start() {
    $('parse').disabled=true;
    if(service){
      const session=await api('session',{});modelName=session.model;
      $('storage-mode').textContent='本次会话的服务端账本';
      $('engine').textContent=modelName?'本机模型 · '+modelName:'规则提取 · API 入账';
      if(modelName) $('assistant-engine').textContent='本机模型 · '+modelName;
    } else {
      try { const res=await fetch('splitagent-evaluation.json');if(res.ok)archive=(await res.json()).cases||[]; }catch{}
    }
    await refresh();ready=true;status('');$('parse').disabled=false;$('manage-members').disabled=false;
    if(!service)try {const old=JSON.parse(sessionStorage.getItem(draftKey));if(old?.id && Array.isArray(old.data?.people) && Array.isArray(old.trace))showDraft(old);}catch{}
    previewReceipt();
  }
  start().catch(()=>{
    ledgerAccessMessage=service?'无法打开账本会话，请重新连接后刷新。':'请允许浏览器保存此网站的数据，再刷新打开账本。';
    status(ledgerAccessMessage,true);
    previewReceipt();
  });
})();
