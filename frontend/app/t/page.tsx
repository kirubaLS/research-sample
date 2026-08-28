"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ClassOption } from "@/lib/api";

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
    <main>
      <div className="hero">
        <p className="eyebrow">Interest test</p>
        <h1>Find your class</h1>
        <p className="lede">
          Tap your class to begin. 36 short questions, about eight minutes, in English,
          தமிழ் or हिन्दी. There are no right or wrong answers, and no login.
        </p>
      </div>

      {error && <div className="notice warn">{error}</div>}
      {!classes && !error && <p className="cardnote">Loading classes…</p>}
      {classes?.length === 0 && (
        <div className="notice">
          No classes have been set up yet. Ask your teacher for the class link.
        </div>
      )}

      {[...schools.entries()].map(([school, options]) => (
        <section key={school}>
          <div className="section-head">
            <h2>{school}</h2>
          </div>
          <div className="grid three">
            {options.map((option) => (
              <Link key={option.class_code} href={`/t/${option.class_code}`} className="card accentbar">
                <h3>{option.label}</h3>
                <span className="arrow">Start the test →</span>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
