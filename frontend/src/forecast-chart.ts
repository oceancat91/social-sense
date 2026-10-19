import type { ForecastDashboard } from "./forecast-api";

const format = (value: number) =>
  value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });

/** A finite draw-on pass; the chart is idle once revealed, unless inspected or resized. */
export class ForecastChart {
  private dashboard?: ForecastDashboard;
  private frame = 0;
  private start = 0;
  private duration = 0;
  private cursor: number | null = null;
  private resize: ResizeObserver;
  private theme: MutationObserver;
  private visibility: IntersectionObserver;
  private visible = false;
  private pendingReveal = false;

  constructor(
    private canvas: HTMLCanvasElement,
    private readout: HTMLElement,
    private animated: () => boolean,
  ) {
    this.resize = new ResizeObserver(() => this.requestPaint());
    this.resize.observe(canvas);
    this.theme = new MutationObserver(() => this.requestPaint());
    this.theme.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style"],
    });
    this.visibility = new IntersectionObserver(
      ([entry]) => {
        this.visible = entry.isIntersecting;
        if (this.visible && this.pendingReveal) {
          this.start = performance.now();
          this.pendingReveal = false;
        }
        if (this.visible) this.requestPaint();
      },
      { threshold: 0.1 },
    );
    this.visibility.observe(canvas);
    canvas.addEventListener("pointermove", this.onPointer);
    canvas.addEventListener("pointerleave", this.onLeave);
    canvas.addEventListener("focus", this.onFocus);
    canvas.addEventListener("blur", this.onLeave);
    canvas.addEventListener("keydown", this.onKey);
  }

  update(dashboard: ForecastDashboard) {
    this.dashboard = dashboard;
    this.cursor = null;
    this.start = performance.now();
    this.duration = this.animated() ? 1250 : 0;
    this.pendingReveal = !this.visible;
    this.canvas.tabIndex =
      dashboard.ot.length + dashboard.prediction.length ? 0 : -1;
    this.canvas.setAttribute(
      "aria-label",
      `热度曲线，${dashboard.ot.length} 个历史观测，${dashboard.prediction.length} 个预测值。左右方向键查看每日热度。`,
    );
    this.updateReadout();
    this.requestPaint();
  }

  private requestPaint() {
    if (!this.frame) this.frame = requestAnimationFrame(this.paint);
  }

  private updateReadout() {
    const data = this.dashboard;
    if (!data || this.cursor === null) {
      this.readout.textContent = "移动至曲线查看热度 · 键盘 ← → 逐日查看";
      return;
    }
    const predicted = this.cursor >= data.ot.length;
    const index = predicted ? this.cursor - data.ot.length : this.cursor;
    const date =
      (predicted ? data.predictionDates : data.dates)[index] ?? "日期未提供";
    const value = (predicted ? data.prediction : data.ot)[index];
    this.readout.textContent = `${date} / ${predicted ? "预测" : "历史"} / OT ${format(value)}`;
  }

  private onPointer = (event: PointerEvent) => {
    const count =
      (this.dashboard?.ot.length ?? 0) +
      (this.dashboard?.prediction.length ?? 0);
    if (!count) return;
    const bounds = this.canvas.getBoundingClientRect();
    const x =
      ((event.clientX - bounds.left) * this.canvas.clientWidth) / bounds.width;
    this.cursor = Math.round(
      Math.max(
        0,
        Math.min(1, (x - 54) / Math.max(1, this.canvas.clientWidth - 72)),
      ) *
        (count - 1),
    );
    this.updateReadout();
    this.requestPaint();
  };

  private onFocus = () => {
    if (
      !this.dashboard ||
      (!this.dashboard.ot.length && !this.dashboard.prediction.length)
    )
      return;
    this.cursor = Math.max(0, this.dashboard.ot.length - 1);
    this.updateReadout();
    this.requestPaint();
  };

  private onLeave = () => {
    if (document.activeElement === this.canvas) return;
    this.cursor = null;
    this.updateReadout();
    this.requestPaint();
  };

  private onKey = (event: KeyboardEvent) => {
    const count =
      (this.dashboard?.ot.length ?? 0) +
      (this.dashboard?.prediction.length ?? 0);
    if (
      !count ||
      !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
    )
      return;
    event.preventDefault();
    this.cursor =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? count - 1
          : Math.max(
              0,
              Math.min(
                count - 1,
                (this.cursor ?? 0) + (event.key === "ArrowRight" ? 1 : -1),
              ),
            );
    this.updateReadout();
    this.requestPaint();
  };

  private paint = (time: number) => {
    this.frame = 0;
    if (!this.canvas.isConnected || !this.visible) return;
    const raw =
      this.duration && this.animated()
        ? Math.min(1, (time - this.start) / this.duration)
        : 1;
    const progress = 1 - Math.pow(1 - raw, 3);
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const pixelWidth = Math.round(width * dpr),
      pixelHeight = Math.round(height * dpr);
    if (
      this.canvas.width !== pixelWidth ||
      this.canvas.height !== pixelHeight
    ) {
      this.canvas.width = pixelWidth;
      this.canvas.height = pixelHeight;
    }
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const data = this.dashboard;
    if (!data) return;
    const values = [...data.ot, ...data.prediction];
    if (!values.length) return;

    const left = 54,
      top = 24,
      plotW = Math.max(1, width - 72),
      plotH = Math.max(1, height - 52);
    const low = Math.min(...values),
      high = Math.max(...values);
    const extra = (high - low || Math.max(Math.abs(high), 1)) * 0.14;
    const min = low - extra,
      max = high + extra;
    const xAt = (index: number) =>
      left + (plotW * index) / Math.max(1, values.length - 1);
    const yAt = (value: number) =>
      top + plotH * (1 - (value - min) / (max - min));
    const styles = getComputedStyle(this.canvas);
    const color = (name: string) =>
      styles.getPropertyValue(`--forecast-${name}`).trim();
    const ink = color("ink"),
      accent = color("accent"),
      grid = color("border"),
      muted = color("muted");

    ctx.font = '11px "MiSans", sans-serif';
    ctx.lineWidth = 1;
    ctx.strokeStyle = grid;
    ctx.fillStyle = muted;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 3; i++) {
      const y = top + (plotH * i) / 3;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(left + plotW, y);
      ctx.stroke();
      const tick = max - ((max - min) * i) / 3;
      const label =
        Math.abs(tick) >= 10000
          ? `${(tick / 10000).toFixed(1)}万`
          : format(tick);
      ctx.fillText(label, left - 10, y, 44);
    }
    const boundary = xAt(Math.max(0, data.ot.length - 1));
    if (data.prediction.length) {
      ctx.save();
      ctx.fillStyle = accent;
      ctx.globalAlpha = 0.055;
      ctx.fillRect(boundary, top, left + plotW - boundary, plotH);
      ctx.globalAlpha = 0.45;
      ctx.strokeStyle = accent;
      ctx.setLineDash([2, 5]);
      ctx.beginPath();
      ctx.moveTo(boundary, top);
      ctx.lineTo(boundary, top + plotH);
      ctx.stroke();
      ctx.restore();
      ctx.fillStyle = accent;
      ctx.textAlign = boundary > left + plotW - 100 ? "right" : "left";
      ctx.fillText(
        "预测区间",
        boundary > left + plotW - 100 ? left + plotW : boundary + 8,
        10,
      );
    }

    // Reveal the same path geometry, retaining every observed value and sharp peak.
    ctx.save();
    ctx.beginPath();
    ctx.rect(left - 5, 0, (plotW + 10) * progress, height);
    ctx.clip();
    const drawLine = (
      series: number[],
      offset: number,
      stroke: string,
      dashed: boolean,
    ) => {
      if (!series.length) return;
      ctx.beginPath();
      series.forEach((value, index) =>
        index
          ? ctx.lineTo(xAt(index + offset), yAt(value))
          : ctx.moveTo(xAt(offset), yAt(value)),
      );
      ctx.strokeStyle = stroke;
      ctx.lineWidth = dashed ? 2 : 1.8;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.setLineDash(dashed ? [5, 5] : []);
      ctx.stroke();
      ctx.setLineDash([]);
      if (dashed || series.length === 1)
        series.forEach((value, index) => {
          ctx.beginPath();
          ctx.arc(xAt(index + offset), yAt(value), 2.6, 0, Math.PI * 2);
          ctx.fillStyle = stroke;
          ctx.fill();
        });
    };
    drawLine(data.ot, 0, ink, false);
    if (data.prediction.length)
      drawLine(
        data.ot.length
          ? [data.ot[data.ot.length - 1], ...data.prediction]
          : data.prediction,
        Math.max(0, data.ot.length - 1),
        accent,
        true,
      );
    ctx.restore();

    const first = data.dates[0] ?? data.predictionDates[0] ?? "";
    const last =
      data.predictionDates[data.predictionDates.length - 1] ??
      data.dates[data.dates.length - 1] ??
      "";
    ctx.fillStyle = muted;
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    ctx.fillText(first, left, top + plotH + 12);
    ctx.textAlign = "right";
    ctx.fillText(last, left + plotW, top + plotH + 12);
    if (this.cursor !== null && this.cursor < values.length) {
      const x = xAt(this.cursor),
        y = yAt(values[this.cursor]);
      ctx.strokeStyle = accent;
      ctx.globalAlpha = 0.4;
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + plotH);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 0.12;
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    if (raw < 1) this.requestPaint();
  };

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.theme.disconnect();
    this.visibility.disconnect();
    this.canvas.removeEventListener("pointermove", this.onPointer);
    this.canvas.removeEventListener("pointerleave", this.onLeave);
    this.canvas.removeEventListener("focus", this.onFocus);
    this.canvas.removeEventListener("blur", this.onLeave);
    this.canvas.removeEventListener("keydown", this.onKey);
  }
}
