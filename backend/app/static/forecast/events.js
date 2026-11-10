/* 事件热度预测面板。
 *
 * 数据全部来自 /api/v1/forecast 下的三个端点：
 *   /events                    事件目录（6 个真实舆情事件）
 *   /event/<id>                指数衰减预测 + 真实值（回测）
 *   /event/<id>/platforms      跨平台画像（样本不足时明确标注）
 *
 * 展示原则：把「事后回测」与「事前可用」的误差分开写，不拿回测误差冒充预测精度。
 */
const API = "/api/v1/forecast";

const $ = (id) => document.getElementById(id);

let events = [];
let currentId = null;
let chart = null;

async function getJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = await res.json();
  return body && typeof body === "object" && "data" in body ? body.data : body;
}

const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("zh-CN", { maximumFractionDigits: 2 }));

function setStatus(text, kind) {
  const el = $("statusPill");
  el.textContent = text;
  el.style.color = kind === "err" ? "#e88" : kind === "ok" ? "#7fe0b8" : "";
}

/* ---------- 事件列表 ---------- */

function renderList() {
  const list = $("evList");
  list.innerHTML = "";
  $("evCount").textContent = `（${events.length}）`;

  for (const ev of events) {
    const card = document.createElement("div");
    card.className = "ev-card" + (ev.event_id === currentId ? " active" : "");
    card.dataset.id = ev.event_id;
    card.innerHTML = `
      <h3>${ev.name}</h3>
      <div class="sub">
        <span>${ev.start} ~ ${ev.end}</span>
        <span>峰值 ${fmt(ev.peak)}</span>
        <span class="tau">τ ${fmt(ev.tau_days)} 天</span>
      </div>`;
    card.addEventListener("click", () => select(ev.event_id));
    list.appendChild(card);
  }
}

/* ---------- 全部事件的半衰期对比 ---------- */

function renderAllTau() {
  const sorted = [...events].sort((a, b) => (a.half_life_days ?? 99) - (b.half_life_days ?? 99));
  const max = Math.max(...sorted.map((e) => e.half_life_days ?? 0), 0.1);
  const rows = sorted
    .map((e) => {
      const w = Math.max(2, ((e.half_life_days ?? 0) / max) * 100);
      return `<div style="font-size:11px;margin-bottom:7px">
        <div style="display:flex;justify-content:space-between;margin-bottom:2px">
          <span style="opacity:.8">${e.name.length > 12 ? e.name.slice(0, 12) + "…" : e.name}</span>
          <span style="color:#7fe0b8;font-variant-numeric:tabular-nums">${fmt(e.half_life_days)} 天</span>
        </div>
        <div style="height:4px;border-radius:2px;background:rgba(255,255,255,.07)">
          <div style="height:4px;border-radius:2px;background:rgba(127,224,184,.65);width:${w}%"></div>
        </div>
      </div>`;
    })
    .join("");
  $("allTau").innerHTML = rows + `<p class="note">半衰期 = τ·ln2，即热度衰减到峰值一半所需天数。数值越小，舆论凉得越快。</p>`;
}

/* ---------- 选中事件 ---------- */

async function select(id) {
  if (!id) return;
  currentId = id;
  document.querySelectorAll(".ev-card").forEach((c) => {
    c.classList.toggle("active", c.dataset.id === id);
  });
  setStatus("加载中…");

  try {
    const d = await getJSON(`${API}/event/${encodeURIComponent(id)}`);
    drawChart(d);
    renderKpi(d);

    const ev = events.find((e) => e.event_id === id);
    $("chartTitle").textContent = `${ev ? ev.name : id} · 爆发后衰减`;
    $("dirBadges").innerHTML = `<span class="badge">锚点 ${d.peak_day}</span>`;

    const p = await getJSON(`${API}/event/${encodeURIComponent(id)}/platforms`).catch(() => null);
    renderPlatforms(p);
    setStatus("数据就绪", "ok");
  } catch (err) {
    setStatus(`加载失败：${err.message}`, "err");
  }
}

/* ---------- 主图 ---------- */

