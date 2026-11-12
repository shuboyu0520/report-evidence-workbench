'use strict';
const SplitDevice = (() => {
  let opening;
  function db() {
    if (!opening) opening=new Promise((resolve,reject)=>{
      const req=indexedDB.open('split-studio-v1',2);
      req.onupgradeneeded=()=>{
        const db=req.result;
        if (!db.objectStoreNames.contains('entries')) db.createObjectStore('entries',{keyPath:'id'});
        const members=db.createObjectStore('members',{keyPath:'id',autoIncrement:true});
        for (const m of SplitTools.members) members.add({...m,active:true,version:1});
        db.createObjectStore('drafts');
      };
      req.onsuccess=()=>{
        req.result.onversionchange=()=>{req.result.close();opening=null;};
        resolve(req.result);
      };
      req.onerror=()=>{opening=null;reject(req.error);};
      req.onblocked=()=>window.dispatchEvent(new Event('split-storage-blocked'));
    });
    return opening;
  }
  function result(req) {
    return new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});
  }
  async function transact(stores,mode,work) {
    const tx=(await db()).transaction(stores,mode);
    const complete=new Promise((resolve,reject)=>{
      tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error || Error('本次操作已取消。'));tx.onerror=()=>{};
    });
    try {
      const value=await work(name=>tx.objectStore(name));
      await complete;
      return value;
    } catch(error) {
      try {tx.abort();} catch {}
      await complete.catch(()=>{});throw error;
    }
  }
  function list(store) {
    return transact([store],'readonly',s=>result(s(store).getAll()));
  }
  function normalize(name) {
    return name.normalize('NFKC').trim();
  }
  async function saveMember(person,changes) {
    return transact(['members'],'readwrite',async s=>{
      const table=s('members'), rows=await result(table.getAll());
      const current=person && rows.find(m=>m.id===person.id);
      if (person && current?.version!==person.version) throw Error('成员资料已更新，请重新操作。');
      const text=changes.name ?? current?.name ?? '', name=normalize(text);
      if (!name || [...name].length>32 || /\p{C}/u.test(text)) throw Error('姓名须为 1 至 32 个可见字符。');
      if (rows.some(m=>m.id!==current?.id && normalize(m.name).toLowerCase()===name.toLowerCase())) throw Error('账本里已有同名成员，请使用其他称呼或恢复已有成员。');
      const member={...(current||{}),name,active:changes.active ?? current?.active ?? true,version:(current?.version||0)+1};
      if(current && current.name===member.name && current.active===member.active)return current;
      member.id=await result(table.put(member));return member;
    });
  }
  function signature(d) {
    const people=[...d.people].sort((a,b)=>a-b), mode=SplitTools.modeOf(d);
    return JSON.stringify([d.description,d.amount,d.currency,d.payer,mode,people,
      mode==='equal'?[]:people.map(id=>Number(d.split_values[id]))]);
  }
  function eligibility(d,people,original) {
    const active=new Set(people.filter(m=>m.active!==false).map(m=>m.id));
    if (d.payer && !active.has(d.payer) && original?.payer!==d.payer) return '所选付款人已移出，请改选在组成员。';
    if (d.people.some(id=>!active.has(id) && !original?.people.includes(id))) return '分摊名单中有已移出的成员，请取消勾选后重试。';
    return '';
  }
  async function saveEntry(id,data,version=null) {
    return transact(['members','entries'],'readwrite',async s=>{
      const table=s('entries');
      const [current,roster]=await Promise.all([result(table.get(id)),result(s('members').getAll())]);
      if (version==null && current) {
        if (signature(current)!==signature(data)) throw Error('同一张草稿已经按其他内容入账。');
        return current;
      }
      if (version!=null && (!current || (current.version||1)!==version)) throw Error('账单已在其他窗口修改，请重新打开最新账单后再编辑。');
      const issue=eligibility(data,roster,current) || SplitTools.problem(data,roster);
      if (issue) throw Error(issue);
      const entry={...data,id,created:current?.created || new Date().toISOString(),version:current?(current.version||1)+1:1};
      await result(table.put(entry));return entry;
    });
  }
  const empty={version:0,draft:null};
  function getDraft() {
    return transact(['drafts'],'readonly',async s=>(await result(s('drafts').get('saved'))) || empty);
  }
  function writeDraft(version,draft) {
    return transact(['drafts'],'readwrite',async s=>{
      const table=s('drafts'), current=(await result(table.get('saved'))) || empty;
      if (current.version!==version) throw Error('已保存的草稿有新的改动，请打开最新草稿后再操作。');
      const next={version:version+1,draft};
      await result(table.put(next,'saved'));return next;
    });
  }
  return {list,saveMember,eligibility,saveEntry,getDraft,writeDraft};
})();
