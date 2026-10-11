import { defineConfig } from "vite";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// Keep Blender's stable source/export paths, while production URLs identify
// exact bytes and can be cached without revalidation across deployments.
const models = ["archive-cassette", "archive-assembly"].map(name => {
  const source = readFileSync(`public/assets/${name}.glb`);
  const hash = createHash("sha256").update(source).digest("hex").slice(0,16);
  return { key:`assets/${name}.glb`, fileName:`assets/${name}.${hash}.glb`, source };
});
export default defineConfig(() => ({
  base: "/app/",
  define: {
    __RHINE_MODELS__: JSON.stringify(Object.fromEntries(models.map(model => [model.key,model.fileName]))),
  },
  plugins: [{
    name: "versioned-model-assets", apply: "build",
    buildStart() { for (const model of models) this.emitFile({type:"asset",fileName:model.fileName,source:model.source}); },
  }],
  // 默认构建目标是 baseline-widely-available（约 Safari 16），老 iPhone 的 Safari
  // 会因为解析不了新语法而整页白屏。降到 safari13，让 esbuild 把可选链、空值合并、
  // 类字段等语法降级，覆盖到 iOS 13 及以上。
  build: {
    target: ["es2019", "safari13"],
  },
  // 开发期把 /api 转发到 Flask 后端（默认 :5000，可用 VITE_API_PROXY 覆盖）。
  // 生产环境由 nginx 反代，见 deploy/nginx-social-sense.conf。
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY ?? "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
}));
