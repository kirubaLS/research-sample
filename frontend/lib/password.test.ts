import { describe, expect, it } from "vitest";
import { passwordProblem } from "./password";

describe("passwordProblem", () => {
  it("accepts a long mix of letters and digits", () => {
    expect(passwordProblem("Sunrise2026Hill")).toBeNull();
  });
  it("flags short, spaced, single-kind and common passwords", () => {
    expect(passwordProblem("abc12")).toMatch(/10/);
    expect(passwordProblem("has space 1234567")).toMatch(/spaces/);
    expect(passwordProblem("onlylettersonly")).toMatch(/letters and digits/);
    expect(passwordProblem("12345678901")).toMatch(/letters and digits/);
    expect(passwordProblem("Password123")).toMatch(/easy to guess/);
  });
});

describe("passwordProblem characters", () => {
  it("flags characters a keyboard header cannot carry", () => {
    expect(passwordProblem("பாஸ்வேர்ட்12345")).toMatch(/keyboard/);
  });
});
