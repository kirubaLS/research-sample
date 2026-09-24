"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowUp, ChevronsUpDown, Check, Copy } from "lucide-react";
import { EASE_OUT } from "@/components/motion";

/**
 * Small shared pieces for the AVAI operator console, trimmed to what the
 * real /platform API actually gives us. The reference design's StatusPill /
 * MiniColumns / MiniArea charts read fields (account status, onboarding
 * progress, weekly trend) our backend has no concept of -- see the gap
 * note in the wiring report. Dropped rather than fed fake numbers.
 */

// ------------------------------------------------------------
// Toast, for acknowledging a real write (key issued, school created, ...)
// ------------------------------------------------------------

export function useToast() {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((text: string) => {
    setMessage(text);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setMessage(null), 3200);
  }, []);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { message, show };
}

export function Toast({ message }: { message: string | null }) {
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          className="toast"
          role="status"
          aria-live="polite"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
          transition={{ duration: 0.28, ease: EASE_OUT }}
        >
          {message}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ------------------------------------------------------------
// Sortable table headers
// ------------------------------------------------------------

export type SortDir = "asc" | "desc";

export function SortHeader<K extends string>({
  label,
  field,
  sort,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  field: K;
  sort: K;
  dir: SortDir;
  onSort: (field: K) => void;
  align?: "left" | "right";
}) {
  const on = sort === field;
  return (
    <th scope="col" aria-sort={on ? (dir === "asc" ? "ascending" : "descending") : "none"} style={{ textAlign: align, whiteSpace: "nowrap" }}>
      <button
        type="button"
        onClick={() => onSort(field)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          background: "none",
          border: "none",
          padding: 0,
          font: "inherit",
          color: on ? "var(--brand-blue)" : "inherit",
          cursor: "pointer",
          letterSpacing: "inherit",
          textTransform: "inherit",
        }}
      >
        {label}
        {on ? dir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} /> : <ChevronsUpDown size={11} style={{ opacity: 0.4 }} />}
      </button>
    </th>
  );
}

// ------------------------------------------------------------
// Empty state
// ------------------------------------------------------------

export function OpsEmpty({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="small muted"
      style={{
        border: "1.5px dashed var(--line-strong)",
        borderRadius: "var(--radius-md)",
        padding: "18px 16px",
        textAlign: "center",
        background: "rgba(255,255,255,.55)",
      }}
    >
      {children}
    </div>
  );
}

// ------------------------------------------------------------
// A secret shown once (a raw api_key) -- copy button, never re-fetchable.
// ------------------------------------------------------------

export function CopySecret({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
      <code className="mono" style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere", fontSize: 12.5, background: "var(--surface-2)", padding: "6px 9px", borderRadius: 6 }}>
        {value}
      </code>
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
          } catch {
            /* clipboard blocked, the value is still selectable text */
          }
        }}
      >
        {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
