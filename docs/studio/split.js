'use strict';
(() => {
  const {byId:$, el, api, service} = Studio;
  const {members, labels, modeOf, major, problem, quote, parse, samples} = SplitTools;
  const names = Object.fromEntries(members.map(m=>[m.id,m.name]));
  const draftKey = 'split-studio-draft-v1-' + (service?'api':'device');
  const fallbackExamples = {
    dinner:'晚饭共 90.00 澳元，小林垫付，小林、小周和小陈三人均摊。',
    exact:'晚餐共 96 澳元，小林垫付。小林承担 48 澳元、小周承担 30 澳元、小陈承担 18 澳元。',
    percentage:'小周付了 120 澳元房租，小林占 50%、小周占 30%、小陈占 20%。',
    shares:'小陈垫了 100 元买食材，小林、小周、小陈按 2:1:1 分摊。',
    no_payer:'三个人小林、小周、小陈一起吃饭，花了 66 澳元，均摊。',
    outside:'朋友小吴替小林和小周支付了 19.00 澳元车费，两人平摊。'
  };
  let dbPromise, records = [], draft = null, archive = [], model = null, ready = false, working = false, committing = false;
  function id() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes=crypto.getRandomValues(new Uint8Array(16)); bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
    const s=Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('');
    return [s.slice(0,8),s.slice(8,12),s.slice(12,16),s.slice(16,20),s.slice(20)].join('-');
  }
  function deviceDB() {
    if (!dbPromise) dbPromise = new Promise((resolve,reject)=>{
      const req=indexedDB.open('split-studio-v1',1);
      req.onupgradeneeded=()=>req.result.createObjectStore('entries',{keyPath:'id'});
      req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
    });
    return dbPromise;
  }
  async function deviceEntries() {
    const db=await deviceDB();
    return new Promise((resolve,reject)=>{
      const req=db.transaction('entries').objectStore('entries').getAll();
      req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
    });
  }
  async function deviceConfirm(entry) {
    const db=await deviceDB();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('entries','readwrite'), store=tx.objectStore('entries'), req=store.get(entry.id);
      let mismatch=false;
      req.onsuccess=()=>{
        if (!req.result) store.add(entry);
        else if (signature(req.result)!==signature(entry)) {
          mismatch=true; tx.abort();
        }
      };
      tx.oncomplete=resolve; tx.onabort=()=>reject(Error(mismatch?'相同草稿已经按其他内容入账。':'账本写入失败，请重试。'));
    });
  }
  function signature(entry) {
    const people=[...entry.people].sort((a,b)=>a-b), mode=modeOf(entry);
    return JSON.stringify([entry.description,entry.amount,entry.currency,entry.payer,mode,people,
      mode==='equal'?[]:people.map(id=>Number(entry.split_values[id]))]);
  }
  const channel = 'BroadcastChannel' in window ? new BroadcastChannel('split-studio-'+(service?'api':'device')) : null;
  function status(message, error=false) {
    $('split-status').classList.toggle('error',error);
    $('split-status').textContent=message;
  }
  function avatar(m) {
    const x=el('span',names[m].slice(-1),'avatar');x.dataset.person=m;x.setAttribute('aria-hidden','true');return x;
  }
  async function refresh() {
    const own=service ? await api('entries') : await deviceEntries();
    own.sort((a,b)=>String(b.created).localeCompare(String(a.created)));
    records=[...own,...samples];
    renderLedger();
  }
  function renderLedger() {
    const currency=$('currency-view').value, rows=records.filter(r=>r.currency===currency);
    const balances=Object.fromEntries(members.map(m=>[m.id,0])); let total=0;
    $('ledger').replaceChildren();
    for (const r of rows) {
      const q=quote(r); if (!q) continue;
      balances[r.payer]+=q.cents;total+=q.cents;
      q.shares.forEach(s=>balances[s.id]-=s.cents);
      const entry=el('details',null,'ledger-entry'), line=el('summary',null,'ledger-row'), copy=el('div',null,'row-copy');
      copy.append(el('strong',r.description),el('small',names[r.payer]+'垫付 · '+labels[modeOf(r)]+' · '+r.people.length+'人'+(r.sample?' · 示例':'')));
      line.append(avatar(r.payer),copy,el('span',major(q.cents),'amt'));
      const detail=el('div',null,'entry-allocations');
      for (const share of q.shares) detail.append(shareLine(share,r));
      entry.append(line,detail);$('ledger').append(entry);
    }
    if (!rows.length) $('ledger').append(el('p','这个币种还没有账单。','hint'));
    $('total').replaceChildren(el('i',currency+' '),document.createTextNode(major(total)));
    $('entry-count').textContent=rows.length+' 笔支出'+(rows.some(r=>r.sample)?' · 含 '+rows.filter(r=>r.sample).length+' 笔示例':'');
    $('ledger-unit').textContent=currency;
    $('balances').replaceChildren();
    const absMax=Math.max(1,...Object.values(balances).map(Math.abs));
    for (const m of members) {
      const v=balances[m.id], row=el('div',null,'balance-row'), copy=el('div',null,'row-copy'), bar=el('div',null,'bar'), fill=el('span');
      fill.style.width=(Math.abs(v)/absMax*100)+'%';bar.append(fill);
      copy.append(el('strong',m.name),bar);
      row.append(avatar(m.id),copy,el('span',v===0?'已结清':(v>0?'应收 ':'应付 ')+major(Math.abs(v)),v>0?'credit':'debit'));
      $('balances').append(row);
    }
    const debtors=members.filter(m=>balances[m.id]<0), creditors=members.filter(m=>balances[m.id]>0);
    const transfers=[]; let i=0,j=0;
    while (i<debtors.length && j<creditors.length) {
      const a=debtors[i],b=creditors[j],n=Math.min(-balances[a.id],balances[b.id]);
      transfers.push(a.name+' → '+b.name+' '+currency+' '+major(n));balances[a.id]+=n;balances[b.id]-=n;
      if (!balances[a.id]) i++;if (!balances[b.id]) j++;
    }
    $('settlement').replaceChildren(...(transfers.length?transfers:['当前币种已结清。']).map(t=>el('span',t,'transfer')));
  }
  function readForm() {
    const people=[...document.querySelectorAll('#draft input[type=checkbox]:checked')].map(box=>Number(box.value));
    const values=Object.fromEntries([...$('split-values').querySelectorAll('input[data-person]')]
      .filter(input=>people.includes(Number(input.dataset.person)))
      .map(input=>[input.dataset.person,input.value.trim()]));
    return {description:$('description').value.trim(),amount:$('amount').value.trim(),currency:$('currency').value,
      payer:Number($('payer').value)||null,people,split_mode:$('split-mode').value,split_values:values};
  }
  function shareLine(share,d) {
    const row=el('div',null,'quote-line'), mode=modeOf(d), value=d.split_values?.[share.id];
    const suffix=mode==='ratio'?' · '+value+' 份':mode==='percentage'?' · '+value+'%':'';
    row.append(el('span',names[share.id]+suffix),el('strong',d.currency+' '+major(share.cents)));
    return row;
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
  function remember() { try { if(draft) sessionStorage.setItem(draftKey,JSON.stringify(draft));else sessionStorage.removeItem(draftKey); }catch{} }
  function updatePreview(event) {
    if (!draft) return;
    let d=readForm();
    const changedMode=event?.target.id==='split-mode';
    if(changedMode || event?.target.id==='currency' || event?.target.type==='checkbox') {
      if(changedMode) d.split_values={};
      renderValueFields(d);d=readForm();
    }
    draft.data=d;remember();
    const q=quote(d), issue=problem(d);
    $('split-feedback').textContent=issue || '各成员分摊合计 '+d.currency+' '+major(q.cents);
    $('split-feedback').classList.toggle('invalid',Boolean(issue));
    $('allocation').replaceChildren();$('confirm').disabled=!ready||committing||!q;
    $('draft-state').textContent=q?'待确认':'待补充';
    if (q) for(const s of q.shares) $('allocation').append(shareLine(s,d));
  }
  function showDraft(item) {
    draft=item;const d=item.data;
    $('expense-text').value=item.text;$('description').value=d.description||'';$('amount').value=d.amount||'';$('currency').value=d.currency||'';
    $('payer').value=d.payer||'';$('split-mode').value=modeOf(d);
    document.querySelectorAll('#draft input[type=checkbox]').forEach(box=>box.checked=d.people.includes(Number(box.value)));
    renderValueFields(d);
    $('draft-hint').textContent=item.note;$('draft-trace').replaceChildren(...item.trace.map(s=>el('li',s)));
    $('draft').hidden=false;updatePreview();
  }
  function clearDraft() {draft=null;remember();$('draft').hidden=true;}
  function recorded(text) {
    const c=archive.find(row=>row.text===text);
    if (!c) return null;
    const a=c.replay;
    const d={description:a.description||'',amount:a.amount||'',currency:a.currency||'',payer:a.payer_user_id,people:a.participant_ids||[]};
    const blocked=!a.description&&!a.amount&&!a.currency;
    return {data:d,blocked,note:blocked?'该样例需要补充，请核对原始账单。':'这是 Qwen 对此固定样例的存档输出，请核对后入账。',trace:['匹配固定评测输入','读取 Qwen 复测字段','根据成员与金额校验草稿']};
  }
  async function createDraft(e) {
    e.preventDefault();if(working||committing) return;
    const text=$('expense-text').value.trim();if(text.length<2){status('请先输入一笔费用。',true);return;}
    working=true;$('parse').disabled=true;status('');
    try {
      let result=parse(text);
      if (!result.blocked) {
        if (service) {
          result=await api('drafts/parse',{text,proposal:result.data});
        } else if(result.data.split_mode==='equal') result=recorded(text)||result;
      }
      clearDraft();
      if(result.blocked){status(result.note);return;}
      showDraft({id:id(),text,...result});
      $('draft').tabIndex=-1;$('draft').focus({preventScroll:true});$('draft').scrollIntoView({block:'nearest'});
    } catch(err) {
      status(err.message,true);
      const manual=parse(text);
      if (!manual.blocked) showDraft({id:id(),text,...manual,note:'模型未完成提取。请手动核对以下本地预填字段。'});
    } finally {working=false;$('parse').disabled=!ready;}
  }
  $('compose').addEventListener('submit',createDraft);
  $('manual').addEventListener('click',()=>{
    if(!ready || working || committing) return;
    status('');
    showDraft({id:id(),text:'',data:{description:'',amount:'',currency:$('currency-view').value,
      payer:null,people:[],split_mode:'',split_values:{}},note:'填写支出并选择分摊方式。',trace:['手动录入','确认前逐人核对金额']});
    $('description').focus();
  });
  $('draft').addEventListener('input',updatePreview);
  $('discard').onclick=()=>{if(!committing){clearDraft();status('草稿已取消。');}};
  $('draft').addEventListener('submit',async e=>{
    e.preventDefault();if(!draft||!ready||committing)return;
    const d=readForm(), q=quote(d);if(!q)return;
    d.amount=major(q.cents);const entry={...d,id:draft.id,created:new Date().toISOString()};
    committing=true;$('confirm').disabled=true;$('parse').disabled=true;$('discard').disabled=true;
    try {
      if(service) await api('entries',{id:draft.id,data:d});else await deviceConfirm(entry);
      clearDraft();$('expense-text').value='';$('currency-view').value=d.currency;
      await refresh();channel?.postMessage('refresh');status('已入账：'+d.description+'，'+d.currency+' '+d.amount+'。');
    } catch(err){status(err.message,true);} finally {committing=false;$('discard').disabled=false;$('parse').disabled=!ready;updatePreview();}
  });
  for(const b of document.querySelectorAll('[data-example]')) b.onclick=()=>{
    $('expense-text').value=fallbackExamples[b.dataset.example];$('expense-text').focus();
  };
  $('currency-view').onchange=renderLedger;
  if (channel) channel.onmessage=()=>refresh().catch(err=>status(err.message,true));
  window.addEventListener('focus',()=>{if(ready)refresh().catch(err=>status(err.message,true));});
  async function start() {
    $('parse').disabled=true;
    if(service){
      const session=await api('session',{});model=session.model;
      $('storage-mode').textContent='本次会话的服务端账本';
      $('engine').textContent=model?'本机模型 · '+model:'规则提取 · API 入账';
    } else {
      try { const res=await fetch('splitagent-evaluation.json');if(res.ok)archive=(await res.json()).cases||[]; }catch{}
    }
    await refresh();ready=true;$('parse').disabled=false;
    try {const old=JSON.parse(sessionStorage.getItem(draftKey));if(old?.id && Array.isArray(old.data?.people) && Array.isArray(old.trace))showDraft(old);}catch{}
  }
  start().catch(err=>status('账本暂时无法打开：'+err.message,true));
})();
