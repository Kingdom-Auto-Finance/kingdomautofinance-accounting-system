"""Kingdom Auto Finance - Metro 2 CLI shim.

Thin command-line wrapper around ``backend.app.libs.metro2_engine`` for
engineers who need to generate the monthly Metro 2 file without the web UI
(e.g. month-end emergencies when the backend is unavailable).

The full Metro 2 transformation logic lives in
``backend/app/libs/metro2_engine.py``. This script only handles file I/O
(reading the two CSV exports, writing the three output CSVs and the summary
report).

HOW TO EXPORT FROM MONGODB (run in MongoDB shell or Compass):
─────────────────────────────────────────────────────────────
  # Deals collection
  mongoexport --db=<your_db> --collection=deals \\
    --type=csv --fields=... --out=kingdomautofinance_Deal.csv

  # Addresses collection
  mongoexport --db=<your_db> --collection=dealaddresses \\
    --type=csv --fields=_id,address,address2,city,state,zip,postalCode \\
    --out=kingdomautofinance_Address.csv

  Or export from MongoDB Compass as CSV - both collections separately.

USAGE:
  python metro2_generator.py

REQUIREMENTS:
  pip install pandas
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd

# Make the backend package importable when running from the repo root.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_THIS_DIR, "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.libs.metro2_engine import (  # noqa: E402
    get_as_of_date,
    merge_deals_addresses,
    transform,
    validate,
)

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
DEALS_CSV = "kingdomautofinance_Deal.csv"
ADDRESS_CSV = "kingdomautofinance_Address.csv"
AS_OF_DATE_OVERRIDE: str | None = None  # e.g. "20260331"


def main() -> int:
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Kingdom Auto Finance - Metro 2 Generator (CLI)     ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    as_of_date = get_as_of_date(AS_OF_DATE_OVERRIDE)
    month_label = as_of_date[:6]
    print(f"As-of date: {as_of_date}  (last day of prior month)")

    output_dir = _THIS_DIR

    # ── LOAD ────────────────────────────────────────────────────────────
    print(f"\nLoading deals from: {DEALS_CSV}")
    if not os.path.exists(DEALS_CSV):
        print(f"  ✗ Deal file not found at '{DEALS_CSV}'")
        return 1
    deals_df = pd.read_csv(DEALS_CSV, dtype=str)
    print(f"  → {len(deals_df)} deal records loaded")

    addresses_df = None
    if os.path.exists(ADDRESS_CSV):
        print(f"Loading addresses from: {ADDRESS_CSV}")
        addresses_df = pd.read_csv(ADDRESS_CSV, dtype=str)
        print(f"  → {len(addresses_df)} address records loaded")
    else:
        print(f"  ⚠ Address file not found at '{ADDRESS_CSV}'")

    # ── MERGE + TRANSFORM ───────────────────────────────────────────────
    merged_df, merge_findings = merge_deals_addresses(deals_df, addresses_df)
    for f in merge_findings:
        print(f"  [{f.severity}] {f.message}")

    print(f"\nProcessing {len(merged_df)} records...")
    ready_df, review_df, excluded_df = transform(merged_df, as_of_date)
    print(f"  → Ready:    {len(ready_df)}")
    print(f"  → Review:   {len(review_df)}")
    print(f"  → Excluded: {len(excluded_df)}")

    # ── VALIDATE ────────────────────────────────────────────────────────
    findings = validate(ready_df, min_accounts=100, enforce_minimum=True)

    # ── WRITE OUTPUTS ───────────────────────────────────────────────────
    ready_path = os.path.join(output_dir, f"metro2_ready_{month_label}.csv")
    review_path = os.path.join(output_dir, f"metro2_review_{month_label}.csv")
    excluded_path = os.path.join(output_dir, f"metro2_excluded_{month_label}.csv")
    report_path = os.path.join(output_dir, f"metro2_report_{month_label}.txt")

    ready_df.to_csv(ready_path, index=False, encoding="utf-8")
    review_df.to_csv(review_path, index=False, encoding="utf-8")
    excluded_df.to_csv(excluded_path, index=False, encoding="utf-8")

    print("\nFiles written:")
    print(f"  {ready_path}")
    print(f"  {review_path}")
    print(f"  {excluded_path}")

    # ── SUMMARY REPORT ──────────────────────────────────────────────────
    report_lines = [
        "=" * 60,
        "KINGDOM AUTO FINANCE - Metro 2 Generation Report",
        f"As-of date:   {as_of_date}",
        f"Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"READY TO UPLOAD:           {len(ready_df)} accounts",
        f"FLAGGED FOR REVIEW:        {len(review_df)} accounts",
        f"EXCLUDED:                  {len(excluded_df)} accounts",
        f"TOTAL INPUT ROWS:          {len(ready_df) + len(review_df) + len(excluded_df)}",
    ]

    if len(review_df) > 0:
        report_lines.append("\n── REVIEW REQUIRED ──────────────────────────────────────")
        for _, r in review_df.iterrows():
            report_lines.append(
                f"  [{r.get('statusName','')}] {r.get('clientName','')} "
                f"→ {r.get('review_reason','')}"
            )

    report_lines.append("\n── VALIDATION RESULTS ───────────────────────────────────")
    fatals = [f for f in findings if f.severity == "FATAL"]
    warns = [f for f in findings if f.severity == "WARNING"]
    infos = [f for f in findings if f.severity == "INFO"]
    for f in fatals + warns + infos:
        report_lines.append(f"  [{f.severity}] {f.code}: {f.message}")
    if not findings:
        report_lines.append("  All checks passed.")

    report_lines.append("\n── NEXT STEPS ───────────────────────────────────────────")
    if fatals:
        report_lines.append("  ✗ FATAL errors found - DO NOT upload until resolved.")
    else:
        report_lines.append(f"  1. Upload metro2_ready_{month_label}.csv to Switch Labs")
        report_lines.append("  2. Run Switch Labs validation - fix any warnings")
        report_lines.append(f"  3. Review metro2_review_{month_label}.csv")
        report_lines.append("  4. Upload final file to Experian STS by the 5th of the month")
    report_lines.append("=" * 60)

    report_text = "\n".join(report_lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print("\n" + report_text)

    return 1 if fatals else 0


if __name__ == "__main__":
    sys.exit(main())
