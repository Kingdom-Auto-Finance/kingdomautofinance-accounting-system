"""API-level smoke tests for credit_reports router.

Exercises the FastAPI endpoints via a TestClient. Uses the SupabaseShim
from conftest so requests hit the real Postgres test database.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_FIXTURES = Path(__file__).parent / "fixtures" / "credit_reports"


@pytest.fixture
def app(supabase_shim):
    """Build a minimal FastAPI app with only the credit_reports router.

    We don't mount the full app because that would pull in google_validator
    and other services that need live credentials.
    """
    from app.api import credit_reports

    app = FastAPI()
    app.include_router(credit_reports.router, prefix="/api/v1/credit-reports")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _open_fixture(name: str) -> tuple[str, io.BytesIO, str]:
    return (name, io.BytesIO((_FIXTURES / name).read_bytes()), "text/csv")


class TestCreateDraftEndpoint:
    def test_happy_path(self, client):
        response = client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "2026-03-31"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert "run_id" in body
        assert body["ready_count"] == 4
        assert body["review_count"] == 2
        assert body["excluded_count"] == 2

    def test_invalid_cycle_month(self, client):
        response = client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "not-a-date"},
        )
        assert response.status_code == 400


class TestListRunsEndpoint:
    def test_empty(self, client):
        response = client.get("/api/v1/credit-reports/runs")
        assert response.status_code == 200
        assert response.json() == {"data": [], "count": 0}

    def test_after_draft(self, client):
        client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "2026-03-31"},
        )
        response = client.get("/api/v1/credit-reports/runs")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["data"][0]["status"] == "draft"


class TestGetRunAndItems:
    def test_get_run_and_list_items(self, client):
        draft_resp = client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "2026-03-31"},
        )
        run_id = draft_resp.json()["run_id"]

        # GET /runs/{id}
        resp = client.get(f"/api/v1/credit-reports/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["run"]["ready_count"] == 4
        assert len(resp.json()["validations"]) > 0

        # GET /runs/{id}/items?bucket=ready
        resp = client.get(
            f"/api/v1/credit-reports/runs/{run_id}/items",
            params={"bucket": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 4

        resp = client.get(
            f"/api/v1/credit-reports/runs/{run_id}/items",
            params={"bucket": "review"},
        )
        assert resp.json()["total"] == 2

    def test_invalid_bucket_returns_400(self, client):
        draft_resp = client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "2026-03-31"},
        )
        run_id = draft_resp.json()["run_id"]
        resp = client.get(
            f"/api/v1/credit-reports/runs/{run_id}/items",
            params={"bucket": "bogus"},
        )
        assert resp.status_code == 400


class TestGetRules:
    def test_returns_all_rule_categories(self, client):
        resp = client.get("/api/v1/credit-reports/rules")
        assert resp.status_code == 200
        body = resp.json()
        assert "experian_config" in body
        assert body["experian_config"]["identification_number"] == "3983542"
        assert "status_buckets" in body
        assert "Cancelled" in body["status_buckets"]["excluded"]
        assert "In Legal" in body["status_buckets"]["review"]
        assert "Active" in body["status_buckets"]["active_reported_as_11"]
        assert "business_pattern" in body
        assert "frequency_map" in body
        assert body["frequency_map"]["bi-weekly"]["metro2_code"] == "B"
        assert "address_field_candidates" in body
        assert "street" in body["address_field_candidates"]["address1"]
        assert "zipCode" in body["address_field_candidates"]["postal_code"]


class TestDownload:
    def test_download_ready_csv(self, client):
        draft_resp = client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "2026-03-31"},
        )
        run_id = draft_resp.json()["run_id"]
        resp = client.get(f"/api/v1/credit-reports/runs/{run_id}/download/ready")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 5  # header + 4 rows
        assert "ConsumerAccountNumber" in lines[0]

    def test_download_report_txt(self, client):
        draft_resp = client.post(
            "/api/v1/credit-reports/runs/draft",
            files={
                "deal_csv": _open_fixture("deals_cycle1.csv"),
                "address_csv": _open_fixture("addresses_cycle1.csv"),
            },
            data={"cycle_month": "2026-03-31"},
        )
        run_id = draft_resp.json()["run_id"]
        resp = client.get(f"/api/v1/credit-reports/runs/{run_id}/download-report")
        assert resp.status_code == 200
        assert "KINGDOM AUTO FINANCE" in resp.text
