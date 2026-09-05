"use client";

/**
 * The student's answer script, on screen.
 *
 * Pages are fetched with the school key and shown from object URLs. A plain <img src> or
 * a link would send no headers, so the page endpoint would refuse and a viewer would show
 * broken images -- an affordance that looks like access and is not.
 *
 * One page at a time, loaded on demand. A twenty-page script is twenty photographs, and
 * pulling all of them to show the first is how a staffroom laptop on school wifi ends up
 * looking broken.
 */

import { useEffect, useState } from "react";
import { api, type ScanDoc } from "@/lib/api";
import { getApiKey } from "@/lib/session";

export function ScriptViewer({ doc }: { doc: ScanDoc }) {
  const [index, setIndex] = useState(0);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const page = doc.pages[index];
  const isPdf = page?.content_type === "application/pdf";

  useEffect(() => {
    const key = getApiKey();
    if (!key || !page) return;
    let url: string | null = null;
    let cancelled = false;
    setSrc(null);
    setError(null);
    api
      .pageBlob(key, page.url)
      .then((objectUrl) => {
        url = objectUrl;
        if (cancelled) URL.revokeObjectURL(objectUrl);
        else setSrc(objectUrl);
      })
      .catch(() => setError("That page could not be loaded."));
    return () => {
      cancelled = true;
      // Revoked on the way out: object URLs are held until the tab closes otherwise, and
      // a teacher paging through a class of forty scripts would keep every one in memory.
      if (url) URL.revokeObjectURL(url);
    };
  }, [page]);

  if (!page) return <p className="muted">This script has no pages stored.</p>;

  return (
    <div>
      <div className="bar">
        <button
          className="secondary tiny"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
        >
          Previous
        </button>
        <span className="small">
          Page {index + 1} of {doc.page_count}
        </span>
        <button
          className="secondary tiny"
          onClick={() => setIndex((i) => Math.min(doc.pages.length - 1, i + 1))}
          disabled={index >= doc.pages.length - 1}
        >
          Next
        </button>
      </div>

      <div className="frame">
        {error && <p className="error">{error}</p>}
        {!error && !src && <p className="muted">Loading the page…</p>}
        {src && isPdf && (
          <object data={src} type="application/pdf" className="pdf">
            <p className="muted">
              This page is a PDF and cannot be shown here.{" "}
              <a href={src} target="_blank" rel="noreferrer">
                Open it in a new tab
              </a>
              .
            </p>
          </object>
        )}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {src && !isPdf && <img src={src} alt={`Page ${index + 1} of the answer script`} />}
      </div>

      <style jsx>{`
        .bar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
        .frame {
          border: 1px solid #e3e3e6; border-radius: 10px; background: #f7f7f8;
          min-height: 220px; display: grid; place-items: center; padding: 10px;
        }
        .frame img { max-width: 100%; height: auto; border-radius: 6px; }
        .pdf { width: 100%; height: 70vh; border: 0; }
        .muted { color: #666; }
        .error { color: #a11; }
      `}</style>
    </div>
  );
}
