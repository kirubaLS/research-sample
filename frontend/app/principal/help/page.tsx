"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Mail, MessageCircle, Phone, Send } from "lucide-react";
import { helpContact, pageHeaders } from "@/lib/avai-mock-data";
import { useAuth } from "@/lib/auth";
import { usePageHeader } from "@/lib/pageHeader";

const categories = ["A number looks wrong", "Something isn't working", "A feature I need", "Something else"];

/** Help & Contact, replaces the old Settings screen. Nothing here is
 * configuration; it's the one place to reach AVAI when a number looks
 * wrong or something breaks. The message form is local-only: it confirms
 * with a toast and nothing is actually sent anywhere. */
export default function HelpPage() {
  usePageHeader({ title: pageHeaders.help.title });
  const { user } = useAuth();
  const [category, setCategory] = useState(categories[0]);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2800);
    return () => clearTimeout(t);
  }, [toast]);

  function send() {
    if (!message.trim()) return;
    setSent(true);
    setToast("Message sent to AVAI support (demo only), we'll follow up by email.");
    setMessage("");
    setTimeout(() => setSent(false), 2400);
  }

  return (
    <>
      <p className="page-sub" style={{ marginTop: 0 }}>{pageHeaders.help.blurb}</p>

      <div className="grid grid--2" style={{ marginTop: 20, alignItems: "start" }}>
        <div className="card">
          <div className="card__head">
            <h3 style={{ fontSize: 16 }}>Reach us directly</h3>
          </div>
          <div className="card__body" style={{ display: "grid", gap: 14 }}>
            <a href={`mailto:${helpContact.supportEmail}`} className="subject-row">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Mail size={16} className="muted" />
                <div>
                  <div className="strong">Email support</div>
                  <div className="small muted">{helpContact.supportEmail}</div>
                </div>
              </div>
            </a>
            <a href={`tel:${helpContact.supportPhone.replace(/\s+/g, "")}`} className="subject-row">
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Phone size={16} className="muted" />
                <div>
                  <div className="strong">Call support</div>
                  <div className="small muted">
                    {helpContact.supportPhone} · {helpContact.hours}
                  </div>
                </div>
              </div>
            </a>
          </div>
          <div className="card__foot small muted">Demo only, these details don&apos;t connect to a real support line yet.</div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 style={{ fontSize: 16, display: "flex", alignItems: "center", gap: 8 }}>
              <MessageCircle size={16} /> Message us
            </h3>
          </div>
          <div className="card__body" style={{ display: "grid", gap: 14 }}>
            <div className="field">
              <label htmlFor="help-category">What&apos;s this about?</label>
              <select id="help-category" className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="help-message">Message</label>
              <textarea
                id="help-message"
                className="input"
                rows={5}
                placeholder="Tell us what you're seeing, the page, the class or student, and what looks off."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn--primary" disabled={!message.trim() || sent} onClick={send}>
                <Send size={13} /> {sent ? "Sent" : "Send message"}
              </button>
            </div>
          </div>
          <div className="card__foot small muted">Sent as {user?.name ?? "you"} · demo only, nothing leaves this session.</div>
        </div>
      </div>

      <section className="section">
        <div className="section__head">
          <h2 className="section-q">Common questions</h2>
        </div>
        <div className="grid" style={{ gap: 12 }}>
          {helpContact.faqs.map((f) => (
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

      <AnimatePresence>
        {toast && (
          <motion.div className="toast" role="status" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }}>
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
