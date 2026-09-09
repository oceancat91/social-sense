"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import {
  motion,
  useReducedMotion,
  useScroll,
  useMotionValueEvent,
} from "motion/react";
import SplitText from "@/components/SplitText";
import BrandMark from "@/components/BrandMark";
import SignalChart from "@/components/SignalChart";
import InsightParallelChart from "@/components/InsightParallelChart";
import { LIEFLAT } from "@/components/lieflatTheme";
import ScrollProgress from "@/components/ScrollProgress";
import NoiseOverlay from "@/components/NoiseOverlay";
import BackgroundLayers from "@/components/BackgroundLayers";
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
  Check,
  CaretDown,
} from "@phosphor-icons/react/dist/ssr";

const DataField3D = dynamic(() => import("@/components/DataField3D"), {
  ssr: false,
  loading: () => <div className="data-field data-field--loading" />,
});

const PRODUCT_URL = "https://socialsense.cn/app/";

const PLATFORMS = ["微博", "抖音", "B站", "小红书", "知乎", "快手"];

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
  { topic: "AI艺人与活人感之争", points: 3298, resonance: 0.24, echo: 0.28 },
  { topic: "人形机器人商业化", points: 3183, resonance: 0.21, echo: 0.26 },
  { topic: "消费降级与反向消费", points: 2923, resonance: 0.13, echo: 0.29 },
  { topic: "国潮与传统文化复兴", points: 2866, resonance: 0.05, echo: 0.32 },
];

/* 三种能力信号 */
const CAPABILITIES = [
  {
    icon: ArrowsMerge,
    title: "跨平台对齐与共振",
    desc: "不同平台量纲不可直接相加，按平台内 z-score 归一后对齐到统一时间轴，声量与情绪才真正可比。",
    note: "声量共振与错峰，一眼可辨。",
  },
  {
    icon: ChartPieSlice,
    title: "立场与情绪画像",
    desc: "对每条讨论做情绪倾向与支持 / 反对 / 中立标注，输出每平台结构化画像。",
    note: "叠加领域词表与知识增强，口径透明可复算。",
  },
  {
    icon: Gauge,
    title: "回声室指数",
    desc: "综合立场分歧、情绪分歧与声量失振，输出跨平台量化指数，直接衡量信息茧房强度。",
    note: "融合结论需通过 CX1-CX5 校准门禁。",
  },
];

