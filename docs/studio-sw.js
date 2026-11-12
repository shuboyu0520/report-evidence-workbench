'use strict';
// Only the public application shell is cached. Original user files and API responses are excluded.
const prefix='agent-studio:'+self.registration.scope+':';
const cacheName=prefix+'2026-11-12.5';
const paths=['index.html','splitagent.html','evidence-review.html','evidence-review.js','evidence-review-data.js',
  'splitagent-evaluation.json','studio/ui.css','studio/split-ledger.css','studio/weekend-coast.webp','studio/common.js','studio/split-tools.js','studio/split-store.js','studio/split.js',
  'studio/documents.js','studio/company-reports.js','studio/company-reader-runs.js','studio/tech-validation.js','studio/reports.webmanifest','studio/split.webmanifest',
  ...['split','reports'].flatMap(key=>[180,192,512].map(size=>'studio/'+key+'-'+size+'.png')),
  'studio/vendor/pdf.min.mjs','studio/vendor/pdf.worker.min.mjs'];
const urls=new Set(paths.map(path=>new URL(path,self.registration.scope).href));
self.addEventListener('install',event=>event.waitUntil((async()=>{
  const cache=await caches.open(cacheName);
  await cache.addAll([...urls].map(url=>new Request(url,{cache:'reload'})));
  await self.skipWaiting();
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  for(const key of await caches.keys())if(key.startsWith(prefix)&&key!==cacheName)await caches.delete(key);
  await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);url.search='';url.hash='';
  if(url.href===self.registration.scope)url.pathname+='index.html';
  if(!urls.has(url.href))return;
  event.respondWith((async()=>{
    const cache=await caches.open(cacheName);
    const cached=await cache.match(url.href);
    return cached || fetch(event.request);
  })());
});
