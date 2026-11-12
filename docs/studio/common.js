'use strict';

window.Studio = (() => {
  const service = document.querySelector('meta[name="studio-runtime"]').content === 'service';
  const byId = id => document.getElementById(id);
  function el(tag, text, cls) {
    const value = document.createElement(tag);
    if (text != null) value.textContent = text;
    if (cls) value.className = cls;
    return value;
  }
  async function api(path, body, method) {
    const options = {method:method || (body ? 'POST' : 'GET'), credentials:'same-origin'};
    if (body) {
      options.headers = {'Content-Type':'application/json'};
      options.body = JSON.stringify(body);
    }
    const response = await fetch(new URL('../api/studio/' + path, location.href), options);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw Error(typeof data.detail === 'string' ? data.detail : '请求失败（' + response.status + '）');
    }
    return response.json();
  }
  const ignore = new Set(['多少','什么','可以','请问','公司','集团','请给','给出','the','what','is','of','for','and','百万','美元']);
  const synonyms = [
    ['营收','营业收入','net revenues','total revenues','revenue'],
    ['净利润','净收益','net income'], ['调整后ebitda','adjusted ebitda','ebitda'],
    ['全年指引','指引','outlook','guidance'], ['同比','year over year','yoy'],
    ['自由现金流','free cash flow'], ['费用收入','gross fees'], ['每股收益','earnings per share','eps'],
    ['利息费用','interest expense'], ['营业利润','operating income'], ['客房收入','revpar']
  ];
  function normalize(value) { return String(value || '').normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim(); }
  function tokens(input) {
    const q = normalize(input);
    const hits = new Set();
    for (const match of q.matchAll(/[a-z0-9]+|[\u3400-\u9fff]+/g)) {
      const v = match[0];
      if (/^[a-z0-9]+$/.test(v) || v.length < 2) hits.add(v);
      else for (let i=0;i<v.length-1;i++) hits.add(v.slice(i,i+2));
    }
    for (const group of synonyms) {
      if (group.some(term=>q.includes(term))) for (const term of group) hits.add(term);
    }
    return [...hits].filter(t=>!ignore.has(t));
  }
  function searchScore(query, content, terms = tokens(query)) {
    const q = normalize(query), s = normalize(content);
    if (!q) return 0;
    const exact = s.includes(q) ? 14 : 0;
    return exact + terms.reduce((sum,t)=>sum+(s.includes(t) ? Math.min(6,t.length) : 0),0);
  }
  if (!service && 'serviceWorker' in navigator && ['https:','http:'].includes(location.protocol)) {
    window.addEventListener('load',()=>navigator.serviceWorker.register('./studio-sw.js').catch(()=>{}));
  }
  return {service, byId, el, api, tokens, searchScore};
})();
