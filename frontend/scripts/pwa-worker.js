/* The build replaces both tokens; this file is never registered in development. */
const VERSION = __CACHE_VERSION__;
const FILES = __PRECACHE_FILES__;
const PREFIX = `rhine-lab:${new URL(self.registration.scope).pathname}:`;
const CACHE = PREFIX + VERSION;
const urls = FILES.map(path => new URL(path, self.registration.scope).href);
const allowed = new Set(urls);
const index = new URL("index.html", self.registration.scope).href;

self.addEventListener("install", event => {
  event.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE);
      // Limit connections so a complete font family does not flood the page.
      // Keep successful files private until every resource is present; failure
      // still deletes this entire release and leaves the active release intact.
      let next = 0;
      const workers = Array.from({ length: 6 }, async () => {
        while (next < urls.length) {
          const url = urls[next++];
          const immutable = /\/fonts\/misans-webfont-4\.3\.1\//.test(url) || /\/assets\/archive-(cassette|assembly)\.[a-f0-9]{16}\.glb$/.test(url);
          await cache.add(new Request(url, { cache: immutable ? "default" : "no-cache" }));
        }
      });
      const results = await Promise.allSettled(workers);
      const failure = results.find(result => result.status === "rejected");
      if (failure) throw failure.reason;
      // 新版本装好就立即接管，不等用户点「更新并重启」。
      // 旧版本装好却一直 waiting，是「要刷新好几次」的另一半原因：
      // 旧 SW 继续用旧策略返回旧 HTML，用户怎么刷都还在旧版本上。
      // 接管是安全的：导航已改为网络优先，未在当前缓存列表里的资源直接走网络，
      // 上一版缓存也会保留到下一次激活，不会让正在浏览的标签页当场丢资源。
      await self.skipWaiting();
    } catch (error) {
      await caches.delete(CACHE);
      throw error;
    }
  })());
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    // 只保留「当前」与「上一版」缓存。
    // 之前这里会立刻删掉所有旧版本缓存，而仍停留在旧页面上的标签页还在引用
    // 旧版本的 hashed 资源 —— 缓存被删 + 文件已被新部署替换，结果是白屏。
    const keys = (await caches.keys()).filter(key => key.startsWith(PREFIX) && key !== CACHE);
    for (const key of keys.slice(0, Math.max(0, keys.length - 1))) await caches.delete(key);
    await self.clients.claim();
  })());
});
self.addEventListener("message", event => {
  if (event.data?.type === "RHINE_APPLY_UPDATE") event.waitUntil(self.skipWaiting());
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  url.search = "";
  url.hash = "";
  const navigation = event.request.mode === "navigate" &&
    (url.href === self.registration.scope || url.href === index);
  const key = navigation ? index : url.href;
  if (!allowed.has(key)) return;

  // 导航（HTML）走网络优先。
  //
  // 之前这里是纯缓存优先：发布新版本后，旧 SW 依然把旧的 index.html 交出去，
  // 而它引用的 hashed 资源已经被新部署替换并删除 —— 于是页面白屏，
  // 用户必须反复刷新、直到新 SW 完成交接才进得去（"要刷新好几次"）。
  // 现在导航总是先取网络，取到就顺手更新缓存；离线时才回落到缓存。
  // 这样 index.html 永远是最新的，它引用的资源若不在本缓存允许列表里，
  // 下面的 !allowed.has(key) 会让浏览器直接走网络，不会出现版本错配。
  if (navigation) {
    event.respondWith((async () => {
      try {
        const response = await fetch(event.request, { cache: "no-store" });
        if (response.ok) {
          const cache = await caches.open(CACHE);
          await cache.put(key, response.clone());
        }
        return response;
      } catch (error) {
        const cache = await caches.open(CACHE);
        const cached = await cache.match(key);
        if (cached) return cached;
        throw error;
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    // Hashed bundles are content-addressed, so cache-first is safe for them.
    const cached = await cache.match(key);
    return cached ?? fetch(event.request);
  })());
});
