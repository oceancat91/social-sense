"use client";

import { motion, useReducedMotion } from "motion/react";
import SplitText from "@/components/SplitText";
import BrandMark from "@/components/BrandMark";
import SignalChart from "@/components/SignalChart";
import {
  GlobeHemisphereWest,
  FunnelSimple,
  ChartBar,
  ArrowsLeftRight,
  SealCheck,
  ArrowsMerge,
  ChartPieSlice,
  Gauge,
  SuitcaseSimple,
  Lightbulb,
  ChartLineUp,
  Megaphone,
  Database,
  ArrowRight,
  ArrowUpRight,
  Check,
  CaretDown,
} from "@phosphor-icons/react/dist/ssr";

const PRODUCT_URL = "https://socialsense.cn/app/";

const PLATFORMS = ["微博", "抖音", "B站", "小红书", "知乎", "快手"];

const SIGNALS = [
  "时间对齐的声量与情绪曲线",
  "支持 / 反对 / 中立立场分布",
  "跨平台声量共振与分歧",
  "回声室指数与校准门禁",
];

const PIPELINE = [
  {
    icon: GlobeHemisphereWest,
    title: "采集",
    desc: "接入微博、抖音、B站、小红书、知乎、快手等平台公开讨论，统一字段口径。",
  },
  {
    icon: FunnelSimple,
    title: "清洗",
    desc: "去除重复与机器噪声，保留可进入分析的实质讨论文本。",
  },
  {
    icon: ChartBar,
    title: "画像",
    desc: "在平台内标注情绪倾向与支持 / 反对立场，叠加领域词表增强。",
  },
  {
    icon: ArrowsLeftRight,
    title: "对齐",
    desc: "将各平台时间序列对齐到统一时间轴，并按平台内 z-score 去量纲。",
  },
  {
    icon: SealCheck,
    title: "校准",
    desc: "跨平台融合后经 CX1-CX5 门禁校验，无证据不推断。",
  },
];

/* 真实话题洞察：来自 real_multiplatform 数据集的 12 个领域热点 */
const TOPICS = [
  "国潮与传统文化复兴",
  "房价下跌与楼市",
  "学历贬值与就业难",
  "AI艺人与活人感之争",
  "AI漫剧爆发",
  "青少年心理健康",
  "消费降级与反向消费",
  "极端天气与气候",
  "中美关税战",
  "戒网瘾双胞胎事件",
  "2026美加墨世界杯",
  "人形机器人商业化",
];

/* 真实样本指标：时序点数 / 声量共振 / 回声室指数 */
const INSIGHTS = [
  { topic: "AI艺人与活人感之争", points: "3298", resonance: "0.24", echo: "0.28" },
  { topic: "人形机器人商业化", points: "3183", resonance: "0.21", echo: "0.26" },
  { topic: "消费降级与反向消费", points: "2923", resonance: "0.13", echo: "0.29" },
  { topic: "国潮与传统文化复兴", points: "2866", resonance: "0.05", echo: "0.32" },
];

/* CX1-CX5 校准门禁（与 multiagent/master.py 保持一致） */
const GATES = [
  { id: "CX1", name: "平台覆盖", desc: "至少两个平台参与，单平台自动降级为单平台结论。" },
  { id: "CX2", name: "分歧诚实", desc: "不得夸大或漏报茧房，强断言须与指标读数一致。" },
  { id: "CX3", name: "禁跨平台幻觉", desc: "结论引用的平台必须真实存在于报告集合内。" },
  { id: "CX4", name: "证据可溯源", desc: "每条跨平台断言至少绑定一个平台的证据。" },
  { id: "CX5", name: "空窗诚实", desc: "全平台无观测时，不得输出任何强结论。" },
];

const FAQS = [
  {
    q: "覆盖哪些平台？",
    a: "接入微博、抖音、B站、小红书、知乎、快手的公开讨论，统一字段口径后进入分析管线。",
  },
  {
    q: "不同平台的数据如何比较？",
    a: "各平台量纲不同，统一采用平台内 z-score 归一后对齐到同一时间轴，跨平台才真正可比。",
  },
  {
    q: "结论是否可信？",
    a: "每条跨平台结论须通过 CX1-CX5 校准门禁，无证据不推断，缺失时间窗如实留空，不做插值。",
  },
  {
    q: "覆盖哪些领域？",
    a: "十二个领域热点：文化历史、财经商业、教育科研、影视娱乐、游戏动漫、医疗健康、生活消费、自然环境、时政、社会事件、体育竞技、科技工业。",
  },
];

