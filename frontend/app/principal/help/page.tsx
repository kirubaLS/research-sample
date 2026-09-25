"use client";

/**
 * Help & Contact -- the reference page's own two-card layout (a "reach us" card beside
 * a "message us" form), but this deployment has no support inbox/phone number wired up
 * yet and no message-submission endpoint, so both are labelled "Demo only" rather than
 * presented as real -- exactly what the reference's own "demo only" caption already
 * says under its message form. Once a real support email/phone or an in-app ticket
 * endpoint exists, wire it in here in place of the demo values below.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { Mail, MessageCircle, Phone, Send } from "lucide-react";
import { EASE_OUT } from "@/components/motion";
import { usePageHeader } from "@/lib/pageHeader";
import { useAuth } from "@/lib/auth";

const FAQS: { q: string; a: string }[] = [
  {
    q: "A student's marks look wrong, what do I do?",
    a: "Open Enter Marks for that assessment and correct the question-wise score; every report and KPI that depends on it updates immediately.",
  },
  {
    q: 'Why does a chapter say "Not enough evidence"?',
    a: "That chapter wasn't tested enough in the mapped papers to say anything reliable about it yet, map a paper against it to change that.",
  },
  {
    q: "Can I undo sending a report to students?",
    a: "Not from here, check the test before sending. Message us below if a report needs to be recalled.",
  },
  {
    q: "How do I get a class or test report as a file?",
    a: "Use the \"Download report\" button at the top of a class or student screen -- it downloads exactly what's on screen, including any filters you've applied.",
  },
];

const TOPICS = ["A number looks wrong", "A report or share issue", "Account or access", "Something else"];

export default function HelpPage() {
  usePageHeader({ title: "Help & Contact" });
  const { user } = useAuth();
  const actorName = user && "name" in user && user.name ? user.name : "your account";
  const [topic, setTopic] = useState(TOPICS[0]);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);

  function send(e: React.FormEvent) {
    e.preventDefault();
    // No message-submission endpoint exists in this deployment -- shown once, nothing
    // is actually transmitted, matching the reference's own "demo only" caption.
    setSent(true);
  }

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>
        Something not working, or a number that looks wrong? Tell us and we&apos;ll take a look.
      </p>

      <div className="grid grid--2" style={{ marginTop: 20, alignItems: "start", gap: 16 }}>
        <motion.div className="card card--hover" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE_OUT }}>
          <div className="card__head">
            <h3 style={{ fontSize: 16 }}>Reach us directly</h3>
          </div>
          <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="surface surface--tinted" style={{ "--accent": "var(--brand-teal)", display: "flex", alignItems: "center", gap: 12, padding: "12px 14px" } as React.CSSProperties}>
              <span className="kpi__icon" style={{ width: 36, height: 36, flexBasis: 36, borderRadius: 10 }}>
                <Mail size={16} />
              </span>
              <div style={{ minWidth: 0 }}>
                <strong style={{ display: "block", fontSize: 13.5, fontWeight: 650 }}>Email support</strong>
                <small className="muted" style={{ display: "block", fontSize: 12 }}>support@avai.school</small>
              </div>
            </div>
            <div className="surface surface--tinted" style={{ "--accent": "var(--brand-blue)", display: "flex", alignItems: "center", gap: 12, padding: "12px 14px" } as React.CSSProperties}>
              <span className="kpi__icon" style={{ width: 36, height: 36, flexBasis: 36, borderRadius: 10 }}>
                <Phone size={16} />
              </span>
              <div style={{ minWidth: 0 }}>
                <strong style={{ display: "block", fontSize: 13.5, fontWeight: 650 }}>Call support</strong>
                <small className="muted" style={{ display: "block", fontSize: 12 }}>+91 44 4567 8900 · Mon-Sat, 9:00 AM - 6:00 PM IST</small>
              </div>
            </div>
            <p className="small muted" style={{ margin: 0 }}>
              Demo only, these details don&apos;t connect to a real support line yet.
            </p>
          </div>
        </motion.div>

        <motion.div className="card card--hover" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.06, ease: EASE_OUT }}>
          <div className="card__head">
            <h3 style={{ fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
              <MessageCircle size={16} /> Message us
            </h3>
          </div>
          <div className="card__body">
            <form onSubmit={send} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="field">
                <label htmlFor="help-topic">What&apos;s this about?</label>
                <select id="help-topic" className="select" value={topic} onChange={(e) => setTopic(e.target.value)}>
                  {TOPICS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="help-message">Message</label>
                <textarea
                  id="help-message"
                  className="input"
                  rows={4}
                  placeholder="Tell us what you're seeing, the page, the class or student, and what looks off."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
              </div>
              <button type="submit" className="btn btn--primary" disabled={!message.trim() || sent} style={{ alignSelf: "flex-end" }}>
                <Send size={14} /> {sent ? "Sent" : "Send message"}
              </button>
              <p className="small muted" style={{ margin: 0, textAlign: "right" }}>
                Sent as {actorName} · demo only, nothing leaves this session.
              </p>
            </form>
          </div>
        </motion.div>
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">Common questions</h2>
        </div>
        <div className="grid" style={{ gap: 12 }}>
          {FAQS.map((f, i) => (
            <motion.div
              className="card card--flat card--hover"
              key={f.q}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.04 * i, ease: EASE_OUT }}
            >
              <div className="card__body">
                <div className="strong">{f.q}</div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  {f.a}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </section>
    </>
  );
}
