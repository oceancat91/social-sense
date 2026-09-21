"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide";
import MorphGlyph from "@/components/MorphGlyph";
import { FAQS } from "@/content/home";
import Reveal from "./Reveal";

function FaqRow({
  item,
  delay,
}: {
  item: { q: string; a: string };
  delay: number;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Reveal delay={delay}>
      <details
        className="group"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[15px] font-semibold">
          {item.q}
          <MorphGlyph
            icon={open ? ChevronUp : ChevronDown}
            size={16}
            className="shrink-0 text-txt3"
          />
        </summary>
        <p className="pb-5 pr-8 leading-relaxed text-txt2">{item.a}</p>
      </details>
    </Reveal>
  );
}

export function Faq() {
  return (
    <section id="faq" className="border-t border-line bg-card">
      <div className="mx-auto w-full max-w-3xl px-6 py-24 md:py-28">
        <Reveal>
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              常见问题
            </h2>
            <p className="mt-4 text-txt2">
              平台、口径、可信度，你可能想问的都在这里。
            </p>
          </div>
        </Reveal>
        <div className="mt-12 divide-y divide-line border-y border-line">
          {FAQS.map((item, index) => (
            <FaqRow key={item.q} item={item} delay={index * 0.04} />
          ))}
        </div>
      </div>
    </section>
  );
}

export function Closing() {
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
