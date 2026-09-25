"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Mascot, Wordmark } from "@/components/Mascot";
import { EASE_OUT } from "@/components/motion";
import { homeFor, useAuth } from "@/lib/auth";
import { getSchoolName } from "@/lib/session";

/** "/" is a router, not a screen, but it is the first paint, so it carries
 *  the brand while auth resolves from storage. */
export default function Index() {
  const { user, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    router.replace(user ? homeFor(user) : "/login");
  }, [ready, user, router]);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        padding: 24,
        textAlign: "center",
        color: "#fff",
        background:
          "radial-gradient(720px 520px at 20% 12%, rgba(31,138,138,.5), transparent 62%)," +
          "radial-gradient(620px 520px at 92% 96%, rgba(29,95,208,.42), transparent 64%)," +
          "radial-gradient(420px 340px at 84% 16%, rgba(240,147,43,.2), transparent 62%)," +
          "linear-gradient(160deg, #1c2f39, #0d191f)",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE_OUT }}
        style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}
      >
        <Mascot pose="hello" size={132} float />
        <Wordmark height={40} onDark />
      </motion.div>

      <motion.div
        className="small"
        style={{ color: "#b9c6ce", fontWeight: 600 }}
        animate={{ opacity: [0.5, 1, 0.5] }}
        transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
      >
        Preparing your workspace…
      </motion.div>

      <div style={{ width: 150, height: 4, borderRadius: 999, background: "rgba(255,255,255,.14)", overflow: "hidden" }}>
        <motion.div
          style={{ width: "40%", height: "100%", borderRadius: 999, background: "linear-gradient(90deg, var(--brand-teal), var(--brand-blue))" }}
          animate={{ x: ["-100%", "250%"] }}
          transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
        />
      </div>

      {getSchoolName() && (
        <div style={{ color: "#8b99a3", fontSize: 12.5 }}>{getSchoolName()}</div>
      )}
    </div>
  );
}
