"""Integration tests for credit_report_service.

These exercise the real service against a local Postgres database via the
SupabaseShim defined in conftest.py. They cover:
  - draft run creation from CSV bytes
  - bucket assignment (ready / review / excluded / carried)
  - validation persistence
  - read-only query endpoints
  - CSV rendering from DB snapshots

Decision persistence (business flag, review decision), finalize, continuity,
and auto-apply are exercised by later-step tests once those features are
wired up.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services import credit_report_service as svc

_FIXTURES = Path(__file__).parent / "fixtures" / "credit_reports"


def _read_bytes(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


@pytest.fixture
def cycle1_bytes():
    return {
        "deal": _read_bytes("deals_cycle1.csv"),
        "address": _read_bytes("addresses_cycle1.csv"),
    }


@pytest.fixture
def cycle2_bytes():
    return {
        "deal": _read_bytes("deals_cycle2.csv"),
        "address": _read_bytes("addresses_cycle2.csv"),
    }


class TestCreateDraftRun:
    def test_buckets_rows_correctly(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
            user_id=None,
        )
        # 8 deals total in the cycle1 fixture:
        # ready:    d001 Active, d002 Past Due, d003 Paid in Full, d009 In Collections = 4
        # review:   d006 In Legal, d007 Repossessed = 2
        # excluded: d004 Cancelled, d005 Taqueria LLC (business) = 2
        assert result.ready_count == 4
        assert result.review_count == 2
        assert result.excluded_count == 2
        assert result.carried_over_count == 0

    def test_persists_run_row(self, supabase_shim, cycle1_bytes):
        svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        runs = supabase_shim.table("credit_report_runs").select("*").execute().data
        assert len(runs) == 1
        run = runs[0]
        assert run["status"] == "draft"
        assert run["as_of_date_str"] == "20260331"
        assert run["ready_count"] == 4

    def test_persists_run_items(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        items = (
            supabase_shim.table("credit_report_run_items")
            .select("*")
            .eq("run_id", result.run_id)
            .execute()
            .data
        )
        # 4 ready + 2 review + 2 excluded = 8
        assert len(items) == 8
        buckets = {i["bucket"] for i in items}
        assert buckets == {"ready", "review", "excluded"}

    def test_ready_items_have_metro2_row(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        items = (
            supabase_shim.table("credit_report_run_items")
            .select("*")
            .eq("run_id", result.run_id)
            .eq("bucket", "ready")
            .execute()
            .data
        )
        for item in items:
            assert item["metro2_row"] is not None
            # Every Metro 2 column should be present
            for col in [
                "ConsumerAccountNumber",
                "AccountStatus",
                "Surname",
                "FirstName",
                "SSN",
                "Address1",
                "State",
            ]:
                assert col in item["metro2_row"]

    def test_review_items_have_no_metro2_row(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        items = (
            supabase_shim.table("credit_report_run_items")
            .select("*")
            .eq("run_id", result.run_id)
            .eq("bucket", "review")
            .execute()
            .data
        )
        for item in items:
            assert item["metro2_row"] is None
            assert item["reason"]  # has a review reason

    def test_excluded_business_has_auto_flag_source(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        # d005 is "Taqueria Los Amigos LLC" - caught by the is_business regex
        item = (
            supabase_shim.table("credit_report_run_items")
            .select("*")
            .eq("run_id", result.run_id)
            .eq("deal_id", "d005")
            .single()
            .execute()
            .data
        )
        assert item["bucket"] == "excluded"
        assert item["business_flag_source"] == "auto"
        assert "Business" in item["reason"]

    def test_persists_uploads_for_lineage(self, supabase_shim, cycle1_bytes):
        svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        uploads = (
            supabase_shim.table("credit_report_uploads").select("*").execute().data
        )
        kinds = {u["kind"] for u in uploads}
        assert kinds == {"deal", "address"}
        for u in uploads:
            assert u["byte_size"] > 0
            assert len(u["sha256"]) == 64

    def test_persists_validations(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        validations = (
            supabase_shim.table("credit_report_validations")
            .select("*")
            .eq("run_id", result.run_id)
            .execute()
            .data
        )
        assert len(validations) > 0
        # With 4 ready accounts, the MIN_ACCOUNTS warning should appear
        codes = {v["code"] for v in validations}
        assert "MIN_ACCOUNTS" in codes


class TestReadOnlyQueries:
    def test_get_run(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        info = svc.get_run(result.run_id)
        assert info["run"]["id"] == result.run_id
        assert len(info["validations"]) > 0

    def test_list_runs(self, supabase_shim, cycle1_bytes):
        svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        runs = svc.list_runs(limit=10)
        assert len(runs) == 1

    def test_list_run_items_by_bucket(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        ready = svc.list_run_items(result.run_id, bucket="ready")
        assert ready["total"] == 4
        review = svc.list_run_items(result.run_id, bucket="review")
        assert review["total"] == 2
        excluded = svc.list_run_items(result.run_id, bucket="excluded")
        assert excluded["total"] == 2

    def test_list_run_items_search(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        # Searching for "Taqueria" should find d005 in the excluded bucket
        hit = svc.list_run_items(result.run_id, q="Taqueria")
        assert hit["total"] == 1
        assert hit["data"][0]["deal_id"] == "d005"


class TestRenderCsv:
    def test_ready_csv_has_42_columns(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        csv_text = svc.render_csv(result.run_id, "ready")
        lines = csv_text.strip().split("\n")
        # header + 4 data rows
        assert len(lines) == 5
        header = lines[0].split(",")
        from app.libs.metro2_engine import METRO2_COLUMNS
        assert header == list(METRO2_COLUMNS)

    def test_review_csv_has_audit_columns(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        csv_text = svc.render_csv(result.run_id, "review")
        header = csv_text.split("\n")[0]
        assert "deal_id" in header
        assert "clientName" in header
        assert "reason" in header

    def test_invalid_bucket_raises(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        with pytest.raises(ValueError):
            svc.render_csv(result.run_id, "bogus")


class TestSetBusinessFlag:
    def _mk_run(self, shim, cycle1_bytes):
        return svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )

    def test_flag_on_moves_ready_to_excluded(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        # d001 is a ready account
        updated = svc.set_business_flag(
            run_id=result.run_id,
            deal_id="d001",
            is_business=True,
            note="Checked, it's a business",
        )
        assert updated["bucket"] == "excluded"
        assert updated["business_flag_source"] == "manual_on"
        assert "Business" in updated["reason"]

        # Ready count should drop from 4 to 3
        run = svc.get_run(result.run_id)
        assert run["run"]["ready_count"] == 3
        assert run["run"]["excluded_count"] == 3

    def test_flag_off_returns_to_ready(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        # d005 (Taqueria LLC) is auto-flagged as business → excluded
        updated = svc.set_business_flag(
            run_id=result.run_id,
            deal_id="d005",
            is_business=False,
            note="Actually a consumer account",
        )
        # d005 is Active, so after unflagging it should go to ready
        assert updated["bucket"] == "ready"
        assert updated["business_flag_source"] == "manual_off"
        assert updated["metro2_row"] is not None

        # Ready count should climb from 4 to 5
        run = svc.get_run(result.run_id)
        assert run["run"]["ready_count"] == 5
        assert run["run"]["excluded_count"] == 1

    def test_cannot_flag_finalized_run(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        # Manually flip status to final to simulate a finalized run
        supabase_shim.table("credit_report_runs").update({"status": "final"}).eq(
            "id", result.run_id
        ).execute()
        with pytest.raises(ValueError, match="draft"):
            svc.set_business_flag(
                run_id=result.run_id, deal_id="d001", is_business=True
            )


class TestSetReviewDecision:
    def _mk_run(self, shim, cycle1_bytes):
        return svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )

    def test_approve_builds_metro2_row(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        # d007 (Diana Evans) is Repossessed → review bucket
        updated = svc.set_review_decision(
            run_id=result.run_id,
            deal_id="d007",
            decision="approve",
            metro2_status_code="95",
            fcra_dofi="20251015",
            note="Repossession complete, reporting as 95",
        )
        assert updated["bucket"] == "ready"
        assert updated["review_decision"] == "approve"
        assert updated["review_metro2_status_code"] == "95"
        assert updated["review_fcra_dofi"] == "20251015"
        assert updated["metro2_row"]["AccountStatus"] == "95"
        assert updated["metro2_row"]["FCRA_DOFI"] == "20251015"

    def test_approve_without_code_raises(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        with pytest.raises(ValueError, match="metro2_status_code"):
            svc.set_review_decision(
                run_id=result.run_id,
                deal_id="d006",
                decision="approve",
                metro2_status_code=None,
            )

    def test_exclude_moves_to_excluded(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        updated = svc.set_review_decision(
            run_id=result.run_id,
            deal_id="d006",
            decision="exclude",
            note="Case dismissed, don't report",
        )
        assert updated["bucket"] == "excluded"
        assert "Case dismissed" in updated["reason"]

    def test_defer_stays_in_review(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        updated = svc.set_review_decision(
            run_id=result.run_id,
            deal_id="d006",
            decision="defer",
            note="Pending insurance ruling",
        )
        assert updated["bucket"] == "review"
        assert updated["review_decision"] == "defer"

    def test_invalid_decision_raises(self, supabase_shim, cycle1_bytes):
        result = self._mk_run(supabase_shim, cycle1_bytes)
        with pytest.raises(ValueError, match="Invalid decision"):
            svc.set_review_decision(
                run_id=result.run_id,
                deal_id="d006",
                decision="bogus",
            )


class TestRenderReportTxt:
    def test_report_includes_counts(self, supabase_shim, cycle1_bytes):
        result = svc.create_draft_run(
            deal_csv_bytes=cycle1_bytes["deal"],
            deal_filename="deals_cycle1.csv",
            address_csv_bytes=cycle1_bytes["address"],
            address_filename="addresses_cycle1.csv",
            cycle_month=date(2026, 3, 31),
        )
        report = svc.render_report_txt(result.run_id)
        assert "KINGDOM AUTO FINANCE" in report
        assert "READY TO UPLOAD:           4" in report
        assert "FLAGGED FOR REVIEW:        2" in report
        assert "EXCLUDED:                  2" in report
