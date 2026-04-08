"""Unit tests for backend.app.libs.metro2_engine.

These tests guard the Metro 2 business rules against regressions. Every
function moved from the original metro2_generator.py has at least one test
that pins its behavior.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.libs import metro2_engine as m


# ─── parse_name ──────────────────────────────────────────────────────────────
class TestParseName:
    def test_two_part_name(self):
        assert m.parse_name("John Smith") == ("Smith", "John", "")

    def test_hispanic_two_surnames(self):
        assert m.parse_name("Juan Carlos Rodriguez Lopez") == (
            "Rodriguez Lopez",
            "Juan",
            "Carlos",
        )

    def test_three_part_name_treats_last_two_as_surname(self):
        # First Surname1 Surname2 → Surname = "Surname1 Surname2"
        assert m.parse_name("Maria Garcia Lopez") == ("Garcia Lopez", "Maria", "")

    def test_single_name_returns_unknown_first(self):
        assert m.parse_name("Madonna") == ("Madonna", "UNKNOWN", "")

    def test_empty_returns_unknown(self):
        assert m.parse_name("") == ("UNKNOWN", "UNKNOWN", "")
        assert m.parse_name(None) == ("UNKNOWN", "UNKNOWN", "")

    def test_business_suffix_stripped(self):
        # "LLC" is scrubbed, leaving "Acme Garcia" → First=Acme, Surname=Garcia
        surname, first, _ = m.parse_name("Acme LLC Garcia")
        assert "LLC" not in surname
        assert "LLC" not in first

    def test_length_limits_enforced(self):
        long = "Alexandrina Theodosia Juliana Maria Rodriguez Washington"
        surname, first, middle = m.parse_name(long)
        assert len(surname) <= 25
        assert len(first) <= 15
        assert len(middle) <= 15


# ─── to_metro2_date ──────────────────────────────────────────────────────────
class TestToMetro2Date:
    def test_iso_date(self):
        assert m.to_metro2_date("2024-05-15") == "20240515"

    def test_iso_datetime_with_zulu(self):
        assert m.to_metro2_date("2024-05-15T10:30:00.000Z") == "20240515"
        assert m.to_metro2_date("2024-05-15T10:30:00Z") == "20240515"

    def test_slash_format(self):
        assert m.to_metro2_date("05/15/2024") == "20240515"

    def test_already_metro2_format(self):
        assert m.to_metro2_date("20240515") == "20240515"

    def test_invalid_returns_empty(self):
        assert m.to_metro2_date("not a date") == ""
        assert m.to_metro2_date("") == ""
        assert m.to_metro2_date(None) == ""


# ─── get_ssn ─────────────────────────────────────────────────────────────────
class TestGetSsn:
    def test_strips_dashes(self):
        assert m.get_ssn("123-45-6789", "SSN") == "123456789"

    def test_zero_pads_short(self):
        assert m.get_ssn("12345", "SSN") == "000012345"

    def test_non_ssn_doctype_returns_zeros(self):
        assert m.get_ssn("AB1234567", "Passport") == "000000000"

    def test_missing_document_returns_zeros(self):
        assert m.get_ssn(None, "SSN") == "000000000"
        assert m.get_ssn(None, None) == "000000000"

    def test_mixed_case_doctype(self):
        assert m.get_ssn("123456789", "ssn") == "123456789"
        assert m.get_ssn("123456789", "Ssn") == "123456789"


# ─── map_account_status ──────────────────────────────────────────────────────
class TestMapAccountStatus:
    def test_active_returns_11(self):
        code, rating, past_due = m.map_account_status("Active", 0)
        assert code == "11"
        assert past_due == "0"

    def test_past_due_returns_11(self):
        # Kingdom reports all delinquent as current (11) per business rules
        assert m.map_account_status("Past Due", 45)[0] == "11"

    def test_in_collections_returns_11(self):
        assert m.map_account_status("In Collections", 90)[0] == "11"

    def test_paid_in_full_returns_13(self):
        code, rating, _ = m.map_account_status("Paid in Full", 0)
        assert code == "13"
        assert rating == "0"

    def test_review_status_returns_marker(self):
        for status in ("In Legal", "Repossessed", "Write-Off", "Recourse", "Contract Sold"):
            assert m.map_account_status(status, 0)[0] == "REVIEW"


# ─── terms_duration ──────────────────────────────────────────────────────────
class TestTermsDuration:
    def test_monthly_passthrough(self):
        code, months = m.terms_duration("monthly", 60)
        assert code == "M"
        assert months == "060"

    def test_biweekly_halves(self):
        # 104 bi-weekly payments ≈ 48 months (104 * 12 / 26)
        code, months = m.terms_duration("bi-weekly", 104)
        assert code == "B"
        assert months == "048"

    def test_weekly_quarters(self):
        # 208 weekly payments ≈ 48 months
        code, months = m.terms_duration("weekly", 208)
        assert code == "W"
        assert months == "048"

    def test_semi_monthly(self):
        code, months = m.terms_duration("semi-monthly", 120)
        assert code == "S"
        assert months == "060"

    def test_clamps_to_max_999(self):
        _, months = m.terms_duration("monthly", 5000)
        assert months == "999"

    def test_clamps_to_min_001(self):
        _, months = m.terms_duration("monthly", 0.1)
        # round(0.1) → 0, should clamp to min 1
        assert months == "001"

    def test_unknown_frequency_defaults_monthly(self):
        code, months = m.terms_duration("quarterly", 24)
        assert code == "M"

    def test_nan_returns_zero_months(self):
        code, months = m.terms_duration("monthly", float("nan"))
        assert months == "000"


# ─── clean_balance / clean_amount ────────────────────────────────────────────
class TestCleanAmounts:
    def test_negative_balance_floors_to_zero(self):
        assert m.clean_balance(-50.25) == "0"

    def test_positive_balance_rounds(self):
        assert m.clean_balance(1234.56) == "1235"

    def test_nan_balance_returns_zero(self):
        assert m.clean_balance(float("nan")) == "0"

    def test_clean_amount_abs_value(self):
        # Unlike clean_balance, clean_amount uses absolute value
        assert m.clean_amount(-500) == "500"

    def test_clean_amount_rounds(self):
        assert m.clean_amount(12345.67) == "12346"


# ─── format_postal ───────────────────────────────────────────────────────────
class TestFormatPostal:
    def test_strips_dash(self):
        assert m.format_postal("01234-5678") == "012345678"

    def test_pads_short(self):
        assert m.format_postal("123") == "00123"

    def test_empty_returns_empty(self):
        assert m.format_postal("") == ""
        assert m.format_postal(None) == ""

    def test_strips_letters(self):
        # Canadian postal codes: "M5H 2N2" → digits "522" → zero-padded "00522"
        assert m.format_postal("M5H 2N2") == "00522"

    def test_five_digit_unchanged(self):
        assert m.format_postal("75201") == "75201"


# ─── is_business ─────────────────────────────────────────────────────────────
class TestIsBusiness:
    @pytest.mark.parametrize(
        "name",
        [
            "Acme LLC",
            "Taqueria Los Amigos",
            "Johnson INC",
            "Global Corp",
            "Cleaning Services",
            "Davis Enterprise",
            "Smith Associates",
        ],
    )
    def test_business_detected(self, name):
        assert m.is_business(name) is True

    @pytest.mark.parametrize(
        "name",
        ["John Smith", "Maria Garcia", "Bob Johnson", "Alice Brown"],
    )
    def test_consumer_not_flagged(self, name):
        assert m.is_business(name) is False


# ─── deduplicate_refinanced ──────────────────────────────────────────────────
class TestDeduplicateRefinanced:
    def test_marks_old_when_active_twin_exists(self):
        df = pd.DataFrame([
            {"_id": "d1", "clientName": "John Smith", "statusName": "Active"},
            {"_id": "d2", "clientName": "John Smith", "statusName": "Refinanced"},
        ])
        result = m.deduplicate_refinanced(df)
        assert result.loc[result["_id"] == "d2", "refinance_duplicate"].item() is True
        assert result.loc[result["_id"] == "d1", "refinance_duplicate"].item() is False

    def test_no_twin_not_marked(self):
        df = pd.DataFrame([
            {"_id": "d1", "clientName": "Jane Doe", "statusName": "Refinanced"},
        ])
        result = m.deduplicate_refinanced(df)
        assert bool(result.loc[0, "refinance_duplicate"]) is False


# ─── merge_deals_addresses ───────────────────────────────────────────────────
class TestMergeDealsAddresses:
    def test_successful_merge(self):
        deals = pd.DataFrame([
            {"_id": "d1", "dealAddressId": "a1"},
            {"_id": "d2", "dealAddressId": "a2"},
        ])
        addrs = pd.DataFrame([
            {"_id": "a1", "address": "1 Main", "address2": "", "city": "Dallas", "state": "TX", "zip": "75201"},
            {"_id": "a2", "address": "2 Oak", "address2": "", "city": "Houston", "state": "TX", "zip": "77001"},
        ])
        merged, findings = m.merge_deals_addresses(deals, addrs)
        assert len(merged) == 2
        assert merged.loc[merged["_id"] == "d1", "address1"].item() == "1 Main"
        assert merged.loc[merged["_id"] == "d1", "city"].item() == "Dallas"

    def test_missing_address_file_emits_warning(self):
        deals = pd.DataFrame([{"_id": "d1", "dealAddressId": "a1"}])
        merged, findings = m.merge_deals_addresses(deals, None)
        assert "address1" in merged.columns
        assert (merged["address1"] == "").all()
        assert any(f.code == m.CODE_MISSING_ADDRESS for f in findings)

    def test_street_and_zipCode_variants(self):
        """Real Kingdom export uses street/zipCode - must map automatically."""
        deals = pd.DataFrame([{"_id": "d1", "dealAddressId": "a1"}])
        addrs = pd.DataFrame([
            {
                "_id": "a1",
                "street": "3028 Chamblee Tucker Rd",
                "state": "GA",
                "city": "Atlanta",
                "zipCode": "30341",
            }
        ])
        merged, findings = m.merge_deals_addresses(deals, addrs)
        assert merged.loc[0, "address1"] == "3028 Chamblee Tucker Rd"
        assert merged.loc[0, "city"] == "Atlanta"
        assert merged.loc[0, "state"] == "GA"
        assert merged.loc[0, "postal_code"] == "30341"
        # Match rate should be 100% since every deal has an address.
        match_finding = next(f for f in findings if f.code == "ADDRESS_MATCH_RATE")
        assert "100.0%" in match_finding.message

    def test_addressLine1_variant(self):
        deals = pd.DataFrame([{"_id": "d1", "dealAddressId": "a1"}])
        addrs = pd.DataFrame([
            {
                "_id": "a1",
                "addressLine1": "1 Main",
                "addressLine2": "Apt 2",
                "city": "Dallas",
                "state": "TX",
                "postalCode": "75201",
            }
        ])
        merged, findings = m.merge_deals_addresses(deals, addrs)
        assert merged.loc[0, "address1"] == "1 Main"
        assert merged.loc[0, "address2"] == "Apt 2"
        assert merged.loc[0, "postal_code"] == "75201"

    def test_unknown_column_emits_warning_with_available_list(self):
        """When no candidate matches, the operator should be told what's in the file."""
        deals = pd.DataFrame([{"_id": "d1", "dealAddressId": "a1"}])
        addrs = pd.DataFrame([
            {"_id": "a1", "rua": "1 Main", "cidade": "Dallas", "cep": "75201"}
        ])
        merged, findings = m.merge_deals_addresses(deals, addrs)
        # No match → address1 should be blank
        assert merged.loc[0, "address1"] == ""
        # And we should get a warning listing the actual columns available
        avail_finding = next(
            f for f in findings if f.code == "ADDRESS_COLUMNS_AVAILABLE"
        )
        assert "rua" in avail_finding.message
        assert "cidade" in avail_finding.message
        # And at least one unresolved field warning (address1 / city / state)
        assert any(
            f.code == m.CODE_MISSING_COLUMN and "address1" in f.message
            for f in findings
        )

    def test_fields_mapped_finding_surfaces_picks(self):
        deals = pd.DataFrame([{"_id": "d1", "dealAddressId": "a1"}])
        addrs = pd.DataFrame([
            {
                "_id": "a1",
                "street": "1 Main",
                "city": "Dallas",
                "state": "TX",
                "zipCode": "75201",
            }
        ])
        _, findings = m.merge_deals_addresses(deals, addrs)
        mapped = next(f for f in findings if f.code == "ADDRESS_FIELDS_MAPPED")
        assert "address1=street" in mapped.message
        assert "postal_code=zipCode" in mapped.message


