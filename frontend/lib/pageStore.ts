/**
 * Scanned pages live only in the browser until Complete is pressed.
 *
 * The whole capture flow works with no network, and a 24-hour purge clears any shared
 * staffroom laptop automatically.
 */

import Dexie, { type Table } from "dexie";

export interface ScannedPage {
  id?: number;
  sessionId: string;
  /** the page's position in the script — retake replaces the blob and KEEPS this index */
  index: number;
  blob: Blob;
  thumbnail: string;
  quality: { blur: number; glare: number; coverage: number; skew: number; band: string };
  capturedAt: number;
  uploaded: boolean;
}

class ScanDatabase extends Dexie {
  pages!: Table<ScannedPage, number>;

  constructor() {
    super("yaadhum-scan");
    this.version(1).stores({ pages: "++id, sessionId, index, uploaded, capturedAt" });
  }
}

export const scanDb = new ScanDatabase();

const DAY_MS = 24 * 60 * 60 * 1000;

export async function purgeStale(now = Date.now()): Promise<number> {
  const stale = await scanDb.pages.where("capturedAt").below(now - DAY_MS).toArray();
  await scanDb.pages.bulkDelete(stale.map((p) => p.id!).filter(Boolean));
  return stale.length;
}

export async function putPage(page: Omit<ScannedPage, "id">): Promise<void> {
  const existing = await scanDb.pages
    .where({ sessionId: page.sessionId, index: page.index })
    .first();
  if (existing?.id) {
    await scanDb.pages.update(existing.id, page); // retake: same index, new blob
  } else {
    await scanDb.pages.add(page as ScannedPage);
  }
}

export async function listPages(sessionId: string): Promise<ScannedPage[]> {
  const pages = await scanDb.pages.where({ sessionId }).toArray();
  return pages.sort((a, b) => a.index - b.index);
}

export async function deletePage(sessionId: string, index: number): Promise<void> {
  const pages = await listPages(sessionId);
  const target = pages.find((p) => p.index === index);
  if (target?.id) await scanDb.pages.delete(target.id);
  // close the gap so the sequence stays contiguous
  const remaining = (await listPages(sessionId)).filter((p) => p.index > index);
  for (const p of remaining) {
    if (p.id) await scanDb.pages.update(p.id, { index: p.index - 1 });
  }
}
