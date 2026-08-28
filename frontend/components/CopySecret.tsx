"use client";

import { useState } from "react";

/**
 * A credential shown once.
 *
 * Masked until deliberately revealed, because this component renders on a screen that may
 * be projected or left open in a staffroom, and there is no route that reads the key back
 * later — if it is lost, the only remedy is rotation.
 */
export function CopySecret({ value }: { value: string }) {
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);

  return (
    <div className="copyfield">
      <code title={shown ? value : "hidden"}>{shown ? value : "•".repeat(value.length)}</code>
      <button type="button" className="secondary" onClick={() => setShown((s) => !s)}>
        {shown ? "Hide" : "Reveal"}
      </button>
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
          } catch {
            setCopied(false);
          }
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