# ─── transform ───────────────────────────────────────────────────────────────
class TestTransform:
    @pytest.fixture
    def sample_df(self):
        rows = [
            # 1. Active consumer - ready
            {"_id": "d001", "clientName": "John Smith", "statusName": "Active",
             "loanAmount": 15000, "loanDate": "2024-01-15", "accountBalance": 8500,
             "lastPaymentDate": "2026-03-01", "daysPastDue": 0, "frequency": "monthly",
             "numberOfPayments": 60, "paymentAmount": 350, "lastAmountPaid": 350,
             "document": "123456789", "documentType": "SSN", "birthdate": "1985-06-15",
             "phoneNumber": "5551234567", "dealAddressId": "a001",
             "address1": "123 Main", "address2": "", "city": "Dallas", "state": "TX", "postal_code": "75201"},
            # 2. Cancelled - excluded
            {"_id": "d002", "clientName": "Alice Brown", "statusName": "Cancelled",
             "loanAmount": 5000, "loanDate": "2025-01-01", "accountBalance": 5000,
             "lastPaymentDate": "", "daysPastDue": 0, "frequency": "monthly",
             "numberOfPayments": 24, "paymentAmount": 220, "lastAmountPaid": 0,
             "document": "", "documentType": "", "birthdate": "1992-04-10",
             "phoneNumber": "5553334444", "dealAddressId": "a002",
             "address1": "456 Oak", "address2": "", "city": "Houston", "state": "TX", "postal_code": "77001"},
            # 3. Business - excluded
            {"_id": "d003", "clientName": "Taqueria LLC", "statusName": "Active",
             "loanAmount": 25000, "loanDate": "2024-03-20", "accountBalance": 18000,
             "lastPaymentDate": "2026-03-10", "daysPastDue": 0, "frequency": "monthly",
             "numberOfPayments": 60, "paymentAmount": 480, "lastAmountPaid": 480,
             "document": "", "documentType": "", "birthdate": "",
             "phoneNumber": "5554445555", "dealAddressId": "a003",
             "address1": "555 Commerce", "address2": "", "city": "Dallas", "state": "TX", "postal_code": "75201"},
            # 4. In Legal - review
            {"_id": "d004", "clientName": "Charles Davis", "statusName": "In Legal",
             "loanAmount": 18000, "loanDate": "2023-11-05", "accountBalance": 14000,
             "lastPaymentDate": "2025-12-01", "daysPastDue": 90, "frequency": "monthly",
             "numberOfPayments": 60, "paymentAmount": 360, "lastAmountPaid": 360,
             "document": "222334455", "documentType": "SSN", "birthdate": "1980-07-22",
             "phoneNumber": "5556667777", "dealAddressId": "a004",
             "address1": "100 Liberty", "address2": "", "city": "Fort Worth", "state": "TX", "postal_code": "76101"},
            # 5. Paid in Full - ready with status 13
            {"_id": "d005", "clientName": "Bob Johnson", "statusName": "Paid in Full",
             "loanAmount": 10000, "loanDate": "2022-05-01", "accountBalance": 0,
             "lastPaymentDate": "2026-03-15", "daysPastDue": 0, "frequency": "monthly",
             "numberOfPayments": 48, "paymentAmount": 250, "lastAmountPaid": 250,
             "document": "111223333", "documentType": "SSN", "birthdate": "1975-11-30",
             "phoneNumber": "5551112222", "dealAddressId": "a005",
             "address1": "789 Pine", "address2": "", "city": "Austin", "state": "TX", "postal_code": "73301"},
        ]
        return pd.DataFrame(rows)

    def test_buckets_correctly(self, sample_df):
        ready, review, excluded = m.transform(sample_df, "20260331")
        assert len(ready) == 2  # d001, d005
        assert len(review) == 1  # d004
        assert len(excluded) == 2  # d002, d003

    def test_ready_row_has_42_metro2_columns(self, sample_df):
        ready, _, _ = m.transform(sample_df, "20260331")
        for col in m.METRO2_COLUMNS:
            assert col in ready.columns

    def test_ready_row_values(self, sample_df):
        ready, _, _ = m.transform(sample_df, "20260331")
        d001 = ready[ready["ConsumerAccountNumber"] == "d001"].iloc[0]
        assert d001["AccountStatus"] == "11"
        assert d001["TermsFrequency"] == "M"
        assert d001["TermsDuration"] == "060"
        assert d001["Surname"] == "Smith"
        assert d001["FirstName"] == "John"
        assert d001["SSN"] == "123456789"
        assert d001["DateOfBirth"] == "19850615"
        assert d001["State"] == "TX"
        assert d001["PostalCode"] == "75201"

    def test_paid_in_full_gets_status_13_and_date_closed(self, sample_df):
        ready, _, _ = m.transform(sample_df, "20260331")
        d005 = ready[ready["ConsumerAccountNumber"] == "d005"].iloc[0]
        assert d005["AccountStatus"] == "13"
        assert d005["DateClosed"] == "20260315"

    def test_excluded_rows_have_reasons(self, sample_df):
        _, _, excluded = m.transform(sample_df, "20260331")
        reasons = set(excluded["reason"].tolist())
        assert any("Cancelled" in r for r in reasons)
        assert any("Business" in r for r in reasons)


