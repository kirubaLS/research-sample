"""Dedupe and apply proposed concept families for a subject, over the HTTP API.

    python -m scripts.apply_concept_families https://frontend1.onrender.com X.MATH
    python -m scripts.apply_concept_families https://frontend1.onrender.com X.MATH --apply

Fetches GET /platform/books/{subject}/concept-families, merges proposals that are the
same idea, and POSTs the cleaned set to /platform/books/{subject}/concept-families.

Two kinds of duplicate show up in an LLM proposal run and both are collapsed here:
  - identical `code` appearing twice (the same proposal listed twice) -> kept once,
    `from_sections` unioned.
  - same `chapter_code` + `label` with different codes (the model named the same
    learning area twice in one run) -> kept once (first code wins), `from_sections`
    unioned.

A proposal with no `from_sections` is not dropped: it still creates a usable family,
it just cannot be chosen by section afterwards. That is `choose_family`'s job to flag
per-question, not this script's to guess at.

Without --apply this only prints what it would create -- nothing is written.
"""

from __future__ import annotations

import argparse

import httpx


def merge(families: list[dict]) -> list[dict]:
    by_code: dict[str, dict] = {}
    order: list[str] = []
    for fam in families:
        code = fam["code"]
        if code not in by_code:
            by_code[code] = dict(fam)
            order.append(code)
        else:
            existing = by_code[code]
            existing["from_sections"] = sorted(
                set(existing.get("from_sections") or []) | set(fam.get("from_sections") or [])
            )

    by_key: dict[tuple[str, str], str] = {}
    merged: dict[str, dict] = {}
    for code in order:
        fam = by_code[code]
        key = (fam["chapter_code"], fam["label"].strip().lower())
        canonical = by_key.get(key)
        if canonical is None:
            by_key[key] = code
            merged[code] = fam
        else:
            target = merged[canonical]
            target["from_sections"] = sorted(
                set(target.get("from_sections") or []) | set(fam.get("from_sections") or [])
            )

    return list(merged.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="e.g. https://frontend1.onrender.com")
    parser.add_argument("subject", help="e.g. X.MATH")
    parser.add_argument("--apply", action="store_true", help="actually POST; default is dry-run")
    parser.add_argument("--batch-size", type=int, default=200, help="max families per POST (API caps at 200)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=60) as client:
        resp = client.get(f"{base}/platform/books/{args.subject}/concept-families")
        resp.raise_for_status()
        data = resp.json()

        candidates = [f for f in data["families"] if not f["already_exists"]]
        merged = merge(candidates)

        dropped_dupes = len(candidates) - len(merged)
        print(f"subject: {data['subject']}")
        print(f"existing: {data['existing']}, proposed: {data['proposed']}")
        print(f"candidates to create: {len(candidates)}, after merging duplicates: {len(merged)} "
              f"({dropped_dupes} duplicate entries merged away)")
        print(f"without a section (kept, just unmatched by section): "
              f"{sum(1 for f in merged if not f['from_sections'])}")

        if not args.apply:
            print("\ndry run -- nothing written. Re-run with --apply to create these.")
            for fam in merged:
                print(f"  {fam['chapter_label']:35} {fam['label']}")
            return

        created = already_existed = 0
        unknown: list[str] = []
        for i in range(0, len(merged), args.batch_size):
            batch = merged[i : i + args.batch_size]
            post = client.post(
                f"{base}/platform/books/{args.subject}/concept-families",
                json={"families": batch},
            )
            post.raise_for_status()
            result = post.json()
            created += result["created"]
            already_existed += result["already_existed"]
            unknown.extend(result["unknown_chapters"])

        print(f"\ncreated: {created}, already existed: {already_existed}")
        if unknown:
            print(f"unknown chapters (skipped): {sorted(set(unknown))}")


if __name__ == "__main__":
    main()
