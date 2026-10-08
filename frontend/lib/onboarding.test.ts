import { describe, expect, it } from "vitest";
import {
  academicYearOptions, classSuggestions, DEFAULT_STATE, districtCode, generateSchoolCode, INDIAN_STATES,
  namePrefix, normalisePhone, parseClass, phoneInput, rules, TN_DISTRICTS,
} from "./onboarding";

describe("districts", () => {
  it("lists all 38 Tamil Nadu districts, each with its own code", () => {
    expect(TN_DISTRICTS).toHaveLength(38);
    expect(new Set(TN_DISTRICTS.map((d) => d.code)).size).toBe(38);
    expect(new Set(TN_DISTRICTS.map((d) => d.name)).size).toBe(38);
    TN_DISTRICTS.forEach((d) => expect(d.code).toMatch(/^[A-Z]{2}$/));
  });
  it("puts Tamil Nadu first and the default", () => {
    expect(DEFAULT_STATE).toBe("Tamil Nadu");
    expect(INDIAN_STATES[0]).toBe("Tamil Nadu");
    expect(new Set(INDIAN_STATES).size).toBe(INDIAN_STATES.length);
  });
  it("finds a district's code whatever the case", () => {
    expect(districtCode("Krishnagiri")).toBe("KR");
    expect(districtCode(" krishnagiri ")).toBe("KR");
    expect(districtCode("Atlantis")).toBeNull();
  });
});

describe("school code", () => {
  it("starts with the district code and the first two letters of the school's name", () => {
    expect(generateSchoolCode("Krishnagiri", "Bharathi Matriculation School", [])).toBe("KR-BH-01");
    expect(generateSchoolCode("Krishnagiri", "Bharat Vidya Mandir", [])).toBe("KR-BH-01");
  });
  it("skips words that do not say which school it is", () => {
    expect(namePrefix("Sri Vidya Mandir Senior Secondary School")).toBe("VI");
    expect(namePrefix("St. Joseph's Higher Secondary School")).toBe("JO");
    expect(namePrefix("The Government Higher Secondary School, Hosur")).toBe("HO");
    expect(namePrefix("A")).toBe("AX");
  });
  it("numbers schools whose names begin alike in one district, never reusing a number", () => {
    const issued = ["KR-BH-01", "KR-BH-02"];
    expect(generateSchoolCode("Krishnagiri", "Bharathi Public School", issued)).toBe("KR-BH-03");
    expect(generateSchoolCode("Krishnagiri", "Bharathi Public School", ["KR-BH-01", "KR-BH-07"])).toBe("KR-BH-08");
    expect(generateSchoolCode("Krishnagiri", "Bharathi Public School", ["kr-bh-04"])).toBe("KR-BH-05");
  });
  it("is independent across districts and across prefixes", () => {
    const issued = ["KR-BH-01", "SL-BH-01", "KR-BA-01"];
    expect(generateSchoolCode("Salem", "Bharathi School", issued)).toBe("SL-BH-02");
    expect(generateSchoolCode("Madurai", "Bharathi School", issued)).toBe("MD-BH-01");
    expect(generateSchoolCode("Krishnagiri", "Bala Vidya", issued)).toBe("KR-BA-02");
  });
  it("makes nothing until it has a district and a name", () => {
    expect(generateSchoolCode("", "Bharathi", [])).toBe("");
    expect(generateSchoolCode("Salem", "   ", [])).toBe("");
    expect(generateSchoolCode("Atlantis", "Bharathi", [])).toBe("");
  });
});

describe("academic year", () => {
  it("offers consecutive years from the current academic year, which begins in June", () => {
    const oct = academicYearOptions(new Date(2026, 9, 8), 3);
    expect(oct).toEqual([
      { value: "2026-27", label: "2026 to 2027" },
      { value: "2027-28", label: "2027 to 2028" },
      { value: "2028-29", label: "2028 to 2029" },
    ]);
    expect(academicYearOptions(new Date(2027, 2, 1), 1)[0].value).toBe("2026-27");
    expect(academicYearOptions(new Date(2027, 5, 1), 1)[0].value).toBe("2027-28");
  });
  it("rolls over the century correctly", () => {
    expect(academicYearOptions(new Date(2099, 8, 1), 2).map((o) => o.value)).toEqual(["2099-00", "2100-01"]);
  });
});