# ─── validate ────────────────────────────────────────────────────────────────
class TestValidate:
    def _good_row(self) -> dict:
        return {col: "X" for col in m.REQUIRED_COLUMNS}

    def test_min_accounts_fatal_when_enforced(self):
        df = pd.DataFrame([self._good_row()])
        findings = m.validate(df, min_accounts=100, enforce_minimum=True)
        min_finding = next(f for f in findings if f.code == m.CODE_MIN_ACCOUNTS)
        assert min_finding.severity == "FATAL"

    def test_min_accounts_warning_when_not_enforced(self):
        df = pd.DataFrame([self._good_row()])
        findings = m.validate(df, min_accounts=100, enforce_minimum=False)
        min_finding = next(f for f in findings if f.code == m.CODE_MIN_ACCOUNTS)
        assert min_finding.severity == "WARNING"

    def test_missing_column_emits_fatal(self):
        df = pd.DataFrame([{"SSN": "123456789"}])  # missing most required cols
        findings = m.validate(df, enforce_minimum=False)
        assert any(f.severity == "FATAL" and f.code == m.CODE_MISSING_COLUMN for f in findings)

    def test_duplicate_account_number_fatal(self):
        row = self._good_row()
        df = pd.DataFrame([row, row])  # Two identical rows → dup account number
        findings = m.validate(df, enforce_minimum=False)
        assert any(f.code == m.CODE_DUP_ACCOUNT_NUMBER for f in findings)

    def test_returns_structured_findings(self):
        df = pd.DataFrame([self._good_row()])
        findings = m.validate(df, enforce_minimum=False)
        for f in findings:
            assert isinstance(f, m.ValidationFinding)
            assert f.severity in ("FATAL", "WARNING", "INFO")
            assert isinstance(f.code, str)
            assert isinstance(f.message, str)


