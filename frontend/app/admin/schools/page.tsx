"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Building2, ChevronRight, FileCheck2, KeyRound, Search, UserPlus, Users } from "lucide-react";
import { AnimatedBar, CountUp, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { accountStatuses, adminSchools, boards, formatAgo, onboardingPct, portfolioKpis, statusAccent, type AdminSchool } from "@/lib/avai-admin-data";
import { useOpsVersion } from "@/lib/opsDirectory";
import { OpsEmpty, SortHeader, StatusPill, type SortDir } from "../ui";

type SortField = "name" | "students" | "activation" | "progress";


function sortValue(s: AdminSchool, field: SortField): number | string {
  switch (field) {
    case "students":
      return s.students;
    case "activation":
      return s.teachersInvited ? s.teachersActivated / s.teachersInvited : -1;
    case "progress":
      return s.progress;
    default:
      return s.name;
  }
}

/** AVAI's book of business, kept to what an ops person checks daily: who's
 * live, who's stalled, and a plain list to search and open an account
 * from. No portfolio-mix chart, no contract-value column here, that
 * detail lives on the account page, one click away. */
export default function AdminSchoolsPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");
  const [board, setBoard] = useState("All");
  const [sort, setSort] = useState<SortField>("name");
  const [dir, setDir] = useState<SortDir>("asc");
  const opsVersion = useOpsVersion();
  const kpis = [
    { label: "Schools live", value: portfolioKpis.schoolsLive, sub: `of ${portfolioKpis.schoolsTotal} accounts`, accent: "var(--brand-green)", icon: Building2 },
    { label: "Students under analysis", value: portfolioKpis.studentsUnderAnalysis, sub: "across the portfolio", accent: "var(--brand-teal)", icon: Users },
    { label: "Teachers activated", value: portfolioKpis.teachersActivated, sub: `of ${portfolioKpis.teachersInvited} invited`, accent: "var(--brand-gold)", icon: KeyRound },
    { label: "Assessments analysed", value: portfolioKpis.assessmentsThisTerm, sub: "this term, across the portfolio", accent: "var(--brand-blue)", icon: FileCheck2 },
  ];

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = adminSchools.filter((s) => {
      if (status !== "All" && s.status !== status) return false;
      if (board !== "All" && s.board !== board) return false;
      if (!q) return true;
      return [s.name, s.code, s.state, s.city].some((f) => f.toLowerCase().includes(q));
    });
    return [...filtered].sort((a, b) => {
      const av = sortValue(a, sort);
      const bv = sortValue(b, sort);
      const cmp = typeof av === "string" && typeof bv === "string" ? av.localeCompare(bv) : Number(av) - Number(bv);
      return dir === "asc" ? cmp : -cmp;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, status, board, sort, dir, opsVersion]);

  function onSort(field: SortField) {
    if (field === sort) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setSort(field);
      setDir(field === "name" ? "asc" : "desc");
    }
  }

  return (
    <>
      <Reveal>
        <h1 className="page-title">Schools</h1>
        <p className="page-sub">Every school AVAI has signed. Open an account for its checklist, teacher keys and usage.</p>
      </Reveal>

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

      <section className="section" style={{ marginTop: 18 }} aria-labelledby="table-h">
        <div className="section__head">
          <h2 id="table-h" className="section-q" style={{ fontSize: 17 }}>
            All accounts
          </h2>
          <span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}>
            <span className="small muted">
              {rows.length} of {adminSchools.length} shown
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
                placeholder="Name, code or state"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </span>
          </div>
          <div className="filter">
            <label htmlFor="status-filter">Status</label>
            <select id="status-filter" className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option>All</option>
              {accountStatuses.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
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
          {rows.length === 0 ? (
            <div className="card__body">
              <OpsEmpty>No account matches those filters.</OpsEmpty>
            </div>
          ) : (
            <div className="table-wrap table-wrap--scroll" style={{ maxHeight: 560 }}>
              <table className="table table--hover">
                <thead>
                  <tr>
                    <SortHeader label="School" field="name" sort={sort} dir={dir} onSort={onSort} />
                    <th scope="col">Board / Location</th>
                    <th scope="col">Status</th>
                    <SortHeader label="Students" field="students" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <SortHeader label="Teachers" field="activation" sort={sort} dir={dir} onSort={onSort} align="right" />
                    <SortHeader label="Onboarding" field="progress" sort={sort} dir={dir} onSort={onSort} />
                    <th scope="col" aria-label="Open account" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((s) => {
                    const pct = onboardingPct(s);
                    return (
                      <tr key={s.id} onClick={() => router.push(`/admin/schools/${s.id}`)}>
                        <td style={{ minWidth: 200 }}>
                          <Link href={`/admin/schools/${s.id}`} style={{ color: "inherit", fontWeight: 650 }} onClick={(e) => e.stopPropagation()}>
                            {s.name}
                          </Link>
                          <div className="small muted mono">{s.code}</div>
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <span className="tag">{s.board}</span> {s.city}, {s.state}
                        </td>
                        <td>
                          <StatusPill status={s.status} size="sm" />
                        </td>
                        <td className="num">{s.students}</td>
                        <td className="num mono" style={{ whiteSpace: "nowrap" }}>
                          {s.teachersActivated} / {s.teachersInvited}
                        </td>
                        <td style={{ minWidth: 150 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{ flex: 1, minWidth: 70 }}>
                              <AnimatedBar value={pct} accent={statusAccent(s.status)} height={6} label={`${s.name} onboarding ${pct} percent complete`} />
                            </div>
                            <span className="small mono muted" style={{ width: 34, textAlign: "right" }}>
                              {pct}%
                            </span>
                          </div>
                          <div className="small muted" style={{ marginTop: 2 }}>
                            Active {formatAgo(s.lastActivity)}
                          </div>
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
