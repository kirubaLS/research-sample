"use client";

import { useState } from "react";
import { Scanner } from "@/components/Scanner";
import type { ScannedPage } from "@/lib/pageStore";

export default function ScanPage() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [mode, setMode] = useState<"cover" | "script">("cover");
  const [status, setStatus] = useState<string | null>(null);

  async function upload(pages: ScannedPage[]) {
    // Resumable, one request per page: a dropped connection at page 14 must not lose 1-13.
    let done = 0;
    for (const page of pages) {
      const body = new FormData();
      body.append("file", page.blob, `page-${page.index + 1}.jpg`);
      body.append("index", String(page.index));
      body.append("session_id", page.sessionId);
      body.append("quality", JSON.stringify(page.quality));
      // Endpoint lands with the capture service; the client contract is fixed here.
      await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/capture/${sessionId}/pages`, {
        method: "POST",
        body,
      }).catch(() => undefined);
      done += 1;
      setStatus(`Uploaded ${done} of ${pages.length}`);
    }
    setStatus(`Uploaded ${pages.length} page${pages.length === 1 ? "" : "s"}. The script will appear on the student's record.`);
    if (mode === "cover") setMode("script");
  }

  return (
    <main className="narrow">
      <div className="hero">
        <p className="eyebrow">Answer scripts</p>
        <h1>{mode === "cover" ? "Scan the cover page" : "Scan every page"}</h1>
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