# ─── build_metro2_row ────────────────────────────────────────────────────────
class TestBuildMetro2Row:
    def _sample_row(self) -> dict:
        return {
            "_id": "deal-123",
            "clientName": "Jane Doe",
            "statusName": "Active",
            "loanAmount": 10000,
            "loanDate": "2024-01-01",
            "accountBalance": 5000,
            "lastPaymentDate": "2026-03-01",
            "daysPastDue": 0,
            "frequency": "monthly",
            "numberOfPayments": 48,
            "paymentAmount": 250,
            "lastAmountPaid": 250,
            "document": "123456789",
            "documentType": "SSN",
            "birthdate": "1990-01-01",
            "phoneNumber": "5551234567",
            "address1": "1 Main St",
            "address2": "",
            "city": "Dallas",
            "state": "TX",
            "postal_code": "75201",
        }

    def test_all_columns_present(self):
        row = m.build_metro2_row(self._sample_row(), "20260331")
        for col in m.METRO2_COLUMNS:
            assert col in row

    def test_override_applies_status_and_dofi(self):
        row = m.build_metro2_row(
            self._sample_row(),
            "20260331",
            account_status_override="95",
            fcra_dofi_override="20250812",
        )
        assert row["AccountStatus"] == "95"
        assert row["FCRA_DOFI"] == "20250812"

    def test_default_status_used_without_override(self):
        row = m.build_metro2_row(self._sample_row(), "20260331")
        assert row["AccountStatus"] == "11"  # Active → 11
        assert row["FCRA_DOFI"] == ""
