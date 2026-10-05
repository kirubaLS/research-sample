"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ConductedExam, type ExamsOverview, type PaperSummary, type ScheduledExam } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export type TestRow = { id: string; name: string; date: string | null; status: "Analysed" | "Awaiting marks" | "Scheduled" };

/** The synthetic group a paper that was never attached to a test falls under. There is no
 * way to create one from the screen any more, but papers that already exist stay reachable
 * rather than silently vanishing from the list. */
export const UNSCHEDULED_ID = "__unscheduled";

/** the timetable's own order: Mathematics, Science, English, Social Science, then any
 * other subject alphabetically */
export function subjectRank(code: string): number {
  const i = ["X.MATH", "X.SCI", "X.ENG", "X.SST"].indexOf(code);
  return i === -1 ? 99 : i;
}

/** "Class X Mathematics" -> "Mathematics": the class is the whole screen's context. */
export function shortSubject(label: string): string {
  return label.replace(/^Class\s+[A-Z0-9]+\s+/i, "");
}

/** Every test the school has and the papers under each, read from the same two endpoints
 * for every teacher key (GET /admin/exams, GET /admin/teacher/papers). Used by the Enter
 * marks tab; the Question papers tab reads the same data through usePaperScan. */
export function useTestBoard() {
  const [tests, setTests] = useState<TestRow[]>([]);
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    const key = getApiKey();
    if (!key) {
      setLoading(false);
      return;
    }
    try {
      const [exams, list]: [ExamsOverview, { assessments: PaperSummary[] }] = await Promise.all([
        api.exams(key),
        api.teacherPapers(key),
      ]);
      if (!alive.current) return;
      const conducted: TestRow[] = exams.conducted
        .filter((c): c is ConductedExam & { kind: "exam" } => c.kind === "exam")
        .map((c) => ({ id: c.id, name: c.name, date: c.date, status: "Analysed" }));
      const awaiting: TestRow[] = exams.awaiting_marks.map((e: ScheduledExam) => ({
        id: e.id, name: e.name, date: e.scheduled_date, status: "Awaiting marks",
      }));
      const upcoming: TestRow[] = exams.upcoming.map((e: ScheduledExam) => ({
        id: e.id, name: e.name, date: e.scheduled_date, status: "Scheduled",
      }));
      setTests([...conducted, ...awaiting, ...upcoming].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? "")));
      setPapers(list.assessments);
      setError(null);
    } catch {
      if (alive.current) setError("Could not load the tests. Check your connection and try again.");
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  /** test id -> its papers in timetable order; papers with no test under UNSCHEDULED_ID */
  const papersByTest = useMemo(() => {
    const map = new Map<string, PaperSummary[]>();
    for (const p of papers) {
      const id = p.exam_id ?? UNSCHEDULED_ID;
      map.set(id, [...(map.get(id) ?? []), p]);
    }
    for (const list of map.values()) {
      list.sort((a, b) => subjectRank(a.subject_code) - subjectRank(b.subject_code)
        || a.subject_label.localeCompare(b.subject_label));
    }
    return map;
  }, [papers]);

  return { tests, papers, papersByTest, loading, error, reload };
}
