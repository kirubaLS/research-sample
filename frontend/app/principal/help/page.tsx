"use client";

/**
 * Help & Contact -- the reference page's own two-card layout (a "reach us" card beside
 * a FAQ list), but this deployment has no support inbox/phone number wired up yet and
 * no message-submission endpoint, so nothing here is invented. The "reach us" card and
 * FAQ copy are carried over verbatim from the placeholder this app shipped with before
 * the clone: once a real support email/phone (or an in-app ticket endpoint) exists, wire
 * it in here in place of the "ask your AVAI account contact" placeholder below.
 */

import { usePageHeader } from "@/lib/pageHeader";

const FAQS: { q: string; a: string }[] = [
  {
    q: "A score or status looks wrong -- what should I check first?",
    a: "Every score on these screens is read straight from a recorded mark. Open the student or test it came from and check the individual paper -- if a mark was entered incorrectly, it needs to be corrected at the source (Enter Marks or Scan Answer Sheets), and every screen that shows it will update.",
  },
  {
    q: 'Why does a class show "Not Yet Assessed" for some students?',
    a: 'A student is only counted once a paper has a recorded mark for them. "Not Yet Assessed" means no test in the selected range has a mark on file for that student yet.',
  },
  {
    q: "How do I get a class or test report as a file?",
    a: "Use the \"Download PDF\" or \"Download Excel\" button at the top of the Classes, Exams and Share screens -- each downloads exactly what's on screen, including any filters you've applied.",
  },
  {
    q: "Who do I contact about a data or account issue?",
    a: "Reach your AVAI account contact directly -- the person who set up this school's AVAI account. They can escalate anything that needs a fix on AVAI's side.",
  },
];

export default function HelpPage() {
  usePageHeader({ title: "Help & Contact" });

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Answers to common questions, and how to reach AVAI about anything else.
      </p>

      <div className="grid grid--2" style={{ marginTop: 20, alignItems: "start" }}>
        <div className="card">
          <div className="card__head">
            <h3 style={{ fontSize: 16 }}>Reach us</h3>
          </div>
          <div className="card__body">
            <p className="small muted" style={{ margin: 0 }}>
              For anything not answered below, reach out to your AVAI account contact -- the person who set up this
              school&apos;s AVAI account. They can route data or account issues to the AVAI team on your behalf.
            </p>
          </div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">Common questions</h2>
        </div>
        <div className="grid" style={{ gap: 12 }}>
          {FAQS.map((f) => (
            <div className="card card--flat" key={f.q}>
              <div className="card__body">
                <div className="strong">{f.q}</div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {f.a}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
