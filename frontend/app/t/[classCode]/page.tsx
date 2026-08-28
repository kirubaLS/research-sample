"use client";

/**
 * Screen 1-2: the landing page and the profile form.
 *
 * The student journey that starts here is deliberately a dead end — it finishes at
 * "thank you" and returns no score, code or stream. That boundary is enforced in the
 * database, not by hiding a button, but the UI must not imply otherwise.
 */

import { useRouter } from "next/navigation";
import { use, useState } from "react";
import { z } from "zod";
import { api, ApiError } from "@/lib/api";

const Profile = z.object({
  name: z.string().min(1, "Please enter your name"),
  roll_no: z.string().min(1, "Please enter your roll number"),
  age: z.coerce.number().int().min(8).max(25).optional(),
  gender: z.enum(["female", "male", "other", "prefer_not_to_say"]).optional(),
  section: z.string().default("A"),
  locale: z.enum(["en", "ta", "hi"]).default("en"),
});

export default function StartPage({ params }: { params: Promise<{ classCode: string }> }) {
  const { classCode } = use(params);
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const parsed = Profile.safeParse(Object.fromEntries(form.entries()));
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Please check the form");
      return;
    }
    setBusy(true);
    try {
      const session = await api.startSession(classCode, parsed.data);
      sessionStorage.setItem(`yaadhum:${session.session_id}`, JSON.stringify(session));
      router.push(`/t/${classCode}/test?session=${session.session_id}`);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? "That class link is not recognised. Please check it with your teacher."
          : "Could not start the test. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Class X · interest questionnaire</p>
        <h1>Tell us about yourself</h1>
        <p className="lede">
          36 short questions, about eight minutes. There are no right or wrong answers — just
          say how much you would enjoy doing each thing.
        </p>
      </div>

      <div className="notice" style={{ margin: "18px 0 24px" }}>
        Your school has your parent or guardian&apos;s consent for this activity. Your answers
        go to your school&apos;s counsellor, <strong>not to other students</strong>.
      </div>

      <form onSubmit={onSubmit} className="card">
        <div className="field">
          <label htmlFor="name">Your name</label>
          <input id="name" name="name" autoComplete="name" required />
        </div>

        <div className="field">
          <label htmlFor="roll_no">Roll number</label>
          <input id="roll_no" name="roll_no" inputMode="numeric" required />
        </div>

        <div className="field">
          <label htmlFor="section">Section</label>
          <input id="section" name="section" defaultValue="A" />
        </div>

        <div className="field">
          <label htmlFor="age">Age</label>
          <input id="age" name="age" type="number" min={8} max={25} />
        </div>

        <div className="field">
          <label htmlFor="gender">Gender</label>
          <select id="gender" name="gender" defaultValue="prefer_not_to_say">
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="other">Other</option>
          <option value="prefer_not_to_say">Prefer not to say</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="locale">Language</label>
          <select id="locale" name="locale" defaultValue="en">
            <option value="en">English</option>
            <option value="ta">தமிழ்</option>
            <option value="hi">हिन्दी</option>
          </select>
        </div>

        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy} style={{ marginTop: 8, width: "100%" }}>
          {busy ? "Starting…" : "Start the questionnaire"}
        </button>
      </form>
    </main>
  );
}