function drawChart(d) {
  const hist = d.history || [];
  const pred = d.prediction || { dates: [], volume: [] };
  const actual = d.actual || { dates: [], volume: [] };

  const labels = [...hist.map((h) => h.date), ...(pred.dates || [])];
  const pad = hist.map(() => null);
  const histSeries = [...hist.map((h) => h.volume), ...(pred.dates || []).map(() => null)];
  const predSeries = [...pad, ...(pred.volume || [])];
  const actualSeries = [...pad, ...(actual.volume || [])];

  const ctx = $("chart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "历史声量",
          data: histSeries,
          borderColor: "rgba(160,180,220,.85)",
          backgroundColor: "rgba(160,180,220,.08)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25,
          fill: true,
        },
        {
          label: "预测（指数衰减）",
          data: predSeries,
          borderColor: "rgba(127,224,184,.95)",
          borderWidth: 2,
          borderDash: [5, 4],
          pointRadius: 0,
          tension: 0.25,
        },
        {
          label: "真实值",
          data: actualSeries,
          borderColor: "rgba(240,180,120,.9)",
          borderWidth: 1.6,
          pointRadius: 0,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "rgba(230,235,245,.8)", boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}` } },
      },
      scales: {
        x: {
          ticks: { color: "rgba(200,210,230,.5)", maxTicksLimit: 9, font: { size: 10 } },
          grid: { color: "rgba(255,255,255,.05)" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: "rgba(200,210,230,.5)", font: { size: 10 } },
          grid: { color: "rgba(255,255,255,.05)" },
        },
      },
    },
  });
}

/* ---------- 指标卡 ---------- */

function renderKpi(d) {
  const s = d.scores || {};
  const back = s.backtest_self_tau || {};
  const live = s.live_global_tau || {};
  const items = [
    ["τ（衰减常数）", `${fmt(d.prediction?.tau_days)} 天`],
    ["半衰期", `${fmt(d.half_life_days)} 天`],
    ["衰减到 1/10", `${fmt(d.decay_to_10pct_days)} 天`],
    ["峰值声量", fmt(d.peak_volume)],
    ["回测误差", fmt(back.rel_error)],
    ["全局τ基线误差", fmt(live.rel_error)],
  ];
  $("kpi").innerHTML = items
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join("");
  $("caveat").textContent =
    d.caveat ||
    "峰值前无法预测爆发幅度；本模型只描述爆发后的衰减形态。回测误差使用了该事件自身的衰减段拟合 τ，属乐观估计。";
}

/* ---------- 跨平台 ---------- */

function renderPlatforms(p) {
  if (!p) {
    $("platBadge").innerHTML = `<span class="badge warn">无数据</span>`;
    $("platBody").innerHTML = `<p class="note warn">该事件暂无跨平台画像。</p>`;
    return;
  }
  const adequate = Boolean(p.adequate);
  $("platBadge").innerHTML = adequate
    ? `<span class="badge ok">样本充分</span>`
    : `<span class="badge warn">样本不足</span>`;

  const head = `<tr><th>平台</th><th>条数</th><th>点赞</th><th>时间范围</th></tr>`;
  const rows = (p.platforms || [])
    .map(
      (x) =>
        `<tr><td>${x.platform}</td><td>${fmt(x.count)}</td><td>${fmt(x.like_sum)}</td><td style="opacity:.65">${x.start} ~ ${x.end}</td></tr>`,
    )
    .join("");

  $("platBody").innerHTML = `
    <table class="plat">${head}${rows || `<tr><td colspan="4" style="opacity:.5">无记录</td></tr>`}</table>
    <p class="note ${adequate ? "ok" : "warn"}">${p.verdict || ""}</p>`;
}

/* ---------- 启动 ---------- */

async function boot() {
  try {
    setStatus("加载事件…");
    const d = await getJSON(`${API}/events`);
    events = d.events || [];
    if (!events.length) throw new Error("事件列表为空");
    renderList();
    renderAllTau();
    await select(events[0].event_id);
  } catch (err) {
    setStatus(`初始化失败：${err.message}`, "err");
  }
}

boot();
