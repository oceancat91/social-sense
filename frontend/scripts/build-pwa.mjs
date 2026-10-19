import { readdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
const root=resolve('dist');
const all=await readdir(root,{recursive:true});
const files=all.map(path=>path.replaceAll('\\','/')).filter(path=>
  path==='index.html'||path==='manifest.webmanifest'||path==='favicon.svg'||
  /^(assets|icons|archives|licenses)\/[^/]+\.[^/]+$/.test(path)||
  /^audio\/(atmosphere|motif|pulse)\.ogg$/.test(path)
  // 字体（fonts/，753 个 woff2）和 3D 模型（.glb）不进离线缓存。
  // 它们合计约 37 MB —— 首次进入就要下载这么多，移动网络下极易超时或中断，
  // 反而让「进入」变得不稳定。浏览器 HTTP 缓存会按需缓存实际用到的字体子集，
  // 离线时退化为系统字体（dashboard 里本来就有字体回退）。
).filter(path=>!/\.glb$/i.test(path)&&!/^fonts\//i.test(path)).sort();
if(!files.some(path=>/^assets\/index-.*\.js$/.test(path)))throw Error('Build the application before generating the offline cache.');
const worker=await readFile('scripts/pwa-worker.js','utf8');
const hash=createHash('sha256').update(worker);let bytes=0;
for(const file of files){const content=await readFile(resolve(root,file));hash.update(file).update(content);bytes+=content.length}
const version=hash.digest('hex').slice(0,16);
await writeFile(resolve(root,'sw.js'),worker.replace('__CACHE_VERSION__',JSON.stringify(version)).replace('__PRECACHE_FILES__',JSON.stringify(files)));
await writeFile(resolve(root,'pwa-build.json'),JSON.stringify({version,bytes,files},null,2));
console.log(`Offline release ${version}: ${files.length} files, ${(bytes/1024/1024).toFixed(1)} MiB.`);
