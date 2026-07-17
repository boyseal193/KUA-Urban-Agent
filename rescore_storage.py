#!/usr/bin/env python3
"""Bulk re-score existing SELF-STORAGE properties with the v3 engine.

* DRY-RUN by default — prints a full before/after backtest and writes a report
  file. Nothing is written to the database.
* ``--commit`` inserts a NEW analysis row per property (old analyses are NEVER
  deleted) and updates ``properties.score/verdict/deal_status/classification``.
  The new analysis records ``scoring_version`` and ``previous_score`` for audit.

Usage:
    python3 rescore_storage.py                 # dry run, all properties
    python3 rescore_storage.py --limit 50      # dry run, first 50
    python3 rescore_storage.py --commit        # write changes
    python3 rescore_storage.py --out report.json

The storage vertical lives in the ``properties`` table (the laundromat vertical
uses ``laundry_properties`` and is untouched by this script).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from economics import calculate_economics
from scoring import score_property
from storage_assumptions import SCORING_VERSION


def _latest_analysis(supabase, property_id: str) -> Optional[Dict[str, Any]]:
    rows = (
        supabase.table("analyses").select("*")
        .eq("property_id", property_id).is_("deleted_at", "null")
        .order("created_at", desc=True).limit(1).execute().data
    )
    return rows[0] if rows else None


def _extracted_for(prop: Dict[str, Any], analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if analysis and isinstance(analysis.get("input"), dict) and analysis["input"]:
        return dict(analysis["input"])
    # Fall back to columns stored on the property row.
    keys = ("gba_m2", "asking_price", "asking_rent_month", "rent_per_m2", "price_per_m2_nra",
            "neighbourhood", "city", "address", "ceiling_height", "loading_access",
            "access_type", "floor_level", "building_type", "current_use", "description",
            "latitude", "longitude", "listing_url", "nra_efficiency")
    return {k: prop.get(k) for k in keys if prop.get(k) is not None}


def rescore_all(*, commit: bool = False, limit: Optional[int] = None,
                out_path: Optional[str] = None) -> Dict[str, Any]:
    from database import supabase

    q = supabase.table("properties").select("*").is_("deleted_at", "null").order("created_at", desc=True)
    if limit:
        q = q.limit(limit)
    props: List[Dict[str, Any]] = q.execute().data or []

    before_scores, after_scores = Counter(), Counter()
    before_verdicts, after_verdicts = Counter(), Counter()
    rows: List[Dict[str, Any]] = []
    changed_major: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for prop in props:
        pid = prop.get("id")
        analysis = _latest_analysis(supabase, pid)
        extracted = _extracted_for(prop, analysis)

        old_score = prop.get("score")
        old_verdict = prop.get("verdict")
        old_status = prop.get("deal_status")

        economics = calculate_economics(extracted)
        result = score_property({"extracted": extracted, "economics": economics})
        new_score = result["score"]
        new_verdict = result["verdict_detail"]
        new_status = result["deal_status"]

        def _band(v):
            try:
                v = int(v)
            except (TypeError, ValueError):
                return "unknown"
            return "75+" if v >= 75 else ("40-74" if v >= 40 else "0-39")

        before_scores[_band(old_score)] += 1
        after_scores[_band(new_score)] += 1
        before_verdicts[str(old_status)] += 1
        after_verdicts[new_status] += 1

        delta = None
        try:
            delta = int(new_score) - int(old_score)
        except (TypeError, ValueError):
            pass

        row = {
            "property_id": pid,
            "address": prop.get("address") or prop.get("neighbourhood"),
            "old_score": old_score, "new_score": new_score, "delta": delta,
            "old_verdict": old_verdict, "old_status": old_status,
            "new_verdict": new_verdict, "new_status": new_status,
            "failed_gates": result["gate_failures"],
            "score_caps": [c["reason"] for c in result["score_caps"]],
            "reason": result.get("deal_killer") or (result["gate_failures"][0] if result["gate_failures"] else "recalibrated"),
        }
        rows.append(row)
        if delta is None or abs(delta) >= 15 or old_status != new_status:
            changed_major.append(row)

        if commit:
            supabase.table("analyses").insert({
                "property_id": pid,
                "input": extracted,
                "economics": economics,
                "score": {**result, "previous_score": old_score, "scoring_version": SCORING_VERSION},
                "verdict": result["verdict"],
                "classification": result["classification"],
                "deal_killer": result.get("deal_killer"),
                "ic_memo": (analysis or {}).get("ic_memo"),
            }).execute()
            supabase.table("properties").update({
                "score": new_score, "verdict": result["verdict"],
                "classification": result["classification"], "deal_status": new_status,
            }).eq("id", pid).execute()

    report = {
        "scoring_version": SCORING_VERSION,
        "generated_at": now,
        "committed": commit,
        "count": len(props),
        "score_distribution_before": dict(before_scores),
        "score_distribution_after": dict(after_scores),
        "verdict_distribution_before": dict(before_verdicts),
        "verdict_distribution_after": dict(after_verdicts),
        "major_changes": changed_major,
        "rows": rows,
    }

    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False, default=str)

    return report


def _print(report: Dict[str, Any]) -> None:
    print(f"\nSTORAGE RESCORE — {report['scoring_version']}  "
          f"({'COMMITTED' if report['committed'] else 'DRY RUN'})")
    print(f"Properties processed: {report['count']}")
    print(f"\nScore band   before -> after")
    for band in ("75+", "40-74", "0-39", "unknown"):
        b = report["score_distribution_before"].get(band, 0)
        a = report["score_distribution_after"].get(band, 0)
        if b or a:
            print(f"  {band:8} {b:5} -> {a:5}")
    print(f"\nDeal status  before -> after")
    keys = set(report["verdict_distribution_before"]) | set(report["verdict_distribution_after"])
    for k in sorted(keys):
        print(f"  {k:20} {report['verdict_distribution_before'].get(k,0):5} -> {report['verdict_distribution_after'].get(k,0):5}")
    print(f"\nMajor changes: {len(report['major_changes'])}")
    for r in report["major_changes"][:25]:
        print(f"  {str(r['address'])[:32]:32} {r['old_score']} -> {r['new_score']}  "
              f"{r['old_status']} -> {r['new_status']}  ({r['reason']})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Bulk re-score self-storage properties (v3).")
    ap.add_argument("--commit", action="store_true", help="Write new analyses + update properties.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=str, default="storage_rescore_report.json")
    args = ap.parse_args()

    report = rescore_all(commit=args.commit, limit=args.limit, out_path=args.out)
    _print(report)
    print(f"\nFull report written to {args.out}")
    if not args.commit:
        print("DRY RUN — re-run with --commit to persist. Old analyses are preserved.")


if __name__ == "__main__":
    main()
