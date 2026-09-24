"use client";

import { classRosterFull } from "./avai-mock-data";
import { markSent, sentLog, useLiveVersion } from "./liveData";

/** Section-wide share state, read from the per-student WhatsApp log so the
 * test page and the Share reports page always agree. */

export function markReportShared(section: string, testKey: string) {
  const unsent = (classRosterFull[section] ?? []).filter((s) => !sentLog(section, testKey)[s.id]).map((s) => s.id);
  markSent(section, testKey, unsent, new Date().toISOString());
}

export function isReportShared(section: string, testKey: string): boolean {
  const roster = classRosterFull[section] ?? [];
  const log = sentLog(section, testKey);
  return roster.length > 0 && roster.every((s) => log[s.id]);
}

export function useReportShared(section: string, testKey: string): boolean {
  useLiveVersion();
  return isReportShared(section, testKey);
}
