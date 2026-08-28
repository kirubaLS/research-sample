"use client";

/**
 * Screens 3-4: instructions and the 36 items, six to a screen.
 *
 * Every answer is written the moment it is tapped, and each item carries shown_at and
 * answered_at. Those two timestamps are the entire validity layer — they cannot be added
 * retroactively, which is why they go in on day one.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api, type SessionPayload } from "@/lib/api";

type Answer = { value: number; shownAt: number; answeredAt: number };

function TestFlow() {
  const router = useRouter();
  const search = useSearchParams();
  const sessionId = search.get("session");

  const [payload, setPayload] = useState<SessionPayload | null>(null);
  const [screenIndex, setScreenIndex] = useState(-1); // -1 = instructions
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [saving, setSaving] = useState(false);
  const shownAt = useRef<Record<string, number>>({});

  useEffect(() => {
    if (!sessionId) return;
    const cached = sessionStorage.getItem(`yaadhum:${sessionId}`);
    if (cached) setPayload(JSON.parse(cached) as SessionPayload);
  }, [sessionId]);

  const screen = useMemo(
    () => (payload && screenIndex >= 0 ? payload.screens[screenIndex] : null),
    [payload, screenIndex],
  );

  useEffect(() => {
    const now = Date.now() / 1000;
    for (const item of screen ?? []) {
      if (!(item.item_id in shownAt.current)) shownAt.current[item.item_id] = now;
    }
  }, [screen]);

  if (!sessionId || !payload) {
    return (
      <main>
        <h1>Session not found</h1>
        <p className="muted">Please open the link your teacher gave you again.</p>
      </main>
    );
  }

  const answeredCount = Object.keys(answers).length;
  const allOnScreenAnswered = (screen ?? []).every((i) => answers[i.item_id]);

  function choose(itemId: string, value: number) {
    setAnswers((prev) => ({
      ...prev,
      [itemId]: {
        value,
        shownAt: shownAt.current[itemId] ?? Date.now() / 1000,
        answeredAt: Date.now() / 1000,
      },
    }));
  }

  async function next() {
    if (!screen) return;
    setSaving(true);
    try {
      await api.saveResponses(
        sessionId!,
        screen.map((i) => ({
          item_id: i.item_id,
          value: answers[i.item_id].value,
          shown_at: answers[i.item_id].shownAt,
          answered_at: answers[i.item_id].answeredAt,
        })),
      );
      if (screenIndex + 1 < payload!.screens.length) {
        setScreenIndex(screenIndex + 1);
        window.scrollTo(0, 0);
      } else {
        await api.complete(sessionId!);
        router.push("/t/thanks");
      }
    } catch {
      // Answers are already held locally; the student can retry without losing anything.
      alert("Could not save just now. Please tap Continue again.");
    } finally {
      setSaving(false);
    }
  }

  if (screenIndex < 0) {
    return (
      <main className="narrow">
        <div className="hero">
          <p className="eyebrow">Ready when you are</p>
          <h1>Before you start</h1>
        </div>
        <div className="card" style={{ marginTop: 18 }}>
          <div className="stack" style={{ gap: 14 }}>
            <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
              <span className="badge">1</span>
              <span>36 questions across six screens. About eight minutes.</span>
            </div>
            <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
              <span className="badge">2</span>
              <span>There are no right or wrong answers.</span>
            </div>
            <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
              <span className="badge">3</span>
              <span>
                Answer about what you would <em>enjoy doing</em> — not what you think you
                should say.
              </span>
            </div>
            <div className="row" style={{ gap: 12, alignItems: "flex-start" }}>
              <span className="badge">4</span>
              <span>Your answers save as you go. If the page closes, you can come back.</span>
            </div>
          </div>
        </div>
        <button onClick={() => setScreenIndex(0)} style={{ marginTop: 22, width: "100%" }}>
          Take the test
        </button>
      </main>
    );
  }

  return (
    <main className="narrow">
      <div className="row between small muted" style={{ marginBottom: 8 }}>
        <span>
          Screen {screenIndex + 1} of {payload.screens.length}
        </span>
        <span className="mono">
          {answeredCount} / {payload.total_items}
        </span>
      </div>
      <div className="progress">
        <div style={{ width: `${(answeredCount / payload.total_items) * 100}%` }} />
      </div>

      <h2 style={{ margin: "22px 0 14px" }}>How much would you enjoy doing this?</h2>

      <div className="card">
        {(screen ?? []).map((item) => (
          <div className="item" key={item.item_id}>
            <div className="qtext">{item.text}</div>
            <div className="likert">
              {item.options.map((label, i) => (
                <button
                  key={label}
                  type="button"
                  aria-pressed={answers[item.item_id]?.value === i + 1}
                  onClick={() => choose(item.item_id, i + 1)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={next}
        disabled={!allOnScreenAnswered || saving}
        style={{ marginTop: 20, width: "100%" }}
      >
        {saving
          ? "Saving…"
          : screenIndex + 1 < payload.screens.length
            ? "Continue"
            : "Finish"}
      </button>
    </main>
  );
}


/** useSearchParams needs a Suspense boundary for Next's static generation. */
export default function TestPage() {
  return (
    <Suspense fallback={<main><p className="muted">Loading…</p></main>}>
      <TestFlow />
    </Suspense>
  );
}
