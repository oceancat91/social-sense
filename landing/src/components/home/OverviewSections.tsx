"use client";

import dynamic from "next/dynamic";
import MorphGlyph from "@/components/MorphGlyph";
import SplitText from "@/components/SplitText";
import {
  CAPABILITIES,
  CTA_CLASS,
  PIPELINE,
  PLATFORMS,
  PRODUCT_URL,
} from "@/content/home";
import Reveal from "./Reveal";

const DataField3D = dynamic(() => import("@/components/DataField3D"), {
  ssr: false,
  loading: () => <div className="data-field data-field--loading" />,
});

export function Hero() {
  return (
    <section id="top" className="hero-stage relative overflow-hidden">
      <div className="hero-glow" aria-hidden="true" />
      <div className="relative mx-auto grid min-h-[100dvh] w-full max-w-7xl gap-8 px-6 pb-12 pt-28 md:pt-32 lg:grid-cols-[0.92fr_1.08fr] lg:items-center lg:gap-10 lg:pb-16 lg:pt-36">
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
              六大平台实时追踪，把嘈杂的舆论，收敛成一眼可读的决策信号。
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

export function PlatformStrip() {
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
            {items.map((platform, index) => (
              <span
                key={`${platform}-${index}`}
                className="flex items-center gap-10 whitespace-nowrap text-sm font-medium text-txt2"
              >
                {platform}
                <span className="text-txt3/50">/</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function Method() {
  return (
    <section id="method" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
      <Reveal>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            把杂乱评论，变成可信结论
          </h2>
          <p className="mt-4 text-txt2">
            从采集到校准五步走完，每一步都经得起复查。
          </p>
        </div>
      </Reveal>
      <div className="mt-16 grid gap-10 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE.map((item, index) => (
          <Reveal key={item.title} delay={index * 0.08}>
            <div className="flow-step group pt-6">
              <span className="flow-step__icon inline-flex size-10 items-center justify-center text-txt3">
                <MorphGlyph icon={item.icon} size={20} />
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

export function Capabilities() {
  return (
    <section id="capabilities" className="border-y border-line bg-card">
      <div className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
        <Reveal>
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              三种信号，支撑一种判断
            </h2>
            <p className="mt-4 text-txt2">
              对齐、画像、回声室三者互相咬合，让每一条结论都站在数据上。
            </p>
          </div>
        </Reveal>

        <div className="mt-14 grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0">
          {CAPABILITIES.map((item, index) => (
            <Reveal
              key={item.title}
              delay={index * 0.07}
              className="md:px-8 md:first:pl-0 md:last:pr-0"
            >
              <div className="group py-8 md:py-0">
                <span className="inline-flex size-11 items-center justify-center rounded-md border border-line text-accent transition-transform duration-300 ease-out group-hover:scale-105">
                  <MorphGlyph icon={item.icon} size={22} />
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
