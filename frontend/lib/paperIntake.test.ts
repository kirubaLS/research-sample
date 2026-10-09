import { describe, expect, it } from "vitest";
import { fallbackTitle, findExistingTest, matchSubject, normaliseSubject, summarise, today } from "./paperIntake";

const subjects = [
  { subject_code: "X.MATH", label: "Class X Mathematics" },
  { subject_code: "X.SCI", label: "Class X Science" },
  { subject_code: "X.SST", label: "Class X Social Science" },
  { subject_code: "X.ENG", label: "Class X English", group_label: "English" },
];

describe("matchSubject", () => {
  it("reads the subject however the heading words it", () => {
    expect(matchSubject("Mathematics", subjects)).toBe("X.MATH");
    expect(matchSubject("MATHS", subjects)).toBe("X.MATH");
    expect(matchSubject("Class X - Social Science (Paper 1)", subjects)).toBe("X.SST");
    expect(matchSubject("SST", subjects)).toBe("X.SST");
    expect(matchSubject("English Language & Literature", subjects)).toBe("X.ENG");
  });
  it("says nothing rather than guess", () => {
    expect(matchSubject(null, subjects)).toBeNull();
    expect(matchSubject("Astronomy", subjects)).toBeNull();
    expect(normaliseSubject("Class 10 Maths")).toBe("mathematics");
  });
});

describe("findExistingTest", () => {
  const tests = [
    { id: "a", name: "Unit Test 1", date: "2026-09-28" },
    { id: "b", name: "unit test 1", date: "2026-09-29" },
  ];
  it("joins a card of the same name, preferring the same date", () => {
    expect(findExistingTest("UNIT TEST 1", "2026-09-29", tests)?.id).toBe("b");
    expect(findExistingTest("Unit Test 1", null, tests)?.id).toBe("a");
  });
  it("makes a new card for a different name or an unmatched date", () => {
    expect(findExistingTest("Half Yearly", null, tests)).toBeNull();
    expect(findExistingTest("Unit Test 1", "2026-10-05", tests)).toBeNull();
  });
});

describe("fill-ins", () => {
  it("builds a title and a one-line summary", () => {
    expect(fallbackTitle("Class X Mathematics", "2026-10-09")).toBe("Mathematics test, 2026-10-09");
    expect(today(new Date(2026, 9, 9))).toBe("2026-10-09");
    expect(summarise({ subject: "Maths", class: "X", title: "Unit Test 1", date: null, total_marks: 80, duration: null }, "Class X Mathematics"))
      .toBe("Unit Test 1 · Mathematics · 80 marks");
  });
});
