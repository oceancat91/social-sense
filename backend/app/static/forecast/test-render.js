const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
const JS = fs.readFileSync(path.join(__dirname, "events.js"), "utf8");

// 用真实后端的三个响应作为桩
const FIXTURES = {
  "/events": { code: 200, data: { events: [
    { event_id: "shanghai_luohu", name: "上海非沪籍高校毕业生落户政策", start: "2018-06-23", end: "2018-09-21",
      days: 91, volume: 17551, peak: 11995, peak_day: "2018-08-07", tau_days: 0.75, half_life_days: 0.52, decay_to_10pct_days: 1.73 },
    { event_id: "xinguan", name: "新冠疫情政策", start: "2020-01-20", end: "2020-03-11",
      days: 52, volume: 10953, peak: 1006, peak_day: "2020-01-26", tau_days: 10.75, half_life_days: 7.45, decay_to_10pct_days: 24.75 }
  ]}},
  "/event/shanghai_luohu": { code: 200, data: {
    event_id: "shanghai_luohu", peak_day: "2018-08-07", peak_volume: 11995,
    history: [{date:"2018-08-05",volume:300},{date:"2018-08-06",volume:1200},{date:"2018-08-07",volume:11995}],
    prediction: { dates: ["2018-08-08","2018-08-09"], volume: [3161.8, 833.5], tau_days: 0.75, half_life_days: 0.52 },
    actual: { dates: ["2018-08-08","2018-08-09"], volume: [4625, 173] },
    scores: { backtest_self_tau: { rel_error: 0.4843 }, live_global_tau: { rel_error: 1.6495 } },
    half_life_days: 0.52, decay_to_10pct_days: 1.73,
    caveat: "峰值前无法预测爆发幅度；本模型只描述爆发后的衰减形态。"
  }},
  "/event/shanghai_luohu/platforms": { code: 200, data: {
    event_id: "shanghai_luohu", total_samples: 6, platform_count: 2, adequate: false,
    platforms: [{platform:"weibo",count:4,like_sum:166,start:"2025-08-25",end:"2026-08-10"}],
    verdict: "窗口内样本不足（6 条 / 2 平台），不做跨平台结论"
  }},
  "/event/shanghai_luohu/propagation": { code: 200, data: {
    event_id: "shanghai_luohu", post_count: 22568, comment_count: 19765, comment_per_post: 0.88,
    best_lag_days: 0, best_lag_corr: 0.5287, peak_lag_days: 0,
    post_tau_days: 1.0, comment_tau_days: 0.75,
    series: { dates: ["2018-08-06","2018-08-07","2018-08-08"], post: [1200, 11995, 4000], comment: [800, 9000, 3000] }
  }}
};

const dom = new JSDOM(HTML, { runScripts: "outside-only", pretendToBeVisual: true });
const w = dom.window;

// 桩：Chart（jsdom 无 canvas）
w.Chart = class { constructor(){} destroy(){} };
// 桩：fetch
const BASE = "/api/v1/forecast";
w.fetch = async (url) => {
  const p = String(url).replace(BASE, "").split("?")[0];
  const fx = FIXTURES[p];
  if (!fx) return { ok: false, status: 404, json: async () => ({}) };
  return { ok: true, status: 200, json: async () => fx };
};
w.console = console;

(async () => {
  try {
    w.eval(JS);
  } catch (e) {
    console.log("  ✗ 脚本执行异常:", e.message);
    process.exit(1);
  }
  await new Promise((r) => setTimeout(r, 800));

  const doc = w.document;
  const q = (s) => doc.querySelector(s);
  const check = (label, ok, detail) => {
    console.log(`  ${ok ? "✓" : "✗"} ${label}${detail ? "  " + detail : ""}`);
    return ok;
  };

  let pass = 0, total = 0;
  const t = (l, ok, d) => { total++; if (check(l, ok, d)) pass++; };

  t("页面标题区", /事件热度预测/.test(doc.title));
  t("事件卡片已渲染", doc.querySelectorAll(".ev-card").length === 2, `实际 ${doc.querySelectorAll(".ev-card").length} 张`);
  t("卡片含事件名", /上海非沪籍/.test(doc.body.textContent));
  t("卡片含 τ", /τ 0\.75 天/.test(doc.body.textContent));
  t("状态栏就绪", /数据就绪/.test(doc.querySelector("#statusPill").textContent), doc.querySelector("#statusPill").textContent);
  t("指标卡有 6 项", doc.querySelectorAll("#kpi > div").length === 6, `实际 ${doc.querySelectorAll("#kpi > div").length}`);
  t("指标含半衰期", /半衰期/.test(doc.querySelector("#kpi").textContent));
  t("指标含回测误差", /回测误差/.test(doc.querySelector("#kpi").textContent));
  t("caveat 已填", doc.querySelector("#caveat").textContent.length > 10);
  t("跨平台表已渲染", doc.querySelectorAll("table.plat tr").length >= 2);
  t("跨平台标注样本不足", /样本不足/.test(doc.querySelector("#platBadge").textContent));
  t("传播指标卡 6 项", doc.querySelectorAll("#propKpi > div").length === 6);
  t("传播模式判定", /即时讨论型/.test(doc.querySelector("#propNote").textContent), doc.querySelector("#propNote").textContent.slice(0, 40));
  t("半衰期排行已渲染", doc.querySelector("#allTau").children.length >= 2);

  console.log(`\n  结果: ${pass}/${total} 通过`);
  process.exit(pass === total ? 0 : 1);
})();
