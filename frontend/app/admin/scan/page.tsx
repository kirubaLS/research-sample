"use client";

import { useState } from "react";
import { Scanner } from "@/components/Scanner";
import type { ScannedPage } from "@/lib/pageStore";

export default function ScanPage() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [mode, setMode] = useState<"cover" | "script">("cover");
  const [status, setStatus] = useState<string | null>(null);

  async function upload(pages: ScannedPage[]) {
    // The server route that receives a script does not exist yet. It used to be called
    // here with .catch(() => undefined), which swallowed every failure and then reported
    // "the script will appear on the student's record" -- a success message for work that
    // had not happened. That is the one thing this product must never do, so the screen
    // now says exactly where the pages are: captured, held in this browser, not sent.
    setStatus(
      `${pages.length} page${pages.length === 1 ? "" : "s"} captured and held on this device. ` +
        "They are not on the server yet: reading a script is not switched on. Nothing is " +
        "lost, and nothing has been recorded against a student.",
    );
    if (mode === "cover") setMode("script");
  }

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Answer scripts</p>
        <h1>{mode === "cover" ? "Scan the cover page" : "Scan every page"}</h1>
      </div>
      <div className="notice warn" style={{ marginBottom: 18 }}>
        Reading a script is not switched on yet. Capture works and every page is kept on
        this device, but nothing is sent to the server and no mark is recorded against a
        student. Marks are entered on the Answer sheet screen in the meantime.
      </div>
      <p className="lede" style={{ marginBottom: 20 }}>
        {mode === "cover"
          ? "The cover carries the question numbers and marks. One clear frame is enough."
          : "Capture each page in order. Retake replaces a single page and keeps its position."}
      </p>
      <div className="card">
        <Scanner sessionId={sessionId} mode={mode} onComplete={upload} />
      </div>
      {status && <p className="notice" style={{ marginTop: 14 }}>{status}</p>}
    </main>
  );
}
