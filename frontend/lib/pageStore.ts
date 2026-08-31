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
  /**
   * Set when the page is removed. A soft delete, because undo has to be able to give the
   * image back and a phone camera cannot re-take a page of a script that has already gone
   * back in the pile. Purged on the same 24-hour clock as everything else.
   */
  deletedAt?: number;
}

/** One reversible action. `pages` holds the rows exactly as they were before it ran. */
export interface HistoryEntry {
  id?: number;
  sessionId: string;
  action: "add" | "retake" | "delete" | "reorder";
  at: number;
  /** the affected rows BEFORE the action; empty for an add, which is undone by removing */
  before: ScannedPage[];
  /** the affected rows AFTER it, so redo does not have to recompute anything */
  after: ScannedPage[];
  /** entries undone but still redoable; cleared by the next new action */
  undone: boolean;
}

class ScanDatabase extends Dexie {
  pages!: Table<ScannedPage, number>;
  history!: Table<HistoryEntry, number>;

  constructor() {
    super("yaadhum-scan");
    this.version(1).stores({ pages: "++id, sessionId, index, uploaded, capturedAt" });
    this.version(2).stores({
      pages: "++id, sessionId, index, uploaded, capturedAt, deletedAt",
      history: "++id, sessionId, at, undone",
    });
  }
}

export const scanDb = new ScanDatabase();

const DAY_MS = 24 * 60 * 60 * 1000;

export async function purgeStale(now = Date.now()): Promise<number> {
  const stale = await scanDb.pages.where("capturedAt").below(now - DAY_MS).toArray();
  await scanDb.pages.bulkDelete(stale.map((p) => p.id!).filter(Boolean));
  const staleHistory = await scanDb.history.where("at").below(now - DAY_MS).toArray();
  await scanDb.history.bulkDelete(staleHistory.map((h) => h.id!).filter(Boolean));
  return stale.length;
}

export async function putPage(page: Omit<ScannedPage, "id">): Promise<void> {
  const existing = await scanDb.pages
    .where({ sessionId: page.sessionId, index: page.index })
    .first();
  if (existing?.id) {
    // A retake of a page that was deleted has to bring it back, and update() cannot clear
    // deletedAt -- see restore().
    await scanDb.pages.put({ ...page, id: existing.id });
    const after = await scanDb.pages.get(existing.id);
    await record(page.sessionId, "retake", [existing], after ? [after] : []);
    return;
  }
  const id = await scanDb.pages.add(page as ScannedPage);
  const added = await scanDb.pages.get(id);
  await record(page.sessionId, "add", [], added ? [added] : []);
}

export async function listPages(sessionId: string): Promise<ScannedPage[]> {
  const pages = await scanDb.pages.where({ sessionId }).toArray();
  return pages.filter((p) => !p.deletedAt).sort((a, b) => a.index - b.index);
}

async function record(
  sessionId: string,
  action: HistoryEntry["action"],
  before: ScannedPage[],
  after: ScannedPage[],
): Promise<void> {
  // A new action makes the redo branch unreachable, so it is dropped rather than left to
  // be replayed onto a state it was never recorded against.
  const stale = await scanDb.history.where({ sessionId }).filter((h) => h.undone).toArray();
  await scanDb.history.bulkDelete(stale.map((h) => h.id!).filter(Boolean));
  await scanDb.history.add({ sessionId, action, at: Date.now(), before, after, undone: false });
}

async function restore(rows: ScannedPage[]): Promise<void> {
  // put(), not update(). Dexie's update() ignores any key whose value is undefined, so
  // clearing deletedAt by passing it as undefined silently did nothing and an undone
  // deletion stayed deleted. put() replaces the whole row, which is what restoring means.
  for (const row of rows) {
    if (row.id == null) continue;
    await scanDb.pages.put(row);
  }
}

/** Whether there is anything to undo, and anything to redo. Drives the two buttons. */
export async function historyState(
  sessionId: string,
): Promise<{ canUndo: boolean; canRedo: boolean }> {
  const entries = await scanDb.history.where({ sessionId }).toArray();
  return {
    canUndo: entries.some((h) => !h.undone),
    canRedo: entries.some((h) => h.undone),
  };
}

export async function undo(sessionId: string): Promise<boolean> {
  const entries = (await scanDb.history.where({ sessionId }).toArray())
    .filter((h) => !h.undone)
    .sort((a, b) => a.at - b.at);
  const last = entries.at(-1);
  if (!last?.id) return false;

  if (last.action === "add") {
    // Nothing existed before, so undoing is removal -- hard, since there is no earlier
    // image to keep and the row was never anything a person had seen twice.
    await scanDb.pages.bulkDelete(last.after.map((p) => p.id!).filter(Boolean));
  } else {
    await restore(last.before);
  }
  await scanDb.history.update(last.id, { undone: true });
  return true;
}

export async function redo(sessionId: string): Promise<boolean> {
  const entries = (await scanDb.history.where({ sessionId }).toArray())
    .filter((h) => h.undone)
    .sort((a, b) => a.at - b.at);
  const next = entries[0];
  if (!next?.id) return false;

  await restore(next.after);
  await scanDb.history.update(next.id, { undone: false });
  return true;
}

export async function deletePage(sessionId: string, index: number): Promise<void> {
  const pages = await listPages(sessionId);
  const target = pages.find((p) => p.index === index);
  if (!target?.id) return;

  // Every row the action touches is captured, not just the removed one: closing the gap
  // renumbers the pages after it, and an undo that restored the page without restoring
  // their numbers would leave two pages claiming the same position.
  const shifted = pages.filter((p) => p.index > index);
  const before = [target, ...shifted].map((p) => ({ ...p }));

  await scanDb.pages.update(target.id, { deletedAt: Date.now() });
  for (const p of shifted) {
    if (p.id) await scanDb.pages.update(p.id, { index: p.index - 1 });
  }

  const after = await Promise.all(
    before.map(async (p) => (p.id != null ? await scanDb.pages.get(p.id) : undefined)),
  );
  await record(sessionId, "delete", before, after.filter((p): p is ScannedPage => !!p));
}
