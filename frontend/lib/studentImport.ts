/**
 * Turns a pasted block or an uploaded sheet into student rows, checking every cell on the way in:
 * roll number is digits, student and parent names are names, the parent's WhatsApp is a mobile
 * number. A row that fails any check is not added; it is reported with its row number and why.
 * Pure functions, so the rules are tested without a browser.
 */
import { normalisePhone, rules } from "./onboarding";

export type ImportedStudent = { roll_no: string; name: string; parent_name: string; parent_whatsapp: string; className: string };
export type RejectedRow = { row: number; reasons: string[] };
export type ImportResult = { accepted: ImportedStudent[]; rejected: RejectedRow[]; usedHeader: boolean };

type Field = keyof ImportedStudent;
/** Without a header row the columns are read in the order the table shows them. */
const DEFAULT_ORDER: Field[] = ["roll_no", "name", "parent_name", "parent_whatsapp"];

const HEADERS: [Field, RegExp][] = [
  ["parent_whatsapp", /whats|mobile|phone|contact|number.*parent|parent.*(no|num)/],
  ["parent_name", /parent|guardian|father|mother/],
  ["roll_no", /roll|reg|admission|adm\b|^no\.?$|^id$/],
  ["className", /class|section|grade|std|standard/],
  ["name", /name|student/],
];

function fieldFor(header: string): Field | null {
  const h = header.trim().toLowerCase();
  if (!h) return null;
  for (const [field, re] of HEADERS) if (re.test(h)) return field;
  return null;
}

/** Splits CSV or tab-separated text, honouring "quoted, cells". */
export function parseDelimited(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const delim = text.includes("\t") ? "\t" : ",";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === delim) { row.push(cell.trim()); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell.trim()); cell = "";
      if (row.some((x) => x !== "")) rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell.trim());
  if (row.some((x) => x !== "")) rows.push(row);
  return rows;
}

/** Spreadsheet cells can arrive as numbers (a mobile, a roll number); make them text. */
export function cellText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(v);
  return String(v).trim();
}

export function importStudents(rows: string[][]): ImportResult {
  if (rows.length === 0) return { accepted: [], rejected: [], usedHeader: false };
  const mapped = rows[0].map(fieldFor);
  // A header row names at least two known columns and its "roll" cell is not itself a number.
  const usedHeader = mapped.filter(Boolean).length >= 2 && !/^\d+$/.test(rows[0][mapped.indexOf("roll_no")] ?? "x");
  const order: (Field | null)[] = usedHeader ? mapped : DEFAULT_ORDER;
  const body = usedHeader ? rows.slice(1) : rows;
  const offset = usedHeader ? 2 : 1;

  const accepted: ImportedStudent[] = [];
  const rejected: RejectedRow[] = [];
  const seen = new Set<string>();
  body.forEach((cols, i) => {
    const rec: ImportedStudent = { roll_no: "", name: "", parent_name: "", parent_whatsapp: "", className: "" };
    order.forEach((f, ci) => { if (f && cols[ci] !== undefined) rec[f] = cols[ci].trim(); });
    const reasons: string[] = [];
    const roll = rules.rollNo(rec.roll_no);
    if (roll) reasons.push(roll);
    const name = rules.personName(rec.name);
    if (name) reasons.push(`Student: ${name}`);
    const parent = rules.personName(rec.parent_name, false);
    if (parent) reasons.push(`Parent: ${parent}`);
    const wa = rules.mobile(rec.parent_whatsapp, false);
    if (wa) reasons.push(`WhatsApp: ${wa}`);
    const dupKey = `${rec.className.toUpperCase()}|${rec.roll_no}`;
    if (!roll && seen.has(dupKey)) reasons.push("Roll number repeats earlier in the sheet.");
    if (reasons.length) { rejected.push({ row: i + offset, reasons }); return; }
    seen.add(dupKey);
    accepted.push({ ...rec, parent_whatsapp: rec.parent_whatsapp ? normalisePhone(rec.parent_whatsapp) : "" });
  });
  return { accepted, rejected, usedHeader };
}

/** "10A", "10-a", "Class 10 A" -> "10A", for routing a Class column to the right tab. */
export function classKey(raw: string): string {
  return raw.toUpperCase().replace(/CLASS|STD|STANDARD|GRADE/g, "").replace(/[\s-]/g, "");
}
