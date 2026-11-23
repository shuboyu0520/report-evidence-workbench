'use strict';
// Only the public application shell is cached. Original user files and API responses are excluded.
const prefix='agent-studio:'+self.registration.scope+':';
const cacheName=prefix+'2026-11-24.2';
const paths=['index.html','splitagent.html','evidence-review.html','evidence-review.js','evidence-review-data.js',
  'splitagent-evaluation.json','studio/ui.css','studio/split-ledger.css','studio/weekend-coast.webp','studio/common.js','studio/split-tools.js','studio/split-store.js','studio/split.js',
  'studio/split-receipts.js','studio/split-assistant.js','studio/split-language.mjs','studio/split-language-worker.mjs','studio/split-language-index.json',
  'studio/documents.js','studio/company-reports.js','studio/company-reader-runs.js','studio/tech-validation.js','studio/reports.webmanifest','studio/split.webmanifest',
  ...['split','reports'].flatMap(key=>[180,192,512].map(size=>'studio/'+key+'-'+size+'.png')),
  'studio/vendor/pdf.min.mjs','studio/vendor/pdf.worker.min.mjs'];
const urls=new Set(paths.map(path=>new URL(path,self.registration.scope).href));
const lazyUrls=new Set([
  ...['tesseract.min.js','worker.min.js','tesseract-core-lstm.wasm.js','eng.traineddata.gz','chi_sim.traineddata.gz'].map(path=>'ocr/'+path),
  ...['ort.wasm.min.mjs','ort-wasm-simd-threaded.mjs','ort-wasm-simd-threaded.wasm','bge-small-zh-int8.onnx','vocab.txt'].map(path=>'bge/'+path),
].map(path=>new URL('studio/vendor/'+path,self.registration.scope).href));
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
  const lazy=lazyUrls.has(url.href);
  if(!lazy&&!urls.has(url.href))return;
  event.respondWith((async()=>{
    const cache=await caches.open(cacheName);
    const cached=await cache.match(url.href);
    if(cached)return cached;
    const response=await fetch(event.request);
    if(lazy&&response.ok&&response.status!==206)await cache.put(url.href,response.clone()).catch(()=>{});
    return response;
  })());
});
