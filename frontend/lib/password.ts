/** Mirrors the server's check_new_password (backend/app/api/admin.py), so a weak password is
 * flagged while it is typed. The server still decides. */
const COMMON = new Set([
  "password", "password1", "password123", "qwerty123", "qwertyuiop", "123456789", "1234567890",
  "iloveyou1", "admin12345", "welcome123", "school1234", "principal1", "principal123",
]);

export function passwordProblem(pw: string): string | null {
  if (pw.length < 10) return "Use at least 10 characters.";
  if (pw.length > 64) return "Use at most 64 characters.";
  if (/\s/.test(pw)) return "No spaces.";
  if (!/^[\x21-\x7e]+$/.test(pw)) return "Use only letters, digits and the usual symbols on a keyboard.";
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "Use both letters and digits.";
  if (COMMON.has(pw.toLowerCase()) || new Set(pw.toLowerCase()).size < 4) return "That is too easy to guess. Choose something less common.";
  return null;
}
