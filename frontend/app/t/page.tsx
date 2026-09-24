"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ClassOption } from "@/lib/api";
import { GrowthIllustration } from "@/components/GrowthIllustration";

/**
 * The student front door.
 *
 * A class code is not a secret — it goes on the whiteboard — and a student who mistypes
 * one has no other way in, so the classes are listed here and the link is a real link.
 */
export default function ClassPicker() {
  const [classes, setClasses] = useState<ClassOption[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .classes()
      .then(setClasses)
      .catch(() => setError("Could not reach the server. Check your connection and reload."));
  }, []);

  const schools = new Map<string, ClassOption[]>();
  for (const c of classes ?? []) {
    schools.set(c.school, [...(schools.get(c.school) ?? []), c]);
  }

  return (
    <main className="content" style={{ maxWidth: 960 }}>
      <div
        style={{
          display: "flex", alignItems: "center", gap: 28, flexWrap: "wrap", marginTop: 20,
        }}
      >
        <div style={{ flex: "1 1 320px", minWidth: 0 }}>
          <p className="eyebrow">Interest test</p>
          <h1 className="page-title" style={{ marginTop: 6 }}>Find your class</h1>
          <p className="page-sub" style={{ fontSize: 14.5, maxWidth: 520 }}>
            Tap your class to begin. 36 short questions, about eight minutes, in English,
            தமிழ் or हिन्दी. There are no right or wrong answers, and no login.
          </p>
        </div>
        <div style={{ flex: "0 1 260px", minWidth: 180, maxWidth: 260 }}>
          <GrowthIllustration />
        </div>
      </div>

      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 20 }}>
          <div>{error}</div>
        </div>
      )}
      {!classes && !error && <p className="muted small" style={{ marginTop: 20 }}>Loading classes…</p>}
      {classes?.length === 0 && (
        <div className="evidence evidence--neutral" style={{ marginTop: 20 }}>
          No classes have been set up yet. Ask your teacher for the class link.
        </div>
      )}

      {[...schools.entries()].map(([school, options]) => (
        <section className="section" key={school}>
          <div className="section__head">
            <h2 className="section-q">{school}</h2>
          </div>
          <div className="grid grid--3">
            {options.map((option) => (
              <Link
                key={option.class_code}
                href={`/t/${option.class_code}`}
                className="card card--hover"
              >
                <div className="card__body">
                  <h3 style={{ fontSize: 16, fontWeight: 650 }}>{option.label}</h3>
                  <span
                    className="btn--link"
                    style={{ display: "inline-flex", alignItems: "center", gap: 4, marginTop: 10 }}
                  >
                    Start the test →
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
