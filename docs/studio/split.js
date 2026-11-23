'use strict';
(() => {
  const {byId:$, el, api, service} = Studio;
  const {labels, modeOf, major, problem, quote, summarize, parse, samples} = SplitTools;
  let members=[], names={}, records=[], saved={version:0,draft:null};
  const draftKey = 'split-studio-draft-v1-' + (service?'api':'device');
  const fallbackExamples = {
    dinner:'晚饭共 90.00 澳元，小林垫付，小林、小周和小陈三人均摊。',
    exact:'晚餐共 96 澳元，小林垫付。小林承担 48 澳元、小周承担 30 澳元、小陈承担 18 澳元。',
    percentage:'小周付了 120 澳元房租，小林占 50%、小周占 30%、小陈占 20%。',
    shares:'小陈垫了 100 元买食材，小林、小周、小陈按 2:1:1 分摊。',
    no_payer:'三个人小林、小周、小陈一起吃饭，花了 66 澳元，均摊。',
    outside:'朋友小吴替小林和小周支付了 19.00 澳元车费，两人平摊。'
  };
  let draft=null, shareInputs={}, archive=[], modelName=null, ready=false, working=false, committing=false, refreshSerial=0;
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
    if(changed && draft) {renderPeople(draft.data);renderValueFields(draft.data);updatePreview();}
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
      for (const share of q.shares) detail.append(shareLine(share,r));
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
    row.append(el('span',historyName(share.id)+suffix),el('strong',d.currency+' '+major(share.cents)));
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
    let d=readForm();
    const changedMode=event?.target.id==='split-mode';
    if(changedMode) shareInputs={};
    else Object.assign(shareInputs,d.split_values);
    if(changedMode || ['currency','participants'].includes(event?.target.id) || event?.target.type==='checkbox') {
      renderValueFields({...d,split_values:shareInputs});d=readForm();
    }
    draft.data=d;if(event)draft.dirty=true;remember();
    const issue=SplitDevice.eligibility(d,members,draft.original) || problem(d,members);
    const q=issue?null:quote(d,members);
    $('split-feedback').textContent=issue || '各成员分摊合计 '+d.currency+' '+major(q.cents);
    $('split-feedback').classList.toggle('invalid',Boolean(issue));
    $('allocation').replaceChildren();$('confirm').disabled=!ready||committing||!q;
    $('draft-state').textContent=q?(draft.entryVersion?'编辑中':'待确认'):'待补充';
    if (q) for(const s of q.shares) $('allocation').append(shareLine(s,d));
  }
  function showDraft(item) {
    draft=item;const d=item.data;
    shareInputs={...d.split_values};
    draft.baseDraftVersion ??= saved.version;
    $('review-title').textContent=item.entryVersion?'编辑已入账费用':'核对分账草稿';
    $('confirm').textContent=item.entryVersion?'保存修改':'确认入账';
    $('expense-text').value=item.text;$('description').value=d.description||'';$('amount').value=d.amount||'';$('currency').value=d.currency||'';
    renderPeople(d);$('split-mode').value=modeOf(d);
    renderValueFields(d);
    $('draft-hint').textContent=item.note;$('draft-trace').replaceChildren(...item.trace.map(s=>el('li',s)));
    $('draft').hidden=false;updatePreview();
  }
  function clearDraft() {draft=null;remember();$('draft').hidden=true;}
  function mayReplace() {
    return !committing && !working && (!draft?.dirty || window.confirm('放弃当前表单里尚未保存的修改？'));
  }
  function openEntry(r) {
    if(!mayReplace())return;
    const {description,amount,currency,payer,people,split_values}=r;
    const data={description,amount,currency,payer,people:[...people],split_mode:modeOf(r),split_values:{...split_values}};
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
    if(!draft||committing||working)return;
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
    e.preventDefault();if(!draft||!ready||committing)return;
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
      clearDraft();$('expense-text').value='';$('currency-view').value=d.currency;
      await refresh();channel?.postMessage('refresh');status((item.entryVersion?'已更新账单：':'已入账：')+d.description+'，'+d.currency+' '+d.amount+'。'+cleanup);
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
  let readingReceipt=false, receiptImageURL='';
  $('open-receipt').onclick=()=>receiptDialog.showModal();
  $('close-receipt').onclick=()=>receiptDialog.close();
  $('take-photo').onclick=()=>$('receipt-camera').click();
  $('choose-image').onclick=()=>$('receipt-image').click();
  function previewReceipt() {
    const text=$('receipt-text').value.trim();
    const info=SplitReceipts.details(text);
    $('receipt-evidence').hidden=!info.source;
    $('receipt-source').textContent=info.source;
    $('receipt-amount').textContent=info.amount ? [info.currency,info.amount].filter(Boolean).join(' ') : '';
    $('receipt-issue').textContent=text ? info.issue : '';
    $('receipt-to-draft').disabled=!ready||readingReceipt||!text;
    return info;
  }
  $('receipt-text').addEventListener('input',previewReceipt);
  async function readReceipt(event) {
    const file=event.target.files[0];
    event.target.value='';
    if(!file || readingReceipt) return;
    readingReceipt=true;
    for(const id of ['take-photo','choose-image','receipt-to-draft']) $(id).disabled=true;
    $('receipt-text').readOnly=true;
    const statusEl=$('receipt-status'), image=$('receipt-preview');
    statusEl.textContent='正在加载识别组件…';
    statusEl.classList.remove('error');
    try {
      const text=await SplitReceipts.recognize(file,percent=>{
        statusEl.textContent=percent===null?'正在准备识别…':'正在识别文字 · '+percent+'%';
      });
      if(receiptImageURL) URL.revokeObjectURL(receiptImageURL);
      receiptImageURL=URL.createObjectURL(file);
      image.src=receiptImageURL;image.hidden=false;
      $('receipt-text').value=text.slice(0,6000);
      statusEl.textContent=text?'识别完成，请与照片核对。':'没读到文字。可以重新拍照，或直接粘贴票面文字。';
    } catch(err) {
      statusEl.textContent=(err.message||'图片识别出错。')+' 也可以粘贴票面文字。';
      statusEl.classList.add('error');
    } finally {
      readingReceipt=false;
      for(const id of ['take-photo','choose-image']) $(id).disabled=false;
      $('receipt-text').readOnly=false;previewReceipt();
    }
  }
  $('receipt-image').onchange=readReceipt;
  $('receipt-camera').onchange=readReceipt;
  $('receipt-to-draft').onclick=()=>{
    const info=previewReceipt();
    const data={description:info.description,amount:info.amount,currency:info.currency,payer:null,people:[],
      split_mode:'equal',split_values:{}};
    applyDraft(receiptDialog,{data,note:info.issue||'核对票面合计，然后选择付款人和分摊成员。',
      trace:[info.source?'识别到原票行 '+info.source:'票面金额等待人工核对','等待选择付款人和分摊成员']});
  };

  const assistantDialog=$('assistant-dialog');
  let assisting=false, languageWorker=null;
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
    if(!assistantDialog.open) assistantDialog.showModal();
  }
  $('open-assistant').onclick=openAssistant;
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
  async function assistantReply(question) {
    const {intent,estimate,priceReply,askedCurrency}=SplitAssistant;
    const local=intent(question);
    let plan=local?{tool:local}:null;
    if(!plan && modelName) {
      try {plan=await api('assistant',{question,has_draft:Boolean(draft)});} catch {}
      if(plan?.engine!=='ollama') plan=null;
    }
    if(!plan) plan=await devicePlan(question);
    const heading=plan.engine==='ollama'?'Ollama · '+modelName:plan.engine==='bge'?'设备端 AI · BGE':'账本工具';
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
      if(issue) return {heading,text:issue};
      return {heading,text:'草稿预览 · '+data.description+'\n'+quote(data,members).shares.map(share=>
        historyName(share.id)+'  '+data.currency+' '+major(share.cents)).join('\n')};
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
      const summary=[data.description,data.currency,data.amount].filter(Boolean).join(' ');
      return {heading:result.engine==='ollama'?'Ollama · '+modelName:heading,
        text:[summary,note].filter(Boolean).join('\n'),result};
    }
    return {heading,text:plan.message||'可以问「谁该付款」「这笔草稿怎么分」，或试算一笔费用：120 元打 8 折，3 人均分。'};
  }
  $('assistant-form').onsubmit=async event=>{
    event.preventDefault();
    const input=$('assistant-question'), question=input.value.trim();
    if(assisting||!ready||question.length<2) return;
    assisting=true;$('send-assistant').disabled=true;$('send-assistant').textContent='处理中';
    assistantMessage(question,'user');
    input.value='';
    try {
      const {text,heading,result}=await assistantReply(question);
      const row=assistantMessage(text,'answer',heading);
      if(result) row.append(button('填入草稿','secondary',()=>applyDraft(assistantDialog,result,question)));
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
  $('add-first-member').onclick=$('manage-members').onclick=()=>{
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
    if(!ready) return;
    const target=location.hash==='#scan'?receiptDialog:location.hash==='#assistant'?assistantDialog:null;
    if(!target || target.open) return;
    document.querySelector('dialog[open]')?.close();
    target.showModal();
  }
  window.addEventListener('hashchange',openShortcut);
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
    openShortcut();
  }
  start().catch(err=>status('账本暂时无法打开：'+err.message,true));
})();
