"use client";

import { useEffect } from "react";

/**
 * Real 3D on the cards the app already draws -- a card, a stat tile, a paper row -- tilted
 * toward the pointer with a light source that moves the other way, on top of the CSS-only
 * motion the design system already has (hover lift, page-enter fade). One listener, added
 * once here, reaches every one of them: they are all plain elements carrying a shared
 * class name, so there is nothing to wire up on each page.
 *
 * Skipped entirely for touch (there is no hover to tilt toward) and for anyone who asked
 * the OS for less motion -- the same rule the rest of the sheet already follows.
 */
const SELECTOR = ".card, .stat, .tile, .paper-row, .schoolpick";
const MAX_DEG = 7;
const LIFT = 16;

export function Tilt3D() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (window.matchMedia("(hover: none)").matches) return;

    let current: HTMLElement | null = null;
    let frame = 0;

    function clear(el: HTMLElement) {
      el.style.transform = "";
      el.style.boxShadow = "";
    }

    function apply(target: HTMLElement, clientX: number, clientY: number) {
      const rect = target.getBoundingClientRect();
      const px = (clientX - rect.left) / rect.width;
      const py = (clientY - rect.top) / rect.height;
      const rx = (0.5 - py) * MAX_DEG * 2;
      const ry = (px - 0.5) * MAX_DEG * 2;
      target.style.transform =
        `perspective(900px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateZ(${LIFT}px)`;
      // The shadow falls away from the pointer, as if the card tipped toward a light
      // sitting where the cursor is -- the cheapest cue that sells the tilt as real depth.
      const shadowX = (px - 0.5) * -18;
      const shadowY = (py - 0.5) * -18 + 14;
      target.style.boxShadow = `${shadowX.toFixed(1)}px ${shadowY.toFixed(1)}px 32px -12px rgba(22, 28, 43, 0.35)`;
    }

    function onMove(e: PointerEvent) {
      if (e.pointerType !== "mouse") return;
      const target = (e.target as HTMLElement | null)?.closest<HTMLElement>(SELECTOR) ?? null;
      if (target !== current && current) clear(current);
      current = target;
      if (!target) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => apply(target, e.clientX, e.clientY));
    }

    function onLeave() {
      if (current) clear(current);
      current = null;
    }

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerleave", onLeave);
    document.addEventListener("scroll", onLeave, { passive: true, capture: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("scroll", onLeave, true);
      if (current) clear(current);
    };
  }, []);

  return null;
}
