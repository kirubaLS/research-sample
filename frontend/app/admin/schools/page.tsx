"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2, ChevronRight, FileCheck2, Search, ShieldCheck, UserPlus, Users } from "lucide-react";
import { CountUp, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { api, apiBaseIsDefault, PlatformOverview, PlatformSchool } from "@/lib/api";
import { getPlatformKey } from "@/lib/session";
import { OpsEmpty, SortHeader, type SortDir } from "../ui";

type SortField = "name" | "students" | "papers" | "answer_scripts";

/**
 * AVAI's real book of business: every school GET /platform/schools returns,
 * joined with GET /platform/overview's per-school counts. The reference
 * design's "status" pill, "onboarding %" and "teachers invited/activated"
 * columns all read fields our backend does not have (PlatformSchool carries
 * no status/checklist/teacher-activation state) -- dropped rather than
 * fabricated; see the gap note in the wiring report.
 */
export default function AdminSchoolsPage() {
  const router = useRouter();
  const [schools, setSchools] = useState<PlatformSchool[] | null>(null);
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [board, setBoard] = useState("All");
  const [sort, setSort] = useState<SortField>("name");
  const [dir, setDir] = useState<SortDir>("asc");

  const load = useCallback(async () => {
    const key = getPlatformKey();
    if (!key) return;
    try {
      setSchools(await api.listSchools(key));
    } catch {
      setError("Could not load schools.");
    }
    try {
      setOverview(await api.platformOverview(key));
    } catch {
      /* the table below still works from listSchools alone */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const overviewById = useMemo(() => {
    const m = new Map<string, PlatformOverview["schools"][number]>();
    (overview?.schools ?? []).forEach((r) => m.set(r.id, r));
    return m;
  }, [overview]);

  const boards = useMemo(() => Array.from(new Set((schools ?? []).map((s) => s.board))).sort(), [schools]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = (schools ?? []).filter((s) => {
      if (board !== "All" && s.board !== board) return false;
      if (!q) return true;
      return [s.name, s.board, s.state ?? ""].some((f) => f.toLowerCase().includes(q));
    });
    return [...filtered].sort((a, b) => {
      const ov = (id: string) => overviewById.get(id);
      const av: number | string = sort === "name" ? a.name : sort === "students" ? a.students : sort === "papers" ? ov(a.id)?.papers ?? 0 : ov(a.id)?.answer_scripts ?? 0;
      const bv: number | string = sort === "name" ? b.name : sort === "students" ? b.students : sort === "papers" ? ov(b.id)?.papers ?? 0 : ov(b.id)?.answer_scripts ?? 0;
      const cmp = typeof av === "string" && typeof bv === "string" ? av.localeCompare(bv) : Number(av) - Number(bv);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [schools, query, board, sort, dir, overviewById]);

  function onSort(field: SortField) {
    if (field === sort) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSort(field);
      setDir(field === "name" ? "asc" : "desc");
    }
  }

  const kpis = overview
    ? [
        { label: "Schools", value: overview.totals.schools, sub: "on this deployment", accent: "var(--brand-green)", icon: Building2 },
        { label: "Students", value: overview.totals.students, sub: "across the portfolio", accent: "var(--brand-teal)", icon: Users },
        { label: "Papers loaded", value: overview.totals.papers, sub: `${overview.totals.answer_scripts} answer scripts scanned`, accent: "var(--brand-gold)", icon: FileCheck2 },
        { label: "Reports issued", value: overview.totals.reports_issued, sub: "across the portfolio", accent: "var(--brand-blue)", icon: ShieldCheck },
      ]
    : [];

  return (
    <>
      <Reveal>
        <h1 className="page-title">Schools</h1>
        <p className="page-sub">Every school AVAI has signed. Open an account for its classes, keys and usage.</p>
      </Reveal>

      {apiBaseIsDefault() && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>This site has not been told where its server is, so nothing below will load until it is.</div>
        </div>
      )}
      {error && (
        <div className="evidence evidence--gold" style={{ marginTop: 18 }}>
          <div>{error}</div>
        </div>
      )}

      {overview && (
        <Stagger className="grid grid--4" gap={0.05} style={{ marginTop: 20 }}>
          {kpis.map((k, i) => {
            const Icon = k.icon;
            return (
              <StaggerItem key={k.label}>
                <div className="kpi" style={{ "--accent": k.accent } as React.CSSProperties}>
                  <span className="kpi__icon">
                    <Icon size={21} />
                  </span>
                  <div className="kpi__text">
                    <div className="kpi__label">{k.label}</div>
                    <div className="kpi__value">
                      <CountUp value={k.value} delay={0.1 + i * 0.05} />
                    </div>
                    <div className="kpi__sub">{k.sub}</div>
                  </div>
                </div>
              </StaggerItem>
            );
          })}
        </Stagger>
      )}

      <section className="section" style={{ marginTop: 18 }} aria-labelledby="table-h">
        <div className="section__head">
          <h2 id="table-h" className="section-q" style={{ fontSize: 17 }}>
            All accounts
          </h2>
          <span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}>
            <span className="small muted">
              {rows.length} of {schools?.length ?? 0} shown
            </span>
            <Link href="/admin/onboard" className="btn btn--blue btn--sm">
              <UserPlus size={13} /> Onboard a school
            </Link>
          </span>
        </div>

        <div className="filterbar" style={{ position: "static", background: "transparent", backdropFilter: "none" }}>
          <div className="filter" style={{ flex: "1 1 260px", maxWidth: 360 }}>
            <label htmlFor="school-search">Search</label>
            <span style={{ position: "relative", display: "block" }}>
              <Search size={14} className="muted" style={{ position: "absolute", left: 10, top: 9 }} />
              <input
                id="school-search"
                className="input"
                style={{ paddingLeft: 32 }}
                placeholder="Name, board or state"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </span>
          </div>
          <div className="filter">
            <label htmlFor="board-filter">Board</label>
            <select id="board-filter" className="select" value={board} onChange={(e) => setBoard(e.target.value)}>
              <option>All</option>
              {boards.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="card" style={{ marginTop: 12, overflow: "hidden" }}>
          {!schools ? (
            <div className="card__body">
              <p className="muted small" style={{ margin: 0 }}>Loading…</p>
            </div>
          ) : rows.length === 0 ? (
            <div className="card__body">
              <OpsEmpty>{schools.length === 0 ? "No schools yet. Onboard the first one." : "No account matches those filters."}</OpsEmpty>
            </div>
          ) : (
            <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 560 }}>
              <table className="table table--hover">
                <thead>
                  <tr>
                    <SortHeader label="School" field="name" sort={sort} dir={dir} onSort={onSort} />
                    <th scope="col">Board / State</th>
                    <SortHeader label="Students" field="students" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <SortHeader label="Papers" field="papers" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <SortHeader label="Answer scripts" field="answer_scripts" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <th scope="col">Directory</th>
                    <th scope="col" aria-label="Open account" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => {
                    const ov = overviewById.get(s.id);
                    return (
                      <tr key={s.id} onClick={() => router.push(`/admin/schools/${s.id}`)}>
                        <td style={{ minWidth: 200 }}>
                          <Link href={`/admin/schools/${s.id}`} style={{ color: "inherit", fontWeight: 650 }} onClick={(e) => e.stopPropagation()}>
                            {s.name}
                          </Link>
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <span className="tag">{s.board}</span> {s.state ?? ""}
                        </td>
                        <td className="num">{s.students}</td>
                        <td className="num">{ov?.papers ?? "—"}</td>
                        <td className="num">{ov?.answer_scripts ?? "—"}</td>
                        <td>
                          <span className={`tag ${s.hidden_from_directory ? "tag--risk" : "tag--teal"}`}>
                            {s.hidden_from_directory ? "Hidden" : "Visible"}
                          </span>
                        </td>
                        <td style={{ width: 34 }}>
                          <ChevronRight size={15} className="muted" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
