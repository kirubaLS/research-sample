"use client";

/**
 * The front door. Two audiences, two doors — the previous version described them in prose
 * and offered no way in.
 *
 * framer-motion drives the entrance (a staggered rise, matching the timing the rest of the
 * app already commits to via --ease/--dur-slow) and the card hover lift; lucide-react gives
 * every card a crisp vector icon instead of a bare heading, and the hero art is the real
 * Avai brand banner (frontend/public/brand/hero-banner.png, cropped from the designer's
 * reference sheet) rather than a hand-drawn placeholder.
 */

import { ArrowRight, GraduationCap, LayoutDashboard } from "lucide-react";
import { motion } from "framer-motion";
import Link from "next/link";

const EASE = [0.16, 1, 0.3, 1] as const;

const rise = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number = 0) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.5, delay: i * 0.08, ease: EASE },
  }),
};

export default function Home() {
  return (
    <main className="content" style={{ maxWidth: 960 }}>
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.7, ease: EASE }}
        style={{ marginTop: 20 }}
      >
        <div style={{ display: "flex", gap: 32, alignItems: "center", flexWrap: "wrap" }}>
          <motion.div
            initial="hidden"
            animate="show"
            variants={rise}
            style={{ flex: "1 1 380px", minWidth: 0 }}
          >
            <p className="eyebrow">CBSE Class X · Tamil Nadu</p>
            <h1 className="page-title" style={{ fontSize: 34, marginTop: 8, lineHeight: 1.2 }}>
              Turn a mark sheet into something a teacher can act on.
            </h1>
            <p className="page-sub" style={{ fontSize: 15, marginTop: 12, maxWidth: 520 }}>
              Avai reads question-level performance and says where marks were lost, whether
              the gap is recall or application, and which concepts need reteaching, plus an
              interest profile that helps a student choose a stream.
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.15, ease: EASE }}
            whileHover={{ y: -4 }}
            style={{ flex: "1 1 280px", minWidth: 220, maxWidth: 380 }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/brand/hero-banner.png"
              alt="Avai mascot, standing on a stack of books labelled Higher Marks, New Opportunities, Brighter Futures, with a path leading toward Learn, Improve, Explore, Achieve"
              style={{ width: "100%", height: "auto", display: "block" }}
            />
          </motion.div>
        </div>
      </motion.section>

      <div className="grid grid--2" style={{ marginTop: 30 }}>
        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} custom={0} variants={rise}>
          <Link href="/t" className="card card--hover" style={{ "--accent": "var(--brand-teal)" } as React.CSSProperties}>
            <div className="card__body">
              <span
                aria-hidden
                style={{
                  width: 40, height: 40, borderRadius: "var(--radius-sm)",
                  display: "grid", placeItems: "center", marginBottom: 14,
                  background: "var(--brand-teal-soft)", color: "var(--brand-teal)",
                }}
              >
                <GraduationCap size={22} />
              </span>
              <p className="eyebrow">For students</p>
              <h2 style={{ marginTop: 4 }}>Take the interest test</h2>
              <span className="btn--link" style={{ display: "inline-flex", alignItems: "center", gap: 4, marginTop: 10 }}>
                Find your class <ArrowRight size={14} />
              </span>
            </div>
          </Link>
        </motion.div>

        <motion.div initial="hidden" whileInView="show" viewport={{ once: true }} custom={1} variants={rise}>
          <Link href="/login" className="card card--hover" style={{ "--accent": "var(--brand-blue)" } as React.CSSProperties}>
            <div className="card__body">
              <span
                aria-hidden
                style={{
                  width: 40, height: 40, borderRadius: "var(--radius-sm)",
                  display: "grid", placeItems: "center", marginBottom: 14,
                  background: "var(--brand-blue-soft)", color: "var(--brand-blue)",
                }}
              >
                <LayoutDashboard size={22} />
              </span>
              <p className="eyebrow" style={{ color: "var(--brand-blue)" }}>
                For principals, staff and students
              </p>
              <h2 style={{ marginTop: 4 }}>Sign in</h2>
              <span className="btn--link" style={{ display: "inline-flex", alignItems: "center", gap: 4, marginTop: 10 }}>
                Sign in <ArrowRight size={14} />
              </span>
            </div>
          </Link>
        </motion.div>
      </div>
    </main>
  );
}
