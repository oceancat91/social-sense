"use client";

import { BadgeCheck, Database } from "lucide";
import InsightParallelChart from "@/components/InsightParallelChart";
import MorphGlyph from "@/components/MorphGlyph";
import SignalChart from "@/components/SignalChart";
import { LIEFLAT } from "@/components/lieflatTheme";
import { GATES, INSIGHTS, ROLES, TOPICS } from "@/content/home";
import Reveal from "./Reveal";

export function Insights() {
  return (
    <section id="insights" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-32">
      <Reveal>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            真实话题，实时洞察
          </h2>
          <p className="mt-4 text-txt2">
            十二个领域热点持续追踪，看同一件事在六个平台之间如何共振、如何错峰。
          </p>
        </div>
      </Reveal>

      <Reveal>
        <div className="lf-chart-frame feature-surface mt-14 px-6 py-10 md:px-10 lg:px-14">
          <div className="lf-chart-head">
            <div>
              <p className="lf-chart-title">同一件事，各平台的引爆时刻并不同步</p>
              <p className="lf-chart-sub">
                谁先火、谁在跟，时间轴上看得一清二楚。
              </p>
            </div>
            <span className="lf-chart-code">跨平台节奏</span>
          </div>
          <div className="mt-6 grid items-center gap-8 lg:grid-cols-[1.35fr_1fr]">
            <SignalChart className="w-full" />
            <div>
              <p className="text-lg font-semibold leading-snug">
                不是所有平台，都同时在意同一件事。
              </p>
              <p className="mt-4 leading-relaxed text-[#5B6675]">
                B站与微博的声量几乎同时抬升，抖音明显慢了半拍。只看单一平台，永远拼不出事件的全貌。
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
          <p className="lf-chart-source">Social Sense · 跨平台声量观测</p>
        </div>
      </Reveal>

      <Reveal>
        <div className="lf-chart-frame mt-10 px-6 py-9 md:px-10">
          <div className="lf-chart-head">
            <div>
              <p className="lf-chart-title">声量最大，未必共振最强</p>
              <p className="lf-chart-sub">
                四个真实话题，一条线看完三个维度。
              </p>
            </div>
            <span className="lf-chart-code">话题三维对比</span>
          </div>
          <InsightParallelChart insights={INSIGHTS} />
          <p className="lf-chart-source">Social Sense · 真实话题样本</p>
        </div>
      </Reveal>

      <Reveal>
        <div className="mt-8 flex flex-wrap gap-2">
          {TOPICS.map((topic) => (
            <span
              key={topic}
              className="inline-flex items-center gap-1.5 rounded-md bg-card2 px-3 py-1.5 text-sm text-txt2 transition-colors hover:text-txt"
            >
              {topic}
            </span>
          ))}
        </div>
      </Reveal>
    </section>
  );
}

export function Roles() {
  return (
    <section id="roles" className="border-y border-line bg-card">
      <div className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
        <Reveal>
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              为决策者而做
            </h2>
            <p className="mt-4 text-txt2">
              不是又多一块看板，而是把社交数据翻译成每个岗位能直接用的话。
            </p>
          </div>
        </Reveal>
        <div className="mt-14 grid border-t border-line md:grid-cols-2">
          {ROLES.map((role, index) => (
            <Reveal key={role.title} delay={(index % 2) * 0.06}>
              <div className="group flex gap-5 border-b border-line py-10 md:odd:pr-10 md:even:border-l md:even:pl-10">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-md bg-solid text-on-solid transition-transform duration-300 ease-out group-hover:scale-105">
                  <MorphGlyph icon={role.icon} size={21} />
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

export function Caliber() {
  return (
    <section id="caliber" className="mx-auto w-full max-w-7xl px-6 py-24 md:py-28">
      <Reveal>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            每一步都摊开给你看
          </h2>
          <p className="mt-4 text-txt2">结论怎么来的，全部看得见。</p>
        </div>
      </Reveal>
      <Reveal>
        <div className="mt-10 flex max-w-4xl flex-col gap-5 md:flex-row md:gap-7">
          <span className="inline-flex size-11 shrink-0 items-center justify-center text-accent">
            <MorphGlyph icon={Database} size={21} />
          </span>
          <p className="leading-relaxed text-txt2">
            所有读数都来自各平台清洗后的公开讨论。各平台口径先拉齐，再放到同一根时间轴上比较；
            没有观测到的时间窗如实留空，绝不用估算值填补。每一条判断，都能一路追溯到最原始的讨论。
          </p>
        </div>
      </Reveal>

      <div className="mt-10 max-w-4xl divide-y divide-line border-t border-line">
        {GATES.map((gate, index) => (
          <Reveal key={gate.name} delay={index * 0.05}>
            <div className="group flex items-start gap-6 py-5">
              <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-accent transition-transform duration-300 ease-out group-hover:scale-110">
                <MorphGlyph icon={BadgeCheck} size={17} />
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
