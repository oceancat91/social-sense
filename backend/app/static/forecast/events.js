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
  el.style.color = kind === "err" ? "#b86110" : kind === "ok" ? "#a67d48" : "";
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
        <span class="tau">τ ${fmt(ev.tau_days)} 天</span>${ev.synthetic ? '<span style="color:#b86110">合成</span>' : ""}
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
      return `<div class="tau-row">
        <div class="row-head">
          <span class="row-name">${e.name.length > 12 ? e.name.slice(0, 12) + "…" : e.name}</span>
          <span class="row-val">${fmt(e.half_life_days)} 天</span>
        </div>
        <div class="tau-bar"><i style="width:${w}%"></i></div>
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

    const comp = await getJSON(`${API}/event/${encodeURIComponent(id)}/components`).catch(() => null);
    renderComponents(comp);

    const prop = await getJSON(`${API}/event/${encodeURIComponent(id)}/propagation`).catch(() => null);
    renderPropagation(prop, ev ? { start: ev.start, end: ev.end } : null);
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
          borderColor: "rgba(8,10,8,.55)",
          backgroundColor: "rgba(8,10,8,.05)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25,
          fill: true,
        },
        {
          label: "预测（指数衰减）",
          data: predSeries,
          borderColor: "#a67d48",
          borderWidth: 2,
          borderDash: [5, 4],
          pointRadius: 0,
          tension: 0.25,
        },
        {
          label: "真实值",
          data: actualSeries,
          borderColor: "#ed821b",
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
        legend: { labels: { color: "rgba(8,10,8,.7)", boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}` } },
      },
      scales: {
        x: {
          ticks: { color: "rgba(8,10,8,.45)", maxTicksLimit: 9, font: { size: 10 } },
          grid: { color: "rgba(8,10,8,.08)" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: "rgba(8,10,8,.45)", font: { size: 10 } },
          grid: { color: "rgba(8,10,8,.08)" },
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


/* ---------- 传播时序 ---------- */

let propChartRef = null;

function renderPropagation(d, eventWindow) {
  const badge = $("propBadge");
  const kpi = $("propKpi");
  const note = $("propNote");

  if (!d) {
    badge.innerHTML = `<span class="badge warn">无数据</span>`;
    $("propChart").style.display = "none";
    kpi.innerHTML = "";
    note.textContent = "该事件没有「博文 + 评论」成对数据，无法做传播时序分析。不做外推。";
    note.className = "note warn";
    return;
  }

  $("propChart").style.display = "";
  badge.innerHTML = `<span class="badge ok">${d.post_count.toLocaleString()} 博文 / ${d.comment_count.toLocaleString()} 评论</span>`;

  // 只画事件窗口附近，避免 1794 天的长尾把图压扁
  let dates = d.series.dates;
  let post = d.series.post;
  let cmt = d.series.comment;
  if (eventWindow && eventWindow.start && eventWindow.end) {
    const from = dates.indexOf(eventWindow.start);
    const to = dates.indexOf(eventWindow.end);
    if (from >= 0 && to > from) {
      const a = Math.max(0, from - 7);
      const b = Math.min(dates.length, to + 8);
      dates = dates.slice(a, b);
      post = post.slice(a, b);
      cmt = cmt.slice(a, b);
    }
  }

  const ctx = $("propChart").getContext("2d");
  if (propChartRef) propChartRef.destroy();
  propChartRef = new Chart(ctx, {
    type: "line",
    data: {
      labels: dates,
      datasets: [
        {
          label: "博文",
          data: post,
          borderColor: "rgba(8,10,8,.6)",
          backgroundColor: "rgba(8,10,8,.05)",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.25,
          fill: true,
          yAxisID: "y",
        },
        {
          label: "评论",
          data: cmt,
          borderColor: "#ed821b",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.25,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "rgba(8,10,8,.7)", boxWidth: 12, font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: "rgba(8,10,8,.45)", maxTicksLimit: 8, font: { size: 10 } }, grid: { color: "rgba(255,255,255,.05)" } },
        y: { position: "left", beginAtZero: true, ticks: { color: "rgba(8,10,8,.5)", font: { size: 10 } }, grid: { color: "rgba(255,255,255,.05)" } },
        y1: { position: "right", beginAtZero: true, ticks: { color: "#b86110", font: { size: 10 } }, grid: { drawOnChartArea: false } },
      },
    },
  });

  const items = [
    ["最佳滞后", `${d.best_lag_days} 天`],
    ["滞后相关性", fmt(d.best_lag_corr)],
    ["峰值差", `${d.peak_lag_days} 天`],
    ["评论:博文", fmt(d.comment_per_post)],
    ["博文 τ", `${fmt(d.post_tau_days)} 天`],
    ["评论 τ", `${fmt(d.comment_tau_days)} 天`],
  ];
  kpi.innerHTML = items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");

  const type =
    d.best_lag_days === 0 && d.comment_per_post >= 0.5
      ? "即时讨论型：评论紧跟博文，同一天到峰"
      : "延迟聚集型：博文先发酵，评论数天后才跟上";
  note.className = "note ok";
  note.textContent = `${type}。仅同时具备博文与评论的事件可做此项分析。`;
}


/* ---------- 模型四分量 ---------- */

let compChartRef = null;

function renderComponents(d) {
  const badge = $("compBadge");
  const kpi = $("compKpi");
  const note = $("compNote");

  if (!d || !d.components) {
    badge.innerHTML = `<span class="badge warn">无数据</span>`;
    $("compChart").style.display = "none";
    kpi.innerHTML = "";
    note.textContent = "该事件没有模型分量数据。";
    note.className = "note warn";
    return;
  }

  $("compChart").style.display = "";
  badge.innerHTML = `<span class="badge">${d.model?.name || "RepMoE"}</span>`;

  const keys = ["T", "S", "C", "R"];
  const colors = {
    T: "#080a08",
    S: "#a67d48",
    C: "#ed821b",
    R: "#8b93a1",
  };
  const labels = { T: "T̂ 趋势", S: "Ŝ 季节", C: "Ĉ 冲击", R: "R̂ 残差" };
  const datasets = keys
    .filter((k) => Array.isArray(d.components[k]) && d.components[k].length)
    .map((k) => ({
      label: labels[k],
      data: d.components[k],
      borderColor: colors[k],
      borderWidth: k === "C" ? 2.2 : 1.6,
      pointRadius: 0,
      tension: 0.25,
      borderDash: k === "C" ? [6, 3] : undefined,
    }));

  const ctx = $("compChart").getContext("2d");
  if (compChartRef) compChartRef.destroy();
  compChartRef = new Chart(ctx, {
    type: "line",
    data: { labels: datasets[0]?.data.map((_, i) => `+${i + 1}`) || [], datasets },
    options: {
      responsive: true,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "rgba(8,10,8,.7)", boxWidth: 12, font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { color: "rgba(8,10,8,.45)", font: { size: 10 } }, grid: { color: "rgba(8,10,8,.06)" } },
        y: { ticks: { color: "rgba(8,10,8,.45)", font: { size: 10 } }, grid: { color: "rgba(8,10,8,.08)" } },
      },
    },
  });

  const items = [
    ["模型", d.model?.name || "RepMoE"],
    ["方向 Δ", fmt(d.direction_delta)],
    ["尖峰增益", fmt(d.spike_gain)],
    ["触发度", fmt(d.fire)],
    ["窗口起点", d.window_dates?.[0] || "—"],
    ["窗口长度", `${d.window_volume?.length || 0} 天`],
  ];
  kpi.innerHTML = items.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
  note.className = "note";
  note.textContent =
    d.caveat || "四分量表示模型如何分解这段曲线（标准化空间），属定性解释。";
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
