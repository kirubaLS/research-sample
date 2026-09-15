import { describe, expect, it } from "vitest";
import { plan, sortFile } from "./bookFiles";

const f = (name: string) => new File([""], name, { type: "application/pdf" });

describe("sortFile", () => {
  it("reads NCERT codes: book, chapter, contents, answers", () => {
    expect(sortFile(f("jhks101.pdf"))).toMatchObject({ subject: "X.HIN.KS", role: "chapter", chapter: 1 });
    expect(sortFile(f("jhsp1ps.pdf"))).toMatchObject({ subject: "X.HIN.SP", role: "contents" });
    expect(sortFile(f("jemh1an.pdf"))).toMatchObject({ subject: "X.MATH", role: "skip" });
    expect(sortFile(f("jess3.pdf")).role).toBe("skip");
  });
  it("reads NN-title names with no book", () => {
    expect(sortFile(f("03-kaalakkanitham.pdf"))).toMatchObject({ subject: null, role: "chapter", chapter: 3 });
    expect(sortFile(f("00-contents.pdf"))).toMatchObject({ subject: null, role: "contents" });
    expect(sortFile(f("notes.pdf")).role).toBe("skip");
  });
});

describe("plan", () => {
  it("groups by book, contents first, chapters in order", () => {
    const out = plan([f("jhks102.pdf"), f("jhks1ps.pdf"), f("jhkr101.pdf"), f("jhks101.pdf")], null);
    expect([...out.keys()].sort()).toEqual(["X.HIN.KR", "X.HIN.KS"]);
    expect(out.get("X.HIN.KS")!.map((s) => s.file.name)).toEqual(["jhks1ps.pdf", "jhks101.pdf", "jhks102.pdf"]);
  });
  it("sends bookless files to the fallback, and drops them without one", () => {
    expect(plan([f("01-annai.pdf")], "X.TAM").get("X.TAM")).toHaveLength(1);
    expect(plan([f("01-annai.pdf")], null).size).toBe(0);
  });
});