describe("classes", () => {
  it("reads a class however it is typed", () => {
    expect(parseClass("10C")).toEqual({ grade: 10, name: "C" });
    expect(parseClass("10-c")).toEqual({ grade: 10, name: "C" });
    expect(parseClass(" 9  b ")).toEqual({ grade: 9, name: "B" });
    expect(parseClass("13A")).toBeNull();
    expect(parseClass("0A")).toBeNull();
    expect(parseClass("A10")).toBeNull();
    expect(parseClass("10")).toBeNull();
  });
  it("offers 10A to 10F when 10 is typed", () => {
    expect(classSuggestions("10", []).map((c) => `${c.grade}${c.name}`)).toEqual(
      ["10A", "10B", "10C", "10D", "10E", "10F"],
    );
  });
  it("narrows as the section is typed, and skips what is already added", () => {
    expect(classSuggestions("10b", []).map((c) => `${c.grade}${c.name}`)).toEqual(["10B"]);
    const have = [{ grade: 10, name: "A" }, { grade: 10, name: "B" }];
    expect(classSuggestions("10", have).map((c) => c.name)).toEqual(["C", "D", "E", "F"]);
  });
  it("puts the grade as typed first", () => {
    const labels = classSuggestions("1", []).map((c) => `${c.grade}${c.name}`);
    expect(labels.slice(0, 6)).toEqual(["1A", "1B", "1C", "1D", "1E", "1F"]);
    expect(labels).toContain("10A");
  });
  it("offers nothing for empty or non-class input", () => {
    expect(classSuggestions("", [])).toEqual([]);
    expect(classSuggestions("abc", [])).toEqual([]);
    expect(classSuggestions("99", [])).toEqual([]);
  });
});

describe("phone numbers", () => {
  it("normalises to digits, dropping +91 and a leading 0 before a mobile", () => {
    expect(normalisePhone("+91 98765-43210")).toBe("9876543210");
    expect(normalisePhone("098765 43210")).toBe("9876543210");
    expect(normalisePhone("04343 222333")).toBe("04343222333");
  });
  it("lets only digits and separators through while typing", () => {
    expect(phoneInput("98a76-5 4x3210")).toBe("9876-5 43210");
  });
  it("checks the school contact number: a mobile or a landline with its STD code", () => {
    expect(rules.contactNumber("9876543210")).toBeNull();
    expect(rules.contactNumber("04343 222333")).toBeNull();
    expect(rules.contactNumber("044-12345678")).toBeNull();
    expect(rules.contactNumber("")).toMatch(/Enter/);
    expect(rules.contactNumber("98765abcde")).toMatch(/digits only/);
    expect(rules.contactNumber("98765")).toMatch(/10-digit/);
    expect(rules.contactNumber("5876543210")).toMatch(/10-digit/);
  });
  it("checks a person's mobile", () => {
    expect(rules.mobile("9876543210", true)).toBeNull();
    expect(rules.mobile("", true)).toMatch(/Enter/);
    expect(rules.mobile("", false)).toBeNull();
    expect(rules.mobile("12345", false)).toMatch(/10-digit/);
    expect(rules.mobile("98x7654321", false)).toMatch(/digits only/);
  });
});

