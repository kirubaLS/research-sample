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

import {
  BookOpenCheck, ClipboardCheck, GraduationCap, LayoutDashboard, Sparkles, Target,
} from "lucide-react";
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

const FEATURES = [
  {
    icon: Sparkles,
    title: "Interest profiling",
    body: "A validated six-type inventory, scored with the person's own baseline removed, and withheld entirely when a profile is too flat to call.",
  },
  {
    icon: Target,
    title: "Question-level diagnosis",
    body: "Every mark maps to a chapter, a sub-topic and a cognitive tier, so “weak in Surface Areas” becomes “knows the formula, can’t apply it”.",
  },
  {
    icon: BookOpenCheck,
    title: "Paper quality",
    body: "Whether the paper matches the board's own balance of recall, application and analysis, and which chapters it never tested at all.",
  },
];

export default function Home() {
  return (
    <main>
      <motion.section
        className="hero-bleed"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.7, ease: EASE }}
      >
        <div className="hero-atmosphere" aria-hidden />
        <div className="hero-blob hero-blob-a" aria-hidden />
        <div className="hero-blob hero-blob-b" aria-hidden />
        <div className="hero-inner">
          <motion.div
            className="hero-copy"
            initial="hidden"
            animate="show"
            variants={rise}
          >
            <p className="eyebrow">CBSE Class X · Tamil Nadu</p>
            <h1>
              Turn a mark sheet into
              <br />
              something a teacher can act on.
            </h1>
            <p className="lede">
              Avai reads question-level performance and says where marks were lost, whether
              the gap is recall or application, and which concepts need reteaching, plus an
              interest profile that helps a student choose a stream.
            </p>
          </motion.div>
          <motion.div
            className="hero-frame"
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.15, ease: EASE }}
            whileHover={{ y: -4 }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/brand/hero-banner.png"
              alt="Avai mascot, standing on a stack of books labelled Higher Marks, New Opportunities, Brighter Futures, with a path leading toward Learn, Improve, Explore, Achieve"
            />
          </motion.div>
        </div>
      </motion.section>

      <div className="grid two" style={{ marginTop: 30 }}>
        <motion.div className="mo" initial="hidden" whileInView="show" viewport={{ once: true }} custom={0} variants={rise}>
          <Link href="/t" className="card accentbar doorcard">
            <span className="dooricon student" aria-hidden>
              <GraduationCap size={22} />
            </span>
            <p className="eyebrow">For students</p>
            <h2>Take the interest test</h2>
            <p className="cardnote" style={{ marginBottom: 16 }}>
              36 short questions, about eight minutes, in English, தமிழ் or हिन्दी. There are no
              right or wrong answers, and there is no login.
            </p>
            <span className="arrow">Find your class →</span>
          </Link>
        </motion.div>

        <motion.div className="mo" initial="hidden" whileInView="show" viewport={{ once: true }} custom={1} variants={rise}>
          <Link href="/login" className="card accentbar verify doorcard">
            <span className="dooricon staff" aria-hidden>
              <LayoutDashboard size={22} />
            </span>
            <p className="eyebrow" style={{ color: "var(--verify)" }}>
              For principals, staff and students
            </p>
            <h2>Sign in</h2>
            <p className="cardnote" style={{ marginBottom: 16 }}>
              Class links, marks entry and BoardX for staff; roll number + PIN for a
              student viewing a report their teacher has shared.
            </p>
            <span className="arrow">Sign in →</span>
          </Link>
        </motion.div>
      </div>

      <div className="section-head">
        <h2>What it does</h2>
      </div>
      <div className="grid three">
        {FEATURES.map(({ icon: Icon, title, body }, i) => (
          <motion.div
            key={title}
            className="card featurecard mo"
            initial="hidden"
            whileInView="show"
            viewport={{ once: true }}
            custom={i}
            variants={rise}
            whileHover={{ y: -3 }}
          >
            <span className="featureicon" aria-hidden>
              <Icon size={20} />
            </span>
            <h3>{title}</h3>
            <p className="cardnote">{body}</p>
          </motion.div>
        ))}
      </div>

      <style jsx>{`
        /* framer-motion drives this page's entrance directly (variants={rise}), so the
           global .grid > * CSS keyframe -- meant for pages with no JS-driven animation of
           their own -- is switched off here to stop two animation systems fighting over
           the same transform/opacity on one element. */
        .grid > .mo { animation: none; }
        .doorcard { position: relative; }
        .dooricon {
          width: 40px; height: 40px; border-radius: var(--radius-sm);
          display: grid; place-items: center; margin-bottom: 14px;
        }
        .dooricon.student { background: var(--mark-soft); color: var(--mark); }
        .dooricon.staff { background: var(--verify-soft); color: var(--verify); }
        .featurecard { position: relative; }
        .featureicon {
          display: inline-grid; place-items: center; width: 36px; height: 36px;
          border-radius: var(--radius-sm); background: var(--info-soft); color: var(--info);
          margin-bottom: 10px;
        }
      `}</style>
    </main>
  );
}
