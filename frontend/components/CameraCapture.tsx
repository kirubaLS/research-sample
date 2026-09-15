"use client";

import { useEffect, useRef, useState } from "react";

/**
 * One live photo, taken on the spot, for a screen that only ever needs a single frame --
 * unlike Scanner.tsx's multi-page answer-script capture (its own quality gate and
 * undo/redo history exist because a script is many pages taken in sequence), a class
 * mark-entry sheet is one photograph of one piece of paper.
 *
 * Opens the camera, shows a live preview, freezes a captured frame for a look before it is
 * used, and hands the caller a real File -- the same shape a file-picker would have
 * produced, so nothing downstream needs to know a camera was involved at all.
 */
export function CameraCapture({
  onCapture,
  onCancel,
}: {
  onCapture: (file: File) => void;
  onCancel: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [frozen, setFrozen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stream: MediaStream | null = null;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        });
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch {
        setError("Could not open the camera. Check the browser has permission, or choose a file instead.");
      }
    })();
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function shoot() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    setFrozen(canvas.toDataURL("image/jpeg", 0.92));
  }

  function useIt() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob(
      (blob) => {
        if (blob) onCapture(new File([blob], `mark-entry-sheet-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }

  return (
    <div className="camerawrap">
      {error && <p className="error">{error}</p>}
      {!error && !frozen && <video ref={videoRef} autoPlay playsInline muted />}
      {frozen && <img src={frozen} alt="Captured sheet, not yet used" />}
      <canvas ref={canvasRef} style={{ display: "none" }} />
      <div className="camerabtns">
        {!frozen && !error && (
          <button type="button" onClick={shoot}>
            Capture
          </button>
        )}
        {frozen && (
          <>
            <button type="button" className="secondary" onClick={() => setFrozen(null)}>
              Retake
            </button>
            <button type="button" onClick={useIt}>
              Use this photo
            </button>
          </>
        )}
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>

      <style jsx>{`
        .camerawrap { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
        video, img { width: 100%; border-radius: var(--radius, 10px); background: #0c0f12; display: block; }
        .camerabtns { display: flex; gap: 8px; flex-wrap: wrap; }
      `}</style>
    </div>
  );
}
