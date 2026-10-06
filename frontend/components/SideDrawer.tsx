"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X } from "lucide-react";

/** A panel that slides in from the right over the page, for looking at one thing (a mapped
 * question paper, a class's scanned answer sheets) without leaving the list behind it.
 *
 * Closes on Escape, on a click on the dim backdrop and on its X. Focus moves into it when
 * it opens and back to what had it when it closes; the page behind does not scroll. It is
 * portalled to <body>, because a position:fixed panel inside an ancestor that carries a
 * transform (the tab content has one while it animates) is positioned against that
 * ancestor, not the window. The entrance tilts a few degrees in 3D and settles flat -- the
 * transform is gone at rest, so nothing inside is left in a 3D context. */
export function SideDrawer({
  open, onClose, title, subtitle, actions, children, width = 920,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  /** buttons shown in the header, left of the close button */
  actions?: ReactNode;
  children: ReactNode;
  /** the widest the panel gets, in px; it is the full width of a narrow screen */
  width?: number;
}) {
  const reduce = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const raf = window.requestAnimationFrame(() => panel.current?.focus());
    function onKey(e: KeyboardEvent) {
      // an open modal (edit a question, settle a review) sits above the drawer and takes
      // Escape for itself
      if (e.key === "Escape" && !document.querySelector(".modal-backdrop")) close.current();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
      opener.current?.focus?.();
    };
  }, [open]);

  if (!mounted) return null;
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="sd-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22 }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
          <motion.aside
            ref={panel}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === "string" ? title : "Details"}
            className="sd-panel"
            style={{ maxWidth: width, transformPerspective: 1400, transformOrigin: "right center" }}
            initial={reduce ? { opacity: 0 } : { x: "100%", rotateY: -7, opacity: 0.6 }}
            animate={{ x: 0, rotateY: 0, opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { x: "100%", rotateY: -5, opacity: 0.6 }}
            transition={{ type: "spring", stiffness: 280, damping: 32, mass: 0.9 }}
          >
            <header className="sd-head">
              <div style={{ minWidth: 0 }}>
                <div className="sd-title">{title}</div>
                {subtitle && <div className="small muted sd-sub">{subtitle}</div>}
              </div>
              <div className="sd-head__right">
                {actions}
                <button type="button" className="sd-close" onClick={onClose} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
            </header>
            <div className="sd-body">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
