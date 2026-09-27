"use client";

/**
 * Shared bits for the operator console's forms.
 *
 * /platform does carry a real per-teacher subject/section access grant
 * (PATCH .../keys/{keyId}/assignments) and a real bulk student add
 * (POST .../students/bulk); both are wired from the operator side in
 * app/admin/schools/[schoolId]/page.tsx and app/admin/onboard/page.tsx.
 */

export function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <span className="ops-err">{children}</span>;
}
