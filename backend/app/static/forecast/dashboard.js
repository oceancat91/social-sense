const API = "/api/v1/forecast";

const $ = (id) => document.getElementById(id);

let mainChart;
let compChart;

function badge(text, cls) {
  return `<span class="badge ${cls}">${text}</span>`;
}

function setStatus(ok, text) {
  const el = $("statusPill");
  el.className = `status ${ok ? "ok" : "bad"}`;
  el.textContent = text;
}

function renderMeta(model) {
  const rows = [
    ["checkpoint", model.path || model.checkpoint || "—"],
    ["domain", model.domain || "—"],
    ["seq / pred", `${model.seq_len} / ${model.pred_len}`],
    ["capacity", model.capacity || "—"],
    ["theta", model.theta ?? model.gate?.theta ?? "—"],
    ["C 通路", model.gate?.silent_C ? "off（MSE 门控）" : "on"],
  ];
  $("modelMeta").innerHTML = rows
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join("");
}

function renderEvents(events) {
  if (!events?.length) {
    $("events").innerHTML = `<div class="event"><div class="body">暂无异常事件</div></div>`;
    return;
  }
  $("events").innerHTML = events
    .map(
      (e) => `
    <div class="event">
      <div class="date">${e.date}</div>
      <div class="z">z=${Number(e.z_max).toFixed(1)}</div>
      <div class="body"><span class="trig">${e.trigger}</span>${escapeHtml(e.fact || "")}</div>
    </div>`
    )
    .join("");
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function buildCharts(data) {
  const hist = data.history;
  const pred = data.prediction;
  const labels = [...hist.dates, ...pred.dates];
  const histSeries = [...hist.ot, ...pred.dates.map(() => null)];
  const predSeries = [
    ...hist.ot.slice(0, -1).map(() => null),
    hist.ot[hist.ot.length - 1],
    ...pred.yhat_raw,
  ];

  const ctx = $("chart").getContext("2d");
  if (mainChart) mainChart.destroy();
  mainChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "历史 OT (log1p)",
          data: histSeries,
          borderColor: "#1a1f1c",
          backgroundColor: "rgba(26,31,28,0.05)",
          borderWidth: 1.8,
          pointRadius: 0,
          tension: 0.25,
          spanGaps: false,
        },
        {
          label: "预测 ŷ",
          data: predSeries,
          borderColor: "#0f6b5c",
          backgroundColor: "rgba(15,107,92,0.12)",
          borderWidth: 2.4,
          borderDash: [5, 4],
          pointRadius: 3,
          pointBackgroundColor: "#0f6b5c",
          tension: 0.2,
          spanGaps: false,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { boxWidth: 12, font: { family: "IBM Plex Sans" } } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${Number(c.raw).toFixed(3)}` } },
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 10, color: "#66706a", font: { size: 11 } },
          grid: { color: "rgba(26,31,28,0.06)" },
        },
        y: {
          ticks: { color: "#66706a" },
          grid: { color: "rgba(26,31,28,0.06)" },
        },
      },
    },
  });

  const comps = data.components || {};
  const keys = ["T", "S", "C", "R"].filter((k) => comps[k]);
  const predLen = pred.yhat_raw.length;
  const cctx = $("compChart").getContext("2d");
  if (compChart) compChart.destroy();
  const colors = { T: "#0f6b5c", S: "#2f5d8c", C: "#c45c26", R: "#66706a" };
  compChart = new Chart(cctx, {
    type: "bar",
    data: {
      labels: Array.from({ length: predLen }, (_, i) => `t+${i + 1}`),
      datasets: keys.map((k) => ({
        label: k,
        data: comps[k].map((v) => (Array.isArray(v) ? v[0] : v)),
        backgroundColor: colors[k],
        borderRadius: 4,
      })),
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10 } } },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, grid: { color: "rgba(26,31,28,0.06)" } },
      },
    },
  });
}

function renderPredictionBadges(pred) {
  const dir = pred.direction || "flat";
  const dirCls = dir === "up" ? "up" : dir === "down" ? "down" : "flat";
  const dirLabel =
    dir === "up" ? "方向：上涨" : dir === "down" ? "方向：回落" : "方向：持平";
  const bits = [
    badge(dirLabel, dirCls),
    badge(`Δ=${Number(pred.direction_delta).toFixed(3)}`, "flat"),
  ];
  if (pred.spike_warning) bits.push(badge("尖峰预警", "warn"));
  $("dirBadges").innerHTML = bits.join("");
}

async function loadDashboard() {
  setStatus(false, "拉取中…");
  try {
    const res = await fetch(`${API}/dashboard-data?hist=90`);
    const payload = await res.json();
    if (!res.ok || payload.code !== 200) {
      throw new Error(payload.message || `HTTP ${res.status}`);
    }
    const data = payload.data;
    renderMeta(data.model || {});
    renderPredictionBadges(data.prediction);
    buildCharts(data);
    renderEvents(data.anomalies);
    $("report").innerHTML = marked.parse(data.report_md || "_暂无报告_");
    const ck = (data.model && (data.model.path || "")).split(/[/\\]/).pop() || "ready";
    setStatus(true, `模型已接入 · ${ck}`);
  } catch (err) {
    console.error(err);
    setStatus(false, String(err.message || err));
    $("report").innerHTML = `<p>加载失败：${escapeHtml(err.message || err)}</p>`;
  }
}

$("reloadBtn").addEventListener("click", loadDashboard);
loadDashboard();