const NAV = [
  { href: "#method", label: "处理管线" },
  { href: "#capabilities", label: "能力" },
  { href: "#insights", label: "真实洞察" },
  { href: "#roles", label: "适用角色" },
  { href: "#faq", label: "常见问题" },
];

export default function Page() {
  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-page font-sans text-txt antialiased">
      <Header />
      <main className="w-full max-w-full">
        <Hero />
        <PlatformStrip />
        <Method />
        <Capabilities />
        <Insights />
        <Roles />
        <Caliber />
        <Faq />
        <Closing />
      </main>
      <Footer />
    </div>
  );
}

/* ---------- 通用滚动揭示 ---------- */

function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 20 }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay }}
    >
      {children}
    </motion.div>
  );
}

/* ---------- 统一主 CTA ---------- */

const CTA_CLASS =
  "inline-flex items-center gap-2 rounded-md bg-accent px-5 py-3 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.98]";

/* ---------- S1 顶栏 ---------- */

function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-page/85 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-6">
        <a href="#top" className="flex items-center gap-2.5">
          <span className="grid size-7 place-items-center rounded-md bg-solid text-on-solid">
            <BrandMark size={17} />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">
            Social Sense
          </span>
        </a>
        <nav className="hidden items-center gap-6 text-sm text-txt2 lg:flex">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="transition-colors hover:text-txt"
            >
              {item.label}
            </a>
          ))}
        </nav>
        <a href={PRODUCT_URL} className={CTA_CLASS}>
          进入分析台
          <ArrowUpRight size={15} weight="bold" />
        </a>
      </div>
    </header>
  );
}

/* ---------- S2 Hero ---------- */

