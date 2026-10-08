import { describe, expect, it } from "vitest";
import { classKey, importStudents, parseDelimited } from "./studentImport";

describe("parseDelimited", () => {
  it("reads csv with quotes and tab-separated text", () => {
    expect(parseDelimited('1,"Rao, Aditi",Meera,9876543210\n')).toEqual([["1", "Rao, Aditi", "Meera", "9876543210"]]);
    expect(parseDelimited("1\tAditi\tMeera\t9876543210\r\n2\tKiran\tDeepak\t")).toEqual([
      ["1", "Aditi", "Meera", "9876543210"], ["2", "Kiran", "Deepak", ""],
    ]);
  });
});

describe("importStudents", () => {
  it("maps columns by header, in any order", () => {
    const r = importStudents([
      ["Parent WhatsApp", "Student Name", "Roll No", "Parent Name"],
      ["98765 43210", "Aditi Rao", "12", "Meera Rao"],
    ]);
    expect(r.usedHeader).toBe(true);
    expect(r.accepted).toEqual([
      { roll_no: "12", name: "Aditi Rao", parent_name: "Meera Rao", parent_whatsapp: "9876543210", className: "" },
    ]);
  });
  it("reads roll, name, parent, whatsapp when there is no header", () => {
    const r = importStudents([["12", "Aditi Rao", "Meera Rao", "9876543210"]]);
    expect(r.usedHeader).toBe(false);
    expect(r.accepted).toHaveLength(1);
  });
  it("rejects wrong types and says why, row by row", () => {
    const r = importStudents([
      ["Roll", "Name", "Parent", "WhatsApp"],
      ["A12", "Aditi", "Meera", "9876543210"],
      ["13", "Kiran99", "Deepak", "9876543210"],
      ["14", "Riya Shah", "Neha123", "9876543210"],
      ["15", "Zoya Khan", "Sana Khan", "12345"],
      ["16", "Om Rao", "", ""],
    ]);
    expect(r.accepted.map((s) => s.roll_no)).toEqual(["16"]);
    expect(r.rejected.map((x) => x.row)).toEqual([2, 3, 4, 5]);
  });
  it("rejects a repeated roll number", () => {
    const r = importStudents([["1", "Aditi Rao", "", ""], ["1", "Kiran Shah", "", ""]]);
    expect(r.accepted).toHaveLength(1);
    expect(r.rejected[0].reasons[0]).toMatch(/repeats/);
  });
  it("normalises class labels", () => {
    expect(classKey("Class 10 A")).toBe("10A");
    expect(classKey("10-b")).toBe("10B");
  });
});
