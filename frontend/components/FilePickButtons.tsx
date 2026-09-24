"use client";

import { useRef } from "react";
import { Camera, Upload } from "lucide-react";

/** "Take photo" opens the rear camera directly on a phone (capture=environment);
 * on a laptop it falls back to a normal image picker. */
export function FilePickButtons({
  onPick,
  accept,
  disabled,
  size = "md",
  fileLabel = "Choose file",
}: {
  onPick: (file: File) => void;
  accept: string;
  disabled?: boolean;
  size?: "sm" | "md";
  fileLabel?: string;
}) {
  const cameraRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function handle(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) onPick(file);
  }

  const cls = `btn ${size === "sm" ? "btn--sm" : ""}`;
  return (
    <div className="pickbtns">
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={handle} />
      <input ref={fileRef} type="file" accept={accept} hidden onChange={handle} />
      <button type="button" className={`${cls} btn--primary`} onClick={() => cameraRef.current?.click()} disabled={disabled}>
        <Camera size={size === "sm" ? 13 : 15} /> Take photo
      </button>
      <button type="button" className={cls} onClick={() => fileRef.current?.click()} disabled={disabled}>
        <Upload size={size === "sm" ? 13 : 15} /> {fileLabel}
      </button>
    </div>
  );
}