/* 适用角色 */
const ROLES = [
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
    <div className="relative min-h-[100dvh] overflow-x-hidden bg-page font-sans text-txt antialiased">
      <BackgroundLayers />
      <ScrollProgress />
      <NoiseOverlay />
      <Header />
      <main className="relative z-10 w-full max-w-full pt-16">
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
      viewport={{ once: false, margin: "-60px" }}
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
  // 滚动状态：用 Motion useScroll + useMotionValueEvent（替代 window scroll listener）
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (latest) => {
    setScrolled(latest > 8);
  });

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 border-b backdrop-blur transition-all duration-300 ${
        scrolled
          ? "border-line bg-page/95 shadow-[0_12px_32px_-20px_rgb(20_24_36/0.25)]"
          : "border-transparent bg-page/70"
      }`}
    >
      <div className="flex h-16 w-full items-center justify-between px-6 md:px-8">
        <a href="#top" className="group flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-lg bg-solid text-on-solid transition-transform duration-300 ease-out group-hover:scale-[1.04]">
            <BrandMark size={25} />
          </span>
          <span className="font-brand text-xl font-semibold tracking-[-0.035em]">
            Social Sense
          </span>
        </a>

        <nav className="hidden items-stretch self-stretch text-sm text-txt2 lg:flex">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="nav-link"
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}

/* ---------- S2 Hero ---------- */

function Hero() {
  return (
    <section id="top" className="hero-stage relative overflow-hidden">
      <div className="hero-glow" aria-hidden="true" />
      <div className="relative mx-auto grid min-h-[calc(100dvh-4rem)] w-full max-w-7xl gap-8 px-6 pb-12 pt-12 md:pt-16 lg:grid-cols-[0.92fr_1.08fr] lg:items-center lg:gap-10 lg:pb-16 lg:pt-20">
        <div className="relative z-10">
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
              </a>
            </div>
          </Reveal>
        </div>

        <Reveal delay={0.28} className="relative min-h-[390px] lg:min-h-[560px]">
          <DataField3D />
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
      <Reveal>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            从原始评论到可信结论
          </h2>
          <p className="mt-4 text-txt2">
            五段管线贯穿采集到校准，每一步都产出可检查的中间结果。
          </p>
        </div>
      </Reveal>
      <div className="mt-16 grid gap-10 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE.map((item, i) => (
          <Reveal key={item.title} delay={i * 0.08}>
            <div className="flow-step group pt-6">
              <span className="flow-step__icon inline-flex size-10 items-center justify-center text-txt3">
                <item.icon size={20} weight="bold" />
              </span>
              <h3 className="mt-5 text-[15px] font-semibold transition-colors duration-300 group-hover:text-accent">
                {item.title}
              </h3>
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

/* ---------- S5 能力 ---------- */

function Capabilities() {
  return (
    <section id="capabilities" className="border-y border-line bg-card">
      <div className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
        <Reveal>
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              三种信号，支撑一种判断
            </h2>
            <p className="mt-4 text-txt2">
              对齐、画像与回声室测算互相咬合，共同约束结论不能脱离数据。
            </p>
          </div>
        </Reveal>

        <div className="mt-14 grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0">
          {CAPABILITIES.map((item, i) => (
            <Reveal key={item.title} delay={i * 0.07} className="md:px-8 md:first:pl-0 md:last:pr-0">
              <div className="group py-8 md:py-0">
                <span className="inline-flex size-11 items-center justify-center rounded-md border border-line text-accent transition-transform duration-300 ease-out group-hover:scale-105">
                  <item.icon size={22} weight="bold" />
                </span>
                <h3 className="mt-6 text-lg font-semibold tracking-tight">
                  {item.title}
                </h3>
                <p className="mt-3 leading-relaxed text-txt2">{item.desc}</p>
                <p className="mt-6 text-sm text-txt3">{item.note}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------- S6 真实话题洞察 ---------- */

function Insights() {
  return (
    <section id="insights" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-32">
      <Reveal>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            真实话题，实时洞察
          </h2>
          <p className="mt-4 text-txt2">
            从十二个领域热点出发，观察跨平台声量与情绪如何共振或错峰。指标来自真实话题样本。
          </p>
        </div>
      </Reveal>

      {/* F2 Hairline Line：短时序多平台对齐 */}
      <Reveal>
        <div className="lf-chart-frame feature-surface mt-14 px-6 py-10 md:px-10 lg:px-14">
          <div className="lf-chart-head">
            <div>
              <p className="lf-chart-title">声量在平台之间错峰传播</p>
              <p className="lf-chart-sub">
                一点代表一个时间桶 / z-score 统一量纲 / 缺失不插值
              </p>
            </div>
            <span className="lf-chart-code">F2 HAIRLINE LINE</span>
          </div>
          <div className="mt-6 grid items-center gap-8 lg:grid-cols-[1.35fr_1fr]">
            <SignalChart className="w-full" />
            <div>
              <p className="text-lg font-semibold leading-snug">
                同一话题，各平台的讨论节奏并不相同。
              </p>
              <p className="mt-4 leading-relaxed text-[#5B6675]">
                B站与微博的声量在此处同步抬升，抖音则明显错峰。真实样本显示，跨平台声量以错峰为主，只看单一平台，很难还原事件全貌。
              </p>
              <ul className="mt-6 space-y-2.5 text-sm text-[#44546A]">
                {[
                  ["B站", LIEFLAT.SERIES[0]],
                  ["微博", LIEFLAT.SERIES[1]],
                  ["抖音", LIEFLAT.SERIES[2]],
                  ["小红书", LIEFLAT.SERIES[3]],
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
          <p className="lf-chart-source">HAIRLINE LINE / SOCIAL SENSE SAMPLE / CUSTOM BLUE</p>
        </div>
      </Reveal>

      {/* L20 Parallel Coordinates：同一话题跨三个连续指标 */}
      <Reveal>
        <div className="lf-chart-frame mt-10 px-6 py-9 md:px-10">
          <div className="lf-chart-head">
            <div>
              <p className="lf-chart-title">高声量不等于高共振</p>
              <p className="lf-chart-sub">
                一根发丝线代表一个真实话题 / 三根轴保留各自原始单位
              </p>
            </div>
            <span className="lf-chart-code">L20 PARALLEL COORDINATES</span>
          </div>
          <InsightParallelChart insights={INSIGHTS} />
          <p className="lf-chart-source">PARALLEL COORDINATES / REAL MULTIPLATFORM DATA / CUSTOM BLUE</p>
        </div>
      </Reveal>

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
        <Reveal>
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              为决策者而做
            </h2>
            <p className="mt-4 text-txt2">
              不是多一块看板，而是把社交数据翻译成各岗位能直接使用的语言。
            </p>
          </div>
        </Reveal>
        <div className="mt-14 grid border-t border-line md:grid-cols-2">
          {ROLES.map((role, i) => (
            <Reveal key={role.title} delay={(i % 2) * 0.06}>
              <div className="group flex gap-5 border-b border-line py-10 md:odd:pr-10 md:even:pl-10 md:even:border-l">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-md bg-solid text-on-solid transition-transform duration-300 ease-out group-hover:scale-105">
                  <role.icon size={21} weight="bold" />
                </span>
                <div>
                  <h3 className="text-lg font-semibold tracking-tight transition-colors duration-300 group-hover:text-accent">
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
      <Reveal>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            口径可追溯
          </h2>
          <p className="mt-4 text-txt2">结论如何得出，每一步都写清楚。</p>
        </div>
      </Reveal>
      <Reveal>
        <div className="mt-10 flex max-w-4xl flex-col gap-5 md:flex-row md:gap-7">
          <span className="inline-flex size-11 shrink-0 items-center justify-center text-accent">
            <Database size={21} weight="bold" />
          </span>
          <p className="leading-relaxed text-txt2">
            声量、情绪与立场均基于平台内清洗后的讨论文本计算。各平台量纲不同，
            统一采用平台内 z-score 归一后对齐到同一时间轴；缺失时间窗如实留空，不做插值。
            跨平台结论须通过 CX1-CX5 校准门禁后方可输出，每一次推断都能回溯到数据。
          </p>
        </div>
      </Reveal>

      <div className="mt-10 max-w-4xl divide-y divide-line border-t border-line">
        {GATES.map((gate, i) => (
          <Reveal key={gate.id} delay={i * 0.05}>
            <div className="group flex items-start gap-6 py-5">
              <span className="shrink-0 font-mono text-xs font-medium leading-6 text-accent">
                {gate.id}
              </span>
              <div>
                <h3 className="text-sm font-semibold transition-colors duration-300 group-hover:text-accent">
                  {gate.name}
                </h3>
                <p className="mt-1 text-[13px] leading-relaxed text-txt2">
                  {gate.desc}
                </p>
              </div>
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
        <Reveal>
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              常见问题
            </h2>
            <p className="mt-4 text-txt2">
              关于口径、平台与可信度的常见疑问。
            </p>
          </div>
        </Reveal>
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
      </div>
    </section>
  );
}

/* ---------- 页脚（无 logo，仅文字与导航） ---------- */

function Footer() {
  return (
    <footer className="relative z-10 border-t border-line">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-start justify-between gap-6 px-6 py-10 md:flex-row md:items-center">
        <span className="font-brand text-base font-semibold tracking-[-0.025em]">
          Social Sense
        </span>
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