function Hero() {
  return (
    <section id="top">
      <div className="mx-auto grid w-full max-w-7xl gap-14 px-6 pb-20 pt-16 md:pt-20 lg:grid-cols-[1.02fr_0.98fr] lg:items-center lg:gap-20 lg:pt-24">
        <div>
          <h1 className="text-4xl font-semibold leading-[1.14] tracking-tight text-txt md:text-[54px] lg:text-[60px]">
            <SplitText
              tag="span"
              block
              textAlign="left"
              text="把跨平台舆情，"
              delay={45}
              duration={1}
              from={{ opacity: 0, y: 16 }}
              to={{ opacity: 1, y: 0 }}
              ease="power3.out"
              className="text-txt"
            />
            <SplitText
              tag="span"
              block
              textAlign="left"
              text="读成可决策的信号"
              delay={45}
              duration={1}
              from={{ opacity: 0, y: 16, delay: 0.2 }}
              to={{ opacity: 1, y: 0, delay: 0.2 }}
              ease="power3.out"
              className="text-txt"
            />
          </h1>
          <Reveal delay={0.5}>
            <p className="mt-6 max-w-[46ch] text-lg leading-relaxed text-txt2">
              六平台实时采集，统一口径与时间轴，量化情绪分歧与回声室，把噪音收敛成决策信号。
            </p>
          </Reveal>
          <Reveal delay={0.6}>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <a href={PRODUCT_URL} className={CTA_CLASS}>
                进入分析台
                <ArrowRight size={16} weight="bold" />
              </a>
              <a
                href="#capabilities"
                className="inline-flex items-center gap-2 rounded-md border border-line2 px-5 py-3 text-sm font-semibold text-txt2 transition-colors hover:border-txt3 hover:text-txt"
              >
                查看能力
              </a>
            </div>
          </Reveal>
        </div>

        {/* 真实能力模块预览 */}
        <Reveal delay={0.45}>
          <div className="rounded-xl border border-line bg-card p-7 shadow-card">
            <div className="flex items-center justify-between border-b border-line pb-4">
              <p className="text-sm font-semibold">平台覆盖</p>
              <span className="font-mono text-xs text-txt3">
                {PLATFORMS.length} platforms
              </span>
            </div>
            <div className="flex flex-wrap gap-2 py-5">
              {PLATFORMS.map((p) => (
                <span
                  key={p}
                  className="inline-flex items-center gap-1.5 rounded-md bg-card2 px-2.5 py-1.5 text-sm text-txt"
                >
                  <Check size={13} weight="bold" className="text-accent" />
                  {p}
                </span>
              ))}
            </div>
            <div className="border-t border-line pt-5">
              <p className="mb-3 text-xs font-medium text-txt3">可产出信号</p>
              <ul className="space-y-2.5">
                {SIGNALS.map((s) => (
                  <li key={s} className="flex items-center gap-2.5 text-sm text-txt2">
                    <Check size={14} weight="bold" className="text-accent" />
                    {s}
                  </li>
                ))}
              </ul>
            </div>
            <p className="mt-5 border-t border-line pt-4 text-xs leading-relaxed text-txt3">
              口径：平台内 z-score 归一后跨平台可比，缺失窗口如实留空，不做插值。
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ---------- S3 平台数据源 ---------- */

function PlatformStrip() {
  const items = [...PLATFORMS, ...PLATFORMS];
  return (
    <section aria-label="接入平台" className="border-y border-line bg-card">
      <div className="mx-auto flex w-full max-w-7xl items-center gap-6 px-6 py-5">
        <span className="shrink-0 text-xs font-medium uppercase tracking-[0.16em] text-txt3">
          接入平台
        </span>
        <div className="relative flex-1 overflow-hidden">
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-12 bg-gradient-to-r from-card to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-12 bg-gradient-to-l from-card to-transparent" />
          <div className="marquee-track flex w-max items-center gap-10">
            {items.map((p, i) => (
              <span
                key={`${p}-${i}`}
                className="flex items-center gap-10 whitespace-nowrap text-sm font-medium text-txt2"
              >
                {p}
                <span className="text-txt3/50">/</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------- S4 处理管线 ---------- */

function Method() {
  return (
    <section id="method" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
      <div className="max-w-2xl">
        <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
          从原始评论到可信结论
        </h2>
        <p className="mt-4 text-txt2">
          五段管线贯穿采集到校准，每一步都产出可检查的中间结果。
        </p>
      </div>
      <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE.map((item, i) => (
          <Reveal key={item.title} delay={i * 0.05}>
            <div className="h-full rounded-xl border border-line bg-card p-6 transition-colors hover:border-line2">
              <span className="inline-flex size-10 items-center justify-center rounded-md border border-line text-accent">
                <item.icon size={19} weight="bold" />
              </span>
              <h3 className="mt-5 text-[15px] font-semibold">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-txt2">
                {item.desc}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ---------- S5 能力 bento ---------- */

function Capabilities() {
  return (
    <section
      id="capabilities"
      className="border-y border-line bg-card"
    >
      <div className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            三种信号，支撑一种判断
          </h2>
          <p className="mt-4 text-txt2">
            对齐、画像与回声室测算互相咬合，共同约束结论不能脱离数据。
          </p>
        </div>

        <div className="mt-14 grid gap-4 lg:grid-cols-2">
          <Reveal className="lg:row-span-2">
            <div className="flex h-full flex-col justify-between rounded-xl bg-feature p-8 text-on-feature lg:p-10">
              <div>
                <span className="inline-flex size-11 items-center justify-center rounded-md bg-accent text-on-accent">
                  <ArrowsMerge size={22} weight="bold" />
                </span>
                <h3 className="mt-7 text-2xl font-semibold tracking-tight">
                  跨平台对齐与共振
                </h3>
                <p className="mt-4 max-w-[40ch] leading-relaxed text-feature-mut">
                  不同平台量纲不可直接相加。按平台内 z-score 归一后对齐到统一时间轴，声量与情绪才真正可比。共振与错峰，一眼可辨。
                </p>
              </div>
              <ul className="mt-10 space-y-3 text-sm text-on-feature/85">
                <li className="flex items-center gap-2.5">
                  <Check size={15} weight="bold" className="text-accent" />
                  声量共振与错峰
                </li>
                <li className="flex items-center gap-2.5">
                  <Check size={15} weight="bold" className="text-accent" />
                  缺失窗口如实留空
                </li>
                <li className="flex items-center gap-2.5">
                  <Check size={15} weight="bold" className="text-accent" />
                  平台内归一，跨平台可比
                </li>
              </ul>
            </div>
          </Reveal>

          <Reveal>
            <div className="h-full rounded-xl border border-line bg-page p-8">
              <span className="inline-flex size-11 items-center justify-center rounded-md border border-line text-accent">
                <ChartPieSlice size={22} weight="bold" />
              </span>
              <h3 className="mt-6 text-lg font-semibold tracking-tight">
                立场与情绪画像
              </h3>
              <p className="mt-3 leading-relaxed text-txt2">
                对每条讨论做情绪倾向与支持 / 反对 / 中立标注，输出每平台结构化画像。
              </p>
              <p className="mt-6 text-sm text-txt3">
                叠加领域词表与知识增强，口径透明可复算。
              </p>
            </div>
          </Reveal>

          <Reveal>
            <div className="h-full rounded-xl bg-accent-tint p-8 ring-1 ring-inset ring-accent-line">
              <span className="inline-flex size-11 items-center justify-center rounded-md bg-accent text-on-accent">
                <Gauge size={22} weight="bold" />
              </span>
              <h3 className="mt-6 text-lg font-semibold tracking-tight">
                回声室指数
              </h3>
              <p className="mt-3 leading-relaxed text-txt">
                综合立场分歧、情绪分歧与声量失振，输出跨平台量化指数，直接衡量信息茧房强度。
              </p>
              <p className="mt-6 text-sm text-txt2">
                融合结论需通过 CX1-CX5 校准门禁。
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ---------- S6 真实话题洞察 ---------- */

function Insights() {
  return (
    <section id="insights" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-32">
      <div className="max-w-2xl">
        <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
          真实话题，实时洞察
        </h2>
        <p className="mt-4 text-txt2">
          从十二个领域热点出发，观察跨平台声量与情绪如何共振或错峰。指标来自真实话题样本。
        </p>
      </div>

      {/* 声量共振可视化 */}
      <Reveal>
        <div className="mt-14 rounded-xl bg-feature p-8 text-on-feature lg:p-10">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-6">
            <p className="text-sm font-semibold">声量共振与错峰</p>
            <span className="font-mono text-xs text-feature-mut">
              z-score 归一 / 时间对齐
            </span>
          </div>
          <div className="mt-6 grid items-center gap-8 lg:grid-cols-[1.35fr_1fr]">
            <SignalChart className="w-full" />
            <div>
              <p className="text-lg font-semibold leading-snug">
                同一话题，各平台的讨论节奏并不相同。
              </p>
              <p className="mt-4 leading-relaxed text-feature-mut">
                B站与微博的声量在此处同步抬升，抖音则明显错峰。真实样本显示，跨平台声量以错峰为主，只看单一平台，很难还原事件全貌。
              </p>
              <ul className="mt-6 space-y-2.5 text-sm text-on-feature/85">
                {[
                  ["B站", "#3b82f6"],
                  ["微博", "#9aa7b8"],
                  ["抖音", "#6b7a90"],
                  ["小红书", "#cbd5e1"],
                ].map(([name, color]) => (
                  <li key={name} className="flex items-center gap-2.5">
                    <span
                      className="inline-block h-1 w-5 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    {name}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Reveal>

      {/* 真实样本指标 */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {INSIGHTS.map((item, i) => (
          <Reveal key={item.topic} delay={i * 0.05}>
            <div className="h-full rounded-xl border border-line bg-card p-6">
              <h3 className="text-[15px] font-semibold leading-snug">
                {item.topic}
              </h3>
              <div className="mt-5 grid grid-cols-3 gap-3">
                <div>
                  <p className="font-mono text-lg font-medium text-txt">
                    {item.points}
                  </p>
                  <p className="mt-1 text-xs text-txt3">时序点</p>
                </div>
                <div>
                  <p className="font-mono text-lg font-medium text-txt">
                    {item.resonance}
                  </p>
                  <p className="mt-1 text-xs text-txt3">声量共振</p>
                </div>
                <div>
                  <p className="font-mono text-lg font-medium text-txt">
                    {item.echo}
                  </p>
                  <p className="mt-1 text-xs text-txt3">回声室</p>
                </div>
              </div>
            </div>
          </Reveal>
        ))}
      </div>

      {/* 话题标签 */}
      <Reveal>
        <div className="mt-8 flex flex-wrap gap-2">
          {TOPICS.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1.5 rounded-md bg-card2 px-3 py-1.5 text-sm text-txt2 transition-colors hover:text-txt"
            >
              {t}
            </span>
          ))}
        </div>
      </Reveal>
    </section>
  );
}

/* ---------- S7 适用角色 ---------- */

function Roles() {
  return (
    <section id="roles" className="border-y border-line bg-card">
      <div className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            为决策者而做
          </h2>
          <p className="mt-4 text-txt2">
            不是多一块看板，而是把社交数据翻译成各岗位能直接使用的语言。
          </p>
        </div>
        <div className="mt-14 grid gap-4 md:grid-cols-2">
          {[
            {
              icon: SuitcaseSimple,
              title: "社区运营",
              desc: "定位危机拐点与观点分化平台，处理时机更早。",
            },
            {
              icon: Lightbulb,
              title: "产品经理",
              desc: "把跨平台需求声量对齐，识别被忽略的真实呼声。",
            },
            {
              icon: ChartLineUp,
              title: "数据与增长分析师",
              desc: "口径一致的时间序列，可直接用于复算与建模。",
            },
            {
              icon: Megaphone,
              title: "市场团队",
              desc: "用声量共振与回声室读数校准叙事与投放策略。",
            },
          ].map((role, i) => (
            <Reveal key={role.title} delay={(i % 2) * 0.06}>
              <div className="flex h-full gap-5 rounded-xl border border-line bg-page p-7 transition-colors hover:border-line2">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-md bg-solid text-on-solid">
                  <role.icon size={21} weight="bold" />
                </span>
                <div>
                  <h3 className="text-lg font-semibold tracking-tight">
                    {role.title}
                  </h3>
                  <p className="mt-2 leading-relaxed text-txt2">{role.desc}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------- S8 数据口径 ---------- */

function Caliber() {
  return (
    <section id="caliber" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
      <div className="max-w-2xl">
        <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
          口径可追溯
        </h2>
        <p className="mt-4 text-txt2">结论如何得出，每一步都写清楚。</p>
      </div>
      <Reveal>
        <div className="mt-10 rounded-xl border border-line bg-card p-8">
          <div className="flex flex-col gap-5 md:flex-row md:gap-7">
            <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-md border border-line text-accent">
              <Database size={21} weight="bold" />
            </span>
            <p className="max-w-4xl leading-relaxed text-txt2">
              声量、情绪与立场均基于平台内清洗后的讨论文本计算。各平台量纲不同，
              统一采用平台内 z-score 归一后对齐到同一时间轴；缺失时间窗如实留空，不做插值。
              跨平台结论须通过 CX1-CX5 校准门禁后方可输出，每一次推断都能回溯到数据。
            </p>
          </div>
        </div>
      </Reveal>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {GATES.map((gate, i) => (
          <Reveal key={gate.id} delay={i * 0.05}>
            <div className="h-full rounded-xl border border-line bg-page p-5">
              <p className="font-mono text-xs font-medium text-accent">
                {gate.id}
              </p>
              <h3 className="mt-2 text-sm font-semibold">{gate.name}</h3>
              <p className="mt-2 text-[13px] leading-relaxed text-txt2">
                {gate.desc}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ---------- S9 常见问题 ---------- */

function Faq() {
  return (
    <section id="faq" className="border-t border-line bg-card">
      <div className="mx-auto w-full max-w-3xl px-6 py-24 md:py-28">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            常见问题
          </h2>
          <p className="mt-4 text-txt2">
            关于口径、平台与可信度的常见疑问。
          </p>
        </div>
        <div className="mt-12 divide-y divide-line border-y border-line">
          {FAQS.map((item, i) => (
            <Reveal key={item.q} delay={i * 0.04}>
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[15px] font-semibold">
                  {item.q}
                  <CaretDown
                    size={16}
                    weight="bold"
                    className="shrink-0 text-txt3 transition-transform duration-300 group-open:rotate-180"
                  />
                </summary>
                <p className="pb-5 pr-8 leading-relaxed text-txt2">{item.a}</p>
              </details>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------- S10 收束 ---------- */

function Closing() {
  return (
    <section className="border-t border-line">
      <div className="mx-auto w-full max-w-7xl px-6 py-24 text-center md:py-32">
        <Reveal>
          <h2 className="mx-auto max-w-2xl text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
            让社交数据支撑每一次决策
          </h2>
        </Reveal>
        <Reveal delay={0.1}>
          <a href={PRODUCT_URL} className={`${CTA_CLASS} mt-10`}>
            进入分析台
            <ArrowRight size={16} weight="bold" />
          </a>
        </Reveal>
      </div>
    </section>
  );
}

/* ---------- 页脚 ---------- */

function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-start justify-between gap-6 px-6 py-10 md:flex-row md:items-center">
        <div className="flex items-center gap-2.5">
          <span className="grid size-6 place-items-center rounded bg-solid text-on-solid">
            <BrandMark size={15} />
          </span>
          <span className="text-sm font-semibold">Social Sense</span>
          <span className="font-mono text-xs text-txt3">
            © {new Date().getFullYear()}
          </span>
        </div>
        <nav className="flex flex-wrap items-center gap-6 text-sm text-txt2">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="transition-colors hover:text-txt"
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  );
}
