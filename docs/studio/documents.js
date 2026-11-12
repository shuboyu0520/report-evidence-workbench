'use strict';
(() => {
  const {byId:$, el, service, searchScore, tokens} = Studio;
  let file=null, pages=[], url=null, sequence=0, generation=0, pdfTask=null;
  const limit=15*1024*1024;
  $('open-doc').onclick=()=>{ $('personal').hidden=false;$('personal').scrollIntoView({block:'start'});$('report-file').focus({preventScroll:true}); };
  $('close-doc').onclick=()=>{$('personal').hidden=true;$('open-doc').focus();};
  function clearFile() {
    if(url) URL.revokeObjectURL(url);
    if(pdfTask) {pdfTask.destroy().catch(()=>{});pdfTask=null;}
    file=null;pages=[];url=null;
    $('doc-status').textContent='';$('report-file-name').textContent='';$('doc-hits').replaceChildren();$('live-result').replaceChildren();
  }
  function sourceLink(number) {
    const a=el('a',file.name.toLowerCase().endsWith('.pdf')?'打开 PDF 第 '+number+' 页 ↗':'打开原文 ↗','paper-link');
    a.href=url+(file.name.toLowerCase().endsWith('.pdf')?'#page='+number:'');a.target='_blank';a.rel='noopener noreferrer';return a;
  }
  $('report-file').addEventListener('change', async () => {
    const seq=++sequence;generation++;clearFile();
    const next=$('report-file').files[0]; if(!next)return;
    let task=null;
    try {
      const pdf=/\.pdf$/i.test(next.name);
      if(!pdf&&!/\.txt$/i.test(next.name)) throw Error('请选择 PDF 或 UTF-8 TXT。');
      if(!next.size||next.size>limit) throw Error('文件为空或超过 15 MiB。');
      $('doc-status').textContent='正在解析文件…';
      const bytes=await next.arrayBuffer();let extracted=[];
      if(seq!==sequence)return;
      if(pdf){
        const pdfjs=await import('./vendor/pdf.min.mjs');
        if(seq!==sequence)return;
        pdfjs.GlobalWorkerOptions.workerSrc=new URL('studio/vendor/pdf.worker.min.mjs',location.href).href;
        task=pdfjs.getDocument({data:new Uint8Array(bytes),isEvalSupported:false,useSystemFonts:true});
        pdfTask=task;
        const doc=await task.promise;
        if(doc.numPages>500) throw Error('最多支持 500 页。');
        let size=0;
        for(let i=1;i<=doc.numPages;i++){
          const page=await doc.getPage(i);const text=await page.getTextContent();
          if(seq!==sequence)return;
          const lines=[];let line='';
          for(const part of text.items){if(typeof part.str==='string'){line+=part.str+' ';if(part.hasEOL){lines.push(line.trim());line='';}}}
          if(line.trim())lines.push(line.trim());
          size+=lines.reduce((n,l)=>n+l.length,0);
          if(size>3000000)throw Error('文档文字超过 300 万字符，请选取相关章节。');
          extracted.push(lines); page.cleanup();
        }
      } else {
        let text;
        try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw Error('请将 TXT 保存为 UTF-8 后重试。');}
        if(text.length>3000000)throw Error('文档文字超过 300 万字符。');
        extracted=text.split('\f').map(page=>page.split(/\r?\n/).map(l=>l.trim()).filter(Boolean));
        if(extracted.length>500)throw Error('最多支持 500 页。');
      }
      if(seq!==sequence)return;
      if(!extracted.some(p=>p.some(l=>l.trim())))throw Error('没有提取到文字。扫描版 PDF 需要先做 OCR。');
      file=next;pages=extracted;
      url=URL.createObjectURL(new Blob([next],{type:pdf?'application/pdf':'text/plain;charset=utf-8'}));
      $('report-file-name').textContent=file.name+'　·　'+pages.length+' 页';
      $('doc-status').textContent='解析完成，可输入指标查找原文。';
    } catch(err){if(seq===sequence)$('doc-status').textContent=err.name==='PasswordException'?'文件需要密码，请使用可读取的副本。':'无法读取：'+err.message;}
    finally {if(task && task===pdfTask){pdfTask=null;await task.destroy().catch(()=>{});}}
  });
  $('doc-search').onsubmit=e=>{
    e.preventDefault();$('doc-hits').replaceChildren();
    if(!pages.length){$('doc-status').textContent='请先选择一份财报。';return;}
    const query=$('doc-query').value.trim(),terms=tokens(query);if(!query)return;
    const found=[];
    pages.forEach((lines,i)=>{
      let best=null;
      lines.forEach((line,j)=>{
        const score=searchScore(query,line,terms);
        if(score>0 && (!best||score>best.score))best={page:i+1,j,score};
      });
      if(best)found.push(best);
    });
    found.sort((a,b)=>b.score-a.score || a.page-b.page);
    $('doc-status').textContent=found.length?'匹配 '+found.length+' 页，按相关性显示前 '+Math.min(6,found.length)+' 页。':'未找到匹配的原文。可试试英文指标名称。';
    for(const hit of found.slice(0,6)){
      const item=el('div',null,'hit'),lines=pages[hit.page-1];
      const text=lines.slice(Math.max(0,hit.j-1),hit.j+2).join('\n');
      item.append(sourceLink(hit.page),el('p',text.length>850?text.slice(0,850)+'…':text,'snippet'));$('doc-hits').append(item);
    }
  };
  async function jsonResponse(r) {
    const data=await r.json();
    if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'请求未完成（'+r.status+'）。');
    return data;
  }
  if(service){
    $('live-model').hidden=false;
    $('model-form').onsubmit=async e=>{
      e.preventDefault(); if(!file){$('live-result').textContent='请先选择财报。';return;}
      const seq=++generation;const active=file;const company=$('live-company').value.trim(), question=$('live-question').value.trim();
      if(!company||!question)return;
      $('ask-live').disabled=true;$('live-result').textContent='正在向当前实例提交资料…';
      try{
        const form=new FormData();form.append('company',company);form.append('published_on',$('published').value);form.append('file',active);
        const uploaded=await jsonResponse(await fetch('../reports',{method:'POST',body:form}));
        if(seq!==generation)return;
        $('live-result').textContent='正在核对报告期、检索原文并校验引文…';
        const answer=await jsonResponse(await fetch('../reports/'+encodeURIComponent(uploaded.id)+'/questions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,mode:'reader',as_of:$('published').value})}));
        if(seq!==generation)return;
        const result=$('live-result');result.replaceChildren(el('strong','阅读 Agent'),el('p',answer.answer));
        for(const c of answer.citations || []){
          let link=null;
          if(c.url) {
            try {
              const target=new URL(c.url);
              if(target.protocol==='https:' && !target.username && !target.password) {
                link=el('a',c.source || '打开官方引用页','paper-link');
                link.href=target.href;link.target='_blank';link.rel='noopener noreferrer';
              }
            } catch {}
          }
          if(!link && Number.isInteger(c.page)&&c.page>0&&c.page<=pages.length) link=sourceLink(c.page);
          if(link)result.append(link);
          if(c.quote)result.append(el('blockquote',c.quote));
        }
        const trace=el('details',null,'trace');trace.append(el('summary','查看实际工具调用'));
        const list=el('ol');for(const step of answer.trace||[])list.append(el('li',step.tool));trace.append(list);result.append(trace);
      }catch(err){if(seq===generation)$('live-result').textContent=err.message;}
      finally{$('ask-live').disabled=false;}
    };
  }
})();
