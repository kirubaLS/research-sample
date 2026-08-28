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
};
