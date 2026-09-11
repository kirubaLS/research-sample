"use client";

/**
 * The front door. Two audiences, two doors — the previous version described them in prose
 * and offered no way in.
 *
 * framer-motion drives the entrance (a staggered rise, matching the timing the rest of the
 * app already commits to via --ease/--dur-slow) and the card hover lift; lucide-react gives
 * every card a crisp vector icon instead of a bare heading, and HeroIllustration is the
 * one hand-drawn scene, matching the same idea GrowthIllustration already carries on the
 * student side: a mark sheet becomes something actionable.
 */

import {
  BookOpenCheck, ClipboardCheck, GraduationCap, LayoutDashboard, Sparkles, Target,
} from "lucide-react";
import { motion } from "framer-motion";
import Link from "next/link";
import { HeroIllustration } from "@/components/HeroIllustration";

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
      <div className="hero heroflex">
        <motion.div
          className="herocopy"
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
            Yaadhum reads question-level performance and says where marks were lost, whether
            the gap is recall or application, and which concepts need reteaching, plus an
            interest profile that helps a student choose a stream.
          </p>
        </motion.div>
        <motion.div
          className="heroart"
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.15, ease: EASE }}
        >
          <HeroIllustration />
        </motion.div>
      </div>

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
          <Link href="/admin" className="card accentbar verify doorcard">
            <span className="dooricon staff" aria-hidden>
              <LayoutDashboard size={22} />
            </span>
            <p className="eyebrow" style={{ color: "var(--verify)" }}>
              For principals and staff
            </p>
            <h2>Open the dashboard</h2>
            <p className="cardnote" style={{ marginBottom: 16 }}>
              Class links to hand out, who has finished, each student&apos;s interest profile,
              and the answer-script scanner.
            </p>
            <span className="arrow">Sign in with your school key →</span>
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
        .heroflex {
          display: flex; align-items: center; gap: 36px; flex-wrap: wrap;
        }
        .herocopy { flex: 1 1 360px; min-width: 0; }
        .heroart { flex: 1 1 280px; max-width: 380px; min-width: 220px; margin: 0 auto; }
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
        @media (max-width: 760px) {
          .heroflex { flex-direction: column; }
          .heroart { max-width: 300px; }
        }
      `}</style>
    </main>
  );
}
