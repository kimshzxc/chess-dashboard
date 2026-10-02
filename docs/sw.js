/* 서비스 워커. 목표는 두 가지다.
   1) 온라인이면 항상 최신: 같은 출처의 GET 은 네트워크가 우선이고, GitHub Pages 의 max-age=600 브라우저 캐시를 건너뛰어
      ETag 로 재검증한다. 배포 직후 폰에 옛 스크립트가 남아 새 HTML 과 어긋나는 일이 없다.
   2) 오프라인이거나 네트워크가 6초 넘게 답이 없으면 마지막으로 받은 것을 보여 준다.
   캐시 키는 쿼리를 뗀 경로다 (game.html?id=… 는 모두 같은 문서). */
const CACHE = 'chess-dash-v1';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
  await self.clients.claim();
})()));
self.addEventListener('fetch', (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;   // 다른 출처(글꼴 CDN 등)는 브라우저에 맡긴다
  const key = url.origin + url.pathname;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const net = fetch(url.href, { cache: 'no-cache' }).then((res) => {
      // 리다이렉트를 거친 응답은 문서 탐색에 그대로 쓸 수 없어 새 응답으로 감싼다
      if (res.redirected) res = new Response(res.body, { status: res.status, statusText: res.statusText, headers: res.headers });
      if (res.ok) cache.put(key, res.clone());
      return res;
    });
    const hit = await cache.match(key);
    if (!hit) return net;
    return Promise.race([net, new Promise((r) => setTimeout(() => r(hit), 6000))]).catch(() => hit);
  })());
});
