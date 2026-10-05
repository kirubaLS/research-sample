"""Pick the Tier 0 gate's margin from shadow runs. READ-ONLY.

Run the pipeline with ``YAADHUM_CHAPTER_GATE=true`` (shadow: the chapter judge is still asked
about every question), then:

    docker compose exec -T backend python -m scripts.tune_gate [--min-agreement 0.98]

For each candidate margin it prints how many questions the gate would have settled on its own
and how often the chapter judge named the same chapter. The gate may only be enforced
(``YAADHUM_CHAPTER_GATE_ENFORCE``) at a margin whose agreement you accept: a question the gate
settles wrongly is a chapter nobody read.

Reads only the ``chapter_gate.curve`` each place job already stored.
"""

from __future__ import annotations

import argparse

MARGINS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)


def sweep(curve: list[list], margins=MARGINS) -> list[dict]:
    """``curve`` rows are [relative_margin, retrievers_agreed, judge_agreed]."""
    out = []
    for m in margins:
        passed = [c for c in curve if c[1] and c[0] >= m]
        agreed = sum(1 for c in passed if c[2])
        out.append({
            "margin": m, "settled": len(passed), "of": len(curve), "agreed": agreed,
            "agreement": round(agreed / len(passed), 4) if passed else None,
        })
    return out


def recommend(rows: list[dict], min_agreement: float, min_settled: int = 30) -> dict | None:
    """The loosest margin whose agreement clears ``min_agreement`` on at least
    ``min_settled`` questions -- the one that removes the most calls safely. None when no
    margin does: too few questions, or retrieval alone is not good enough yet."""
    ok = [r for r in rows if r["agreement"] is not None and r["agreement"] >= min_agreement
          and r["settled"] >= min_settled]
    return max(ok, key=lambda r: r["settled"]) if ok else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--min-agreement", type=float, default=0.98)
    ap.add_argument("--min-settled", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=50, help="most recent place jobs to read")
    args = ap.parse_args(argv)

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import PlacementJob

    db = SessionLocal()
    try:
        jobs = db.scalars(
            select(PlacementJob).where(PlacementJob.status == "succeeded")
            .order_by(PlacementJob.created_at.desc()).limit(args.jobs * 3)
        ).all()
        curve: list[list] = []
        used = 0
        for job in jobs:
            gate = (job.result or {}).get("chapter_gate") if isinstance(job.result, dict) else None
            if gate and gate.get("curve"):
                curve.extend(gate["curve"])
                used += 1
            if used >= args.jobs:
                break
    finally:
        db.close()

    if not curve:
        print("no shadow data: run papers with YAADHUM_CHAPTER_GATE=true first")
        return 1
    rows = sweep(curve)
    print(f"{used} jobs, {len(curve)} questions the judge also answered\n")
    print(f"{'margin':>7} {'settled':>8} {'agreed':>7} {'agreement':>10}")
    for r in rows:
        pct = f"{r['agreement']:.1%}" if r["agreement"] is not None else "-"
        print(f"{r['margin']:>7.1f} {r['settled']:>8} {r['agreed']:>7} {pct:>10}")
    pick = recommend(rows, args.min_agreement, args.min_settled)
    if pick is None:
        print(f"\nno margin reaches {args.min_agreement:.0%} agreement on "
              f"{args.min_settled}+ questions yet: keep the gate in shadow")
    else:
        print(f"\nrecommended: YAADHUM_CHAPTER_GATE_MIN_MARGIN={pick['margin']} "
              f"(settles {pick['settled']}/{pick['of']} at {pick['agreement']:.1%} agreement)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