describe("other fields", () => {
  it("checks the school name", () => {
    expect(rules.schoolName("Bharathi Matric School")).toBeNull();
    expect(rules.schoolName("")).toMatch(/Enter/);
    expect(rules.schoolName("ab")).toMatch(/short/);
    expect(rules.schoolName("12345")).toMatch(/letters/);
    expect(rules.schoolName("Bad <script>")).toMatch(/character/);
  });
  it("checks emails, required or optional", () => {
    expect(rules.email("", false)).toBeNull();
    expect(rules.email("", true)).toMatch(/Enter/);
    expect(rules.email("office@school.in", true)).toBeNull();
    expect(rules.email("office@school", false)).toMatch(/valid/);
    expect(rules.email("no spaces@x.in", false)).toMatch(/valid/);
  });
  it("keeps digits out of names", () => {
    expect(rules.personName("K. Ramesh")).toBeNull();
    expect(rules.personName("Ramesh2")).toMatch(/letters only/);
    expect(rules.personName("")).toMatch(/Enter/);
    expect(rules.personName("", false)).toBeNull();
  });
  it("requires a district from the list in Tamil Nadu", () => {
    expect(rules.district("Salem", true)).toBeNull();
    expect(rules.district("", true)).toMatch(/Choose/);
    expect(rules.district("Nowhere", true)).toMatch(/list/);
    expect(rules.district("Nowhere", false)).toBeNull();
  });
  it("requires a listed academic year and at least one class", () => {
    const opts = academicYearOptions(new Date(2026, 9, 1), 3);
    expect(rules.academicYear("2026-27", opts)).toBeNull();
    expect(rules.academicYear("", opts)).toMatch(/Choose/);
    expect(rules.academicYear("1999-00", opts)).toMatch(/Choose/);
    expect(rules.classes([])).toMatch(/at least one/);
    expect(rules.classes([{ grade: 10, name: "A" }])).toBeNull();
  });
  it("checks roll numbers and addresses", () => {
    expect(rules.rollNo("12")).toBeNull();
    expect(rules.rollNo("")).toMatch(/needed/);
    expect(rules.rollNo("a b")).toMatch(/letters and digits/);
    expect(rules.rollNo("12A")).toBeNull();
    expect(rules.rollNo("2024/015")).toBeNull();
    expect(rules.rollNo("10A-12")).toBeNull();
    expect(rules.rollNo("12345678901234567")).not.toBeNull();
    expect(rules.address("")).toBeNull();
    expect(rules.address("abc")).toMatch(/short/);
  });
});

describe("gibberish and bad types", () => {
  it("flags names with digits, keyboard-mash and filler", () => {
    expect(rules.personName("Ravi123")).not.toBeNull();
    expect(rules.personName("aaaaaa")).not.toBeNull();
    expect(rules.personName("qwrtpsdfg")).not.toBeNull();
    expect(rules.personName("S. Ravi Kumar")).toBeNull();
    expect(rules.personName("Krishnamurthy")).toBeNull();
  });
  it("flags school names that are only digits or mash", () => {
    expect(rules.schoolName("12345")).not.toBeNull();
    expect(rules.schoolName("xxxxxx school")).not.toBeNull();
    expect(rules.schoolName("Bharathi Vidyalaya")).toBeNull();
  });
  it("flags letters and wrong lengths in numbers", () => {
    expect(rules.mobile("98a6543210", true)).not.toBeNull();
    expect(rules.mobile("12345", true)).not.toBeNull();
    expect(rules.mobile("98765 43210", true)).toBeNull();
  });
});

describe("student date of birth and career", () => {
  const today = new Date(2026, 9, 8);
  it("accepts a real date for a student aged 8 to 25", () => {
    expect(rules.dob("2011-03-14", today)).toBeNull();
  });
  it("flags impossible, future and out-of-range dates", () => {
    expect(rules.dob("", today)).not.toBeNull();
    expect(rules.dob("2011-02-30", today)).toMatch(/does not exist/);
    expect(rules.dob("2027-01-01", today)).toMatch(/future/);
    expect(rules.dob("2022-01-01", today)).toMatch(/between 8 and 25/);
    expect(rules.dob("1980-01-01", today)).toMatch(/between 8 and 25/);
  });
  it("checks the career answer", () => {
    expect(rules.career("Doctor")).toBeNull();
    expect(rules.career("Not sure yet")).toBeNull();
    expect(rules.career("1234")).not.toBeNull();
    expect(rules.career("")).not.toBeNull();
  });
});
