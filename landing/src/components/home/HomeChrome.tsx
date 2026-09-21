"use client";

import { useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
} from "motion/react";
import { Menu as MenuGlyph, X } from "lucide";
import BrandMark from "@/components/BrandMark";
import MorphGlyph from "@/components/MorphGlyph";
import { CTA_CLASS, NAV, PRODUCT_URL } from "@/content/home";

export function Header() {
  const { scrollY } = useScroll();
  const reduce = useReducedMotion();
  const [lifted, setLifted] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useMotionValueEvent(scrollY, "change", (latest) => {
    setLifted(latest > 16);
  });

  return (
    <header
      data-lifted={lifted || menuOpen}
      className="ss-header fixed inset-x-0 top-0 z-50"
    >
      <div className="flex h-16 w-full items-center justify-between gap-4 px-6 md:px-8">
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
            <a key={item.href} href={item.href} className="nav-link">
              {item.label}
            </a>
          ))}
        </nav>

        <button
          type="button"
          className="header-toggle -mr-2 grid size-10 place-items-center rounded-lg text-txt transition-colors duration-200 hover:bg-card2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent lg:hidden"
          aria-label={menuOpen ? "关闭导航" : "打开导航"}
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
          onClick={() => setMenuOpen((value) => !value)}
        >
          <MorphGlyph icon={menuOpen ? X : MenuGlyph} size={22} />
        </button>
      </div>

      {menuOpen && (
        <motion.nav
          id="mobile-nav"
          className="ss-mobile-nav lg:hidden"
          initial={reduce ? false : { opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        >
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="ss-mobile-nav__link"
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </a>
          ))}
          <a
            href={PRODUCT_URL}
            className={`${CTA_CLASS} mt-3 justify-center`}
            onClick={() => setMenuOpen(false)}
          >
            进入分析台
          </a>
        </motion.nav>
      )}
    </header>
  );
}

export function Footer() {
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
