import { Info, Search, Sparkles, FlaskConical } from "lucide-react";

/**
 * §5.7 Empty / limited-evidence states. These are first-class UI, not errors:
 * they tell the principal what the system can and cannot say yet.
 */
export type EvidenceKind = "trend" | "early" | "cause" | "paper";

const config: Record<EvidenceKind, { title: string; tone: "" | "evidence--gold" | "evidence--neutral"; Icon: typeof Info }> = {
  trend: { title: "Trend not yet available", tone: "", Icon: Info },
  early: { title: "Early signal", tone: "evidence--gold", Icon: Sparkles },
  cause: { title: "Cause not localized", tone: "evidence--neutral", Icon: Search },
  paper: { title: "Paper under-tests this area", tone: "evidence--gold", Icon: FlaskConical },
};

export function EvidenceState({ kind, children, compact = false }: { kind: EvidenceKind; children: React.ReactNode; compact?: boolean }) {
  const { title, tone, Icon } = config[kind];
  return (
    <div className={`evidence ${tone}`} role="note">
      <Icon size={16} />
      <div>
        {!compact && <div className="evidence__title">{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
}
