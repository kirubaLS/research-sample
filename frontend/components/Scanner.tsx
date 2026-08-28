"use client";

/**
 * The multi-page answer-script scanner.
 *
 * Two features share this component:
 *   Feature 1 — a single frame of the cover page carrying question numbers and marks
 *   Feature 2 — every page of the script, with per-page retake
 *
 * Two details carry the whole UX:
 *   * the shutter stays locked until all four quality metrics pass
 *   * RETAKE re-shoots one page and KEEPS its position in the sequence. A scanner that
 *     makes a teacher restart the script is a scanner they abandon on the third student.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { assess, type QualityReport } from "@/lib/quality";
import { deletePage, listPages, purgeStale, putPage, type ScannedPage } from "@/lib/pageStore";

type Mode = "cover" | "script";

interface Props {
  sessionId: string;
  mode: Mode;
  onComplete: (pages: ScannedPage[]) => Promise<void> | void;
}

export function Scanner({ sessionId, mode, onComplete }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pages, setPages] = useState<ScannedPage[]>([]);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [retakeIndex, setRetakeIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setPages(await listPages(sessionId));
  }, [sessionId]);

  useEffect(() => {
    void purgeStale();
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let stream: MediaStream | null = null;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 2560 }, height: { ideal: 1440 } },
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
      } catch {
        setError("Camera unavailable. Check the browser's camera permission for this site.");
      }
    })();
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  // the quality gate: ~10 fps on a downscaled frame
  useEffect(() => {
    const timer = window.setInterval(() => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState < 2) return;
      const w = 240;
      const h = Math.round((video.videoHeight / video.videoWidth) * w) || 320;
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, w, h);
      setQuality(assess(ctx.getImageData(0, 0, w, h)));
    }, 100);
    return () => window.clearInterval(timer);
  }, []);

  async function capture() {
    const video = videoRef.current;
    if (!video || !quality) return;
    setBusy(true);
    try {
      const full = document.createElement("canvas");
      full.width = video.videoWidth;
      full.height = video.videoHeight;
      full.getContext("2d")!.drawImage(video, 0, 0);
      const blob: Blob = await new Promise((resolve) =>
        full.toBlob((b) => resolve(b!), "image/jpeg", 0.92),
      );

      const thumbCanvas = document.createElement("canvas");
      thumbCanvas.width = 168;
      thumbCanvas.height = 224;
      thumbCanvas.getContext("2d")!.drawImage(video, 0, 0, 168, 224);

      const index = retakeIndex ?? pages.length;
      await putPage({
        sessionId,
        index,
        blob,
        thumbnail: thumbCanvas.toDataURL("image/jpeg", 0.6),
        quality: {
          blur: quality.blur, glare: quality.glare,
          coverage: quality.coverage, skew: quality.skew, band: quality.band,
        },
        capturedAt: Date.now(),
        uploaded: false,
      });
      setRetakeIndex(null);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const shutterEnabled = Boolean(quality?.passed) && !busy;
  const weakPages = pages.filter((p) => p.quality.band !== "green");

  return (
    <div>
      <video ref={videoRef} playsInline muted />
      <canvas ref={canvasRef} style={{ display: "none" }} />

      <div className="row" style={{ justifyContent: "space-between", padding: "10px 0" }}>
        <span className={`badge ${quality?.band ?? "red"}`}>
          {quality?.passed ? "ready" : (quality?.failures.join(" · ") || "focusing")}
        </span>
        <span className="muted" style={{ fontSize: 13 }}>
          {retakeIndex !== null
            ? `Retaking page ${retakeIndex + 1}`
            : mode === "cover"
              ? "Cover page"
              : `Page ${pages.length + 1}`}
        </span>
      </div>

      <div className="row">
        <button onClick={capture} disabled={!shutterEnabled}>
          {retakeIndex !== null ? "Replace page" : "Capture"}
        </button>
        {retakeIndex !== null && (
          <button className="secondary" onClick={() => setRetakeIndex(null)}>
            Cancel retake
          </button>
        )}
      </div>
      {!quality?.passed && quality && (
        <p className="muted" style={{ fontSize: 13 }}>
          Hold steady and fill the frame with the page. The button unlocks when the photo is
          good enough to read.
        </p>
      )}
      {error && <p className="error">{error}</p>}

      <div className="strip">
        {pages.map((p) => (
          <div key={p.index} className={`thumb ${p.quality.band}`}>
            <span className="n">{p.index + 1}</span>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p.thumbnail} alt={`Page ${p.index + 1}`} />
            <div className="row" style={{ gap: 4, marginTop: 4 }}>
              <button
                className="secondary"
                style={{ padding: "4px 6px", fontSize: 11 }}
                onClick={() => setRetakeIndex(p.index)}
              >
                Retake
              </button>
              <button
                className="secondary"
                style={{ padding: "4px 6px", fontSize: 11 }}
                onClick={async () => {
                  await deletePage(sessionId, p.index);
                  await refresh();
                }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {weakPages.length > 0 && (
        <p className="muted" style={{ fontSize: 13 }}>
          {weakPages.length} page(s) marked for a possible retake — you can continue, but a
          clearer photo reads more reliably.
        </p>
      )}

      <p style={{ marginTop: 18 }}>
        <button
          onClick={async () => {
            setBusy(true);
            try {
              await onComplete(pages);
            } finally {
              setBusy(false);
            }
          }}
          disabled={pages.length === 0 || busy}
        >
          Complete ({pages.length} page{pages.length === 1 ? "" : "s"})
        </button>
      </p>
    </div>
  );
}
