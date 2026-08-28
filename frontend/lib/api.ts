const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  return (await res.json()) as T;
}

function authed<T>(path: string, key: string, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, headers: { "X-API-Key": key, ...(init?.headers ?? {}) } });
}

// --- dashboard types ------------------------------------------------------------------
export interface SectionSummary {
  section_id: string;
  label: string;
  student_path: string;
  students: number;
  completed: number;
  flagged: number;
}

export interface Overview {
  school: { id: string; name: string; state: string | null };
  sections: SectionSummary[];
  totals: { students: number; completed: number; flagged: number };
  assessments: {
    id: string;
    title: string;
    paper_code: string | null;
    subject_code: string;
    status: string;
    total_marks: number | null;
    frozen: boolean;
  }[];
}

export interface RosterRow {
  student_id: string;
  name: string;
  roll_no: string;
  status: "not_started" | "in_progress" | "complete";
  validity: string | null;
  holland_code: string | null;
  withheld: boolean | null;
  top_stream: string | null;
}

export interface InterestReport {
  student: { id: string; name: string; roll_no: string };
  validity: string;
  validity_detail: { reasons?: string[] } | null;
  scales: { scale: string; raw: number; centered: number; percentile: number; ci: number[] }[];
  holland_code: string | null;
  differentiation: number | null;
  consistency: number | null;
  stream_fit: Record<string, number> | null;
  recommendation_withheld: boolean;
  withheld_reason: string | null;
}

export interface Screen {
  item_id: string;
  text: string;
  options: string[];
}

export interface SessionPayload {
  session_id: string;
  locale: string;
  total_items: number;
  screens: Screen[][];
}

export const api = {
  startSession: (classCode: string, body: Record<string, unknown>) =>
    request<SessionPayload>(`/t/${classCode}/start`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  saveResponses: (
    sessionId: string,
    responses: { item_id: string; value: number; shown_at: number; answered_at: number }[],
  ) =>
    request<{ saved: number; answered: number; total_items: number }>(
      `/t/session/${sessionId}/responses`,
      { method: "POST", body: JSON.stringify({ responses }) },
    ),

  complete: (sessionId: string) =>
    request<{ message: string; submitted: number }>(`/t/session/${sessionId}/complete`, {
      method: "POST",
    }),

  // --- dashboard ---
  whoami: (key: string) => authed<{ name: string; state: string | null }>("/admin/me", key),

  overview: (key: string) => authed<Overview>("/admin/overview", key),

  roster: (key: string, sectionId: string) =>
    authed<{ section: { id: string; label: string; student_path: string }; students: RosterRow[] }>(
      `/admin/sections/${sectionId}/students`,
      key,
    ),

  cohort: (key: string, sectionId: string) =>
    authed<{ holland: Record<string, number>; streams: Record<string, number>; counted: number; withheld: number }>(
      `/admin/cohort/${sectionId}`,
      key,
    ),

  interestReport: (key: string, studentId: string) =>
    authed<InterestReport>(`/reports/interest/${studentId}`, key),
};
