"use client";

import { motion } from "framer-motion";
import { Lock, type LucideIcon } from "lucide-react";
import { EASE_OUT } from "@/components/motion";

/** One wizard screen: a raised panel with a tinted header strip. */
export function StepCard({
  icon: Icon,
  eyebrow,
  title,
  lead,
  accent = "var(--brand-teal)",
  children,
}: {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  lead?: string;
  accent?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="surface surface--raised" style={{ overflow: "hidden" }}>
      <div
        style={{
          display: "flex",
          gap: 14,
          alignItems: "flex-start",
          padding: "clamp(18px, 4vw, 24px) clamp(16px, 4vw, 26px)",
          background: `linear-gradient(180deg, color-mix(in srgb, ${accent} 13%, #fff), color-mix(in srgb, ${accent} 3%, #fff))`,
          borderBottom: "1px solid var(--line)",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 44,
            height: 44,
            flex: "0 0 44px",
            borderRadius: 14,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            background: `linear-gradient(160deg, color-mix(in srgb, ${accent} 74%, #fff), ${accent})`,
            boxShadow: `0 10px 20px -10px ${accent}, inset 0 1px 0 rgba(255,255,255,.4)`,
          }}
        >
          <Icon size={21} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">{eyebrow}</div>
          <h2 style={{ fontSize: "clamp(19px, 4.2vw, 23px)", letterSpacing: "-.01em", marginTop: 2 }}>{title}</h2>
          {lead && (
            <p className="muted" style={{ fontSize: 13.5, lineHeight: 1.45, marginTop: 5 }}>
              {lead}
            </p>
          )}
        </div>
      </div>
      <div style={{ padding: "clamp(18px, 4vw, 24px) clamp(16px, 4vw, 26px)", display: "flex", flexDirection: "column", gap: 22 }}>
        {children}
      </div>
    </div>
  );
}

/** Label + helper text above a group of controls. */
export function Question({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        {htmlFor ? (
          <label htmlFor={htmlFor} style={{ fontSize: 14.5, fontWeight: 650, display: "block" }}>
            {label}
          </label>
        ) : (
          <div style={{ fontSize: 14.5, fontWeight: 650 }}>{label}</div>
        )}
        {hint && (
          <div className="muted" style={{ fontSize: 12.5, marginTop: 3 }}>
            {hint}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

export function FieldError({ show, children }: { show: boolean; children: React.ReactNode }) {
  if (!show) return null;
  return (
    <motion.div
      role="alert"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: EASE_OUT }}
      style={{ fontSize: 12.5, fontWeight: 600, color: "var(--risk)" }}
    >
      {children}
    </motion.div>
  );
}

/** Plain option chips, single- or multi-select, no icon (the reference's
 * per-option icon set belonged entirely to its fake option lists). */
export function ChipGroup({
  options,
  selected,
  onChange,
  accent = "var(--brand-teal)",
  multi = false,
  groupLabel,
}: {
  options: { id: string; label: string }[];
  selected: string[];
  onChange: (next: string[]) => void;
  accent?: string;
  multi?: boolean;
  groupLabel: string;
}) {
  function toggle(id: string) {
    if (!multi) {
      onChange([id]);
      return;
    }
    onChange(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);
  }

  return (
    <div className="chipset" role="group" aria-label={groupLabel}>
      {options.map((o, i) => {
        const on = selected.includes(o.id);
        return (
          <motion.button
            key={o.id}
            type="button"
            className={`chip${on ? " chip--on" : ""}`}
            style={{ "--accent": accent } as React.CSSProperties}
            aria-pressed={on}
            onClick={() => toggle(o.id)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, delay: 0.03 + i * 0.025, ease: EASE_OUT }}
            whileTap={{ scale: 0.96 }}
          >
            {o.label}
          </motion.button>
        );
      })}
    </div>
  );
}

/** A value the school already gave us, shown, not editable. */
export function LockedField({ label, value }: { label: string; value: string }) {
  return (
    <div className="field">
      <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--brand-ink-soft)" }}>{label}</span>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "10px 12px",
          borderRadius: "var(--radius-md)",
          border: "1px dashed var(--line-strong)",
          background: "var(--surface-2)",
          fontSize: 14,
          fontWeight: 600,
          color: "var(--brand-ink)",
        }}
      >
        <Lock size={13} style={{ color: "var(--muted)", flex: "0 0 auto" }} />
        <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</span>
      </div>
    </div>
  );
}
