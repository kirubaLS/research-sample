"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { FullRosterStudent } from "@/lib/avai-mock-data";

/** One student in a drill-down list, always a link through to their own
 * report, so a number on the overview is never a dead end. */
export function StudentRow({ student, showSection, meta }: { student: FullRosterStudent; showSection: boolean; meta?: string }) {
  return (
    <Link href={`/principal/classes/${student.section}/${student.id}`} className="subject-row">
      <div>
        <div className="strong">{student.name}</div>
        <div className="small muted">
          Roll {student.rollNo}
          {showSection ? ` · ${student.section}` : ""}
        </div>
      </div>
      {meta && <div className="strong">{meta}</div>}
    </Link>
  );
}

export interface DrillDown {
  title: string;
  subtitle: string;
  students: FullRosterStudent[];
  /** Right-hand figure per row, the mark that put them in this band. */
  metaFor?: (student: FullRosterStudent) => string;
}

/** The band drill-down drawer: who exactly is behind a count. */
export function StudentDrawer({ drill, onClose }: { drill: DrillDown | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {drill && (
        <>
          <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label={drill.title}
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
          >
            <div className="drawer__head">
              <div>
                <h3 style={{ fontSize: 18 }}>{drill.title}</h3>
                <div className="muted small">{drill.subtitle}</div>
              </div>
              <button className="iconbtn" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </div>
            <div className="drawer__body">
              <div className="small muted" style={{ marginBottom: 10 }}>
                {drill.students.length} student{drill.students.length === 1 ? "" : "s"}, tap one to open their report.
              </div>
              <div style={{ display: "grid", gap: 8 }}>
                {drill.students.map((s, i) => (
                  <div key={s.id} className="reveal" style={{ "--d": `${Math.min(i, 14) * 22}ms` } as React.CSSProperties}>
                    <StudentRow student={s} showSection meta={drill.metaFor?.(s)} />
                  </div>
                ))}
                {drill.students.length === 0 && <p className="small muted">No students in this band.</p>}
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
