"use client";

import React, { useRef, useEffect, useState } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText as GSAPSplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";
import { useReducedMotion } from "motion/react";

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger, GSAPSplitText, useGSAP);
}

export type SplitTextTag =
  | "h1"
  | "h2"
  | "h3"
  | "h4"
  | "h5"
  | "h6"
  | "p"
  | "span";

export interface SplitTextProps {
  text: string;
  className?: string;
  /** per-char stagger in ms */
  delay?: number;
  duration?: number;
  ease?: string;
  splitType?: string;
  from?: gsap.TweenVars;
  to?: gsap.TweenVars;
  threshold?: number;
  rootMargin?: string;
  textAlign?: "left" | "center" | "right";
  tag?: SplitTextTag;
  /** render as a block-level container (needed for multi-line CJK headlines) */
  block?: boolean;
  onLetterAnimationComplete?: () => void;
}

/**
 * React Bits SplitText, ported to TSX.
 * https://reactbits.dev/TextAnimations/SplitText
 *
 * Wraps every character of `text` in its own span via the GSAP SplitText
 * plugin, then staggers each character into view when the element scrolls
 * into the viewport (once).
 *
 * Adaptations for this project:
 * - TypeScript rewrite.
 * - Optional `block` prop for multi-line CJK headlines (official defaults to
 *   an inline-block <p> with centered alignment, which cannot hold controlled
 *   line breaks).
 * - Reduced-motion and SSR safe: when `prefers-reduced-motion` is set, the
 *   text renders statically with no split or tween.
 */
export default function SplitText({
  text,
  className = "",
  delay = 50,
  duration = 1.25,
  ease = "power3.out",
  splitType = "chars",
  from = { opacity: 0, y: 40 },
  to = { opacity: 1, y: 0 },
  threshold = 0.1,
  rootMargin = "-100px",
  textAlign = "center",
  tag = "p",
  block = false,
  onLetterAnimationComplete,
}: SplitTextProps) {
  type SplitEl = HTMLElement & { _rbsplitInstance?: GSAPSplitText | null };
  const ref = useRef<SplitEl | null>(null);
  const animationCompletedRef = useRef(false);
  const onCompleteRef = useRef(onLetterAnimationComplete);
  const [fontsLoaded, setFontsLoaded] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    onCompleteRef.current = onLetterAnimationComplete;
  }, [onLetterAnimationComplete]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (document.fonts?.status === "loaded") {
      setFontsLoaded(true);
    } else {
      document.fonts?.ready.then(() => setFontsLoaded(true));
    }
  }, []);

  useGSAP(
    () => {
      if (!ref.current || !text || !fontsLoaded) return;
      if (prefersReducedMotion) return;
      if (animationCompletedRef.current) return;
      const el = ref.current;

      // Clear a stale instance before re-running (prevents wrapper stacking).
      if ((el as SplitEl)._rbsplitInstance) {
        try {
          (el as SplitEl)._rbsplitInstance!.revert();
        } catch {
          /* noop */
        }
        (el as SplitEl)._rbsplitInstance = null;
      }

      const startPct = (1 - threshold) * 100;
      const marginMatch = /^(-?\d+(?:\.\d+)?)(px|em|rem|%)?$/.exec(rootMargin);
      const marginValue = marginMatch ? parseFloat(marginMatch[1]) : 0;
      const marginUnit = marginMatch ? marginMatch[2] || "px" : "px";
      const sign =
        marginValue === 0
          ? ""
          : marginValue < 0
            ? `-=${Math.abs(marginValue)}${marginUnit}`
            : `+=${marginValue}${marginUnit}`;
      const start = `top ${startPct}%${sign}`;

      let targets: Element[] = [];
      const assignTargets = (self: GSAPSplitText) => {
        if (splitType.includes("chars") && self.chars.length) {
          targets = self.chars;
        }
        if (!targets.length && splitType.includes("words") && self.words.length) {
          targets = self.words;
        }
        if (!targets.length && splitType.includes("lines") && self.lines.length) {
          targets = self.lines;
        }
        if (!targets.length) {
          targets = self.chars || self.words || self.lines;
        }
      };

      const splitInstance = new GSAPSplitText(el, {
        type: splitType,
        smartWrap: true,
        autoSplit: splitType === "lines",
        linesClass: "split-line",
        wordsClass: "split-word",
        charsClass: "split-char",
        reduceWhiteSpace: false,
        onSplit: (self) => {
          assignTargets(self);
          const tween = gsap.fromTo(
            targets,
            { ...from },
            {
              ...to,
              duration,
              ease,
              stagger: delay / 1000,
              scrollTrigger: {
                trigger: el,
                start,
                once: true,
                fastScrollEnd: true,
                anticipatePin: 0.4,
              },
              onComplete: () => {
                animationCompletedRef.current = true;
                onCompleteRef.current?.();
              },
              willChange: "transform, opacity",
              force3D: true,
            },
          );
          return tween;
        },
      });

      (el as SplitEl)._rbsplitInstance = splitInstance;

      return () => {
        ScrollTrigger.getAll().forEach((st) => {
          if (st.trigger === el) st.kill();
        });
        try {
          splitInstance.revert();
        } catch {
          /* noop */
        }
        (el as SplitEl)._rbsplitInstance = null;
      };
    },
    {
      dependencies: [
        text,
        delay,
        duration,
        ease,
        splitType,
        JSON.stringify(from),
        JSON.stringify(to),
        threshold,
        rootMargin,
        fontsLoaded,
        prefersReducedMotion,
      ],
      scope: ref,
    },
  );

  const Tag = tag;
  const style: React.CSSProperties = {
    textAlign,
    overflow: "hidden",
    display: block ? "block" : "inline-block",
    whiteSpace: "normal",
    wordWrap: "break-word",
    willChange: "transform, opacity",
  };
  const classes = `split-parent ${className}`;

  return React.createElement(
    Tag,
    { ref, style, className: classes },
    text,
  );
}
