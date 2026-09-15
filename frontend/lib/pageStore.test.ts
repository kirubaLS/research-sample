/**
 * Undo and redo over the captured pages.
 *
 * A phone camera cannot re-take a page of a script that has already gone back in the
 * pile, so a deletion has to be reversible in fact and not only in the interface. Every
 * case here is one a teacher hits standing in a staffroom, not a hypothetical.
 */

import { beforeEach, describe, expect, it } from "vitest";
import {
  deletePage,
  historyState,
  listPages,
  putPage,
  redo,
  scanDb,
  undo,
} from "./pageStore";

const SESSION = "s1";

function page(index: number, tag: string) {
  return {
    sessionId: SESSION,
    index,
    blob: new Blob([tag]),
    thumbnail: `data:${tag}`,
    quality: { blur: 1, glare: 0, coverage: 1, skew: 0, band: "good" },
    capturedAt: Date.now(),
    uploaded: false,
  };
}

async function tags(): Promise<string[]> {
  const pages = await listPages(SESSION);
  return Promise.all(pages.map((p) => p.blob.text()));
}

beforeEach(async () => {
  await scanDb.pages.clear();
  await scanDb.history.clear();
});

describe("capturing pages", () => {
  it("keeps them in the order they were taken", async () => {
    await putPage(page(0, "a"));
    await putPage(page(1, "b"));
    await putPage(page(2, "c"));
    expect(await tags()).toEqual(["a", "b", "c"]);
  });

  it("replaces the image on a retake and keeps the page's position", async () => {
    await putPage(page(0, "a"));
    await putPage(page(1, "blurry"));
    await putPage(page(1, "sharp"));
    expect(await tags()).toEqual(["a", "sharp"]);
  });

  it("works for a single page as well as many", async () => {
    await putPage(page(0, "only"));
    expect(await tags()).toEqual(["only"]);
  });
});

describe("undo", () => {
  it("gives back a deleted page, with its image", async () => {
    await putPage(page(0, "a"));
    await putPage(page(1, "b"));
    await deletePage(SESSION, 0);
    expect(await tags()).toEqual(["b"]);

    expect(await undo(SESSION)).toBe(true);
    expect(await tags()).toEqual(["a", "b"]);
  });

  it("restores the numbering of the pages the deletion shifted", async () => {
    // The case that makes a naive undo wrong: removing page 0 renumbers b and c, and
    // putting a back without putting their numbers back leaves two pages claiming
    // position 1.
    await putPage(page(0, "a"));
    await putPage(page(1, "b"));
    await putPage(page(2, "c"));
    await deletePage(SESSION, 0);
    expect((await listPages(SESSION)).map((p) => p.index)).toEqual([0, 1]);

    await undo(SESSION);
    const restored = await listPages(SESSION);
    expect(restored.map((p) => p.index)).toEqual([0, 1, 2]);
    expect(await tags()).toEqual(["a", "b", "c"]);
  });

  it("takes back a retake, returning the earlier image", async () => {
    await putPage(page(0, "first"));
    await putPage(page(0, "second"));
    expect(await tags()).toEqual(["second"]);

    await undo(SESSION);
    expect(await tags()).toEqual(["first"]);
  });

  it("removes a page that was only just added", async () => {
    await putPage(page(0, "a"));
    await undo(SESSION);
    expect(await tags()).toEqual([]);
  });

  it("steps back through several actions, most recent first", async () => {
    await putPage(page(0, "a"));
    await putPage(page(1, "b"));
    await deletePage(SESSION, 1);

    await undo(SESSION);
    expect(await tags()).toEqual(["a", "b"]);
    await undo(SESSION);
    expect(await tags()).toEqual(["a"]);
    await undo(SESSION);
    expect(await tags()).toEqual([]);
  });

  it("reports honestly when there is nothing left to undo", async () => {
    expect(await undo(SESSION)).toBe(false);
    expect((await historyState(SESSION)).canUndo).toBe(false);
  });
});

describe("redo", () => {
  it("re-applies a deletion that was undone", async () => {
    await putPage(page(0, "a"));
    await putPage(page(1, "b"));
    await deletePage(SESSION, 0);
    await undo(SESSION);
    expect(await tags()).toEqual(["a", "b"]);

    expect(await redo(SESSION)).toBe(true);
    expect(await tags()).toEqual(["b"]);
  });

  it("is unavailable once a new page makes the branch unreachable", async () => {
    // The classic bug: undo, then capture something new, then redo -- replaying an action
    // recorded against a state that no longer exists.
    await putPage(page(0, "a"));
    await deletePage(SESSION, 0);
    await undo(SESSION);
    expect((await historyState(SESSION)).canRedo).toBe(true);

    await putPage(page(1, "new"));
    expect((await historyState(SESSION)).canRedo).toBe(false);
    expect(await redo(SESSION)).toBe(false);
  });

  it("reports honestly when there is nothing to redo", async () => {
    await putPage(page(0, "a"));
    expect(await redo(SESSION)).toBe(false);
  });
});

describe("isolation between scripts", () => {
  it("does not let one student's undo touch another's pages", async () => {
    await putPage(page(0, "mine"));
    await putPage({ ...page(0, "theirs"), sessionId: "s2" });
    await undo("s2");

    expect(await tags()).toEqual(["mine"]);
    expect(await listPages("s2")).toEqual([]);
  });
});
