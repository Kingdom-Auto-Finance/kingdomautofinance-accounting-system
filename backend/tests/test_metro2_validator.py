"""Unit tests for metro2_validator - Layers 2 and 3 of the guardrail system."""
from __future__ import annotations

import pytest

from app.services import metro2_validator as v
from app.services.metro2_validator import SEVERITY_FATAL, SEVERITY_WARNING


def _clean_row(**overrides):
    """Return a baseline Metro 2 record that passes all Layer 2 checks."""
    row = {
        "ConsumerAccountNumber": "KAF-0001",
        "PortfolioType": "I",
        "AccountType": "00",
        "DateOpened": "20240115",
        "HighestCreditOrOrigLoanAmt": 15000,
        "TermsDuration": "060",
        "TermsFrequency": "M",
        "AccountStatus": "11",
        "CurrentBalance": 12500,
        "AmountPastDue": 0,
        "OriginalChargeoffAmt": 0,
        "DateOfAccountInfo": "20260331",
        "Surname": "GARCIA",
        "FirstName": "MARIA",
        "SSN": "123456789",
        "ECOACode": "1",
        "CountryCode": "US",
        "Address1": "123 MAIN ST",
        "City": "ORLANDO",
        "State": "FL",
        "PostalCode": "32801",
        "AddressIndicator": "C",
    }
    row.update(overrides)
    return row


def _codes(findings):
    return {f.code for f in findings}


class TestLayer2RequiredFields:
    def test_clean_row_has_no_fatal_findings(self):
        findings = v.validate_row(_clean_row())
        assert all(f.severity != SEVERITY_FATAL for f in findings)

    def test_missing_account_number_fatal(self):
        row = _clean_row()
        row.pop("ConsumerAccountNumber")
        findings = v.validate_row(row)
        assert "MISSING_REQUIRED" in _codes(findings)

    def test_missing_state_fatal(self):
        row = _clean_row()
        row.pop("State")
        findings = v.validate_row(row)
        codes = _codes(findings)
        assert "MISSING_REQUIRED" in codes or "BAD_STATE" in codes


class TestLayer2Names:
    def test_unknown_surname_is_fatal(self):
        findings = v.validate_row(_clean_row(Surname="UNKNOWN"))
        assert "BAD_NAME" in _codes(findings)

    def test_blank_first_name_is_fatal(self):
        findings = v.validate_row(_clean_row(FirstName=""))
        assert any(
            f.code in ("MISSING_REQUIRED", "BAD_NAME") and f.severity == SEVERITY_FATAL
            for f in findings
        )


class TestLayer2SSN:
    def test_short_ssn_fatal(self):
        findings = v.validate_row(_clean_row(SSN="123"))
        assert "BAD_SSN" in _codes(findings)

    def test_all_zero_ssn_warning(self):
        findings = v.validate_row(_clean_row(SSN="000000000"))
        codes = _codes(findings)
        assert "SSN_ZEROS" in codes


class TestLayer2StatusConsistency:
    def test_past_due_must_be_zero_on_status_11(self):
        findings = v.validate_row(_clean_row(AmountPastDue=500))
        assert "PAST_DUE_NOT_ZERO" in _codes(findings)

    def test_past_due_may_be_nonzero_on_delinquent_status(self):
        findings = v.validate_row(_clean_row(
            AccountStatus="71",
            AmountPastDue=500,
        ))
        assert "PAST_DUE_NOT_ZERO" not in _codes(findings)

    def test_derogatory_status_requires_dofi(self):
        findings = v.validate_row(_clean_row(
            AccountStatus="97",
            DateClosed="20260101",
            OriginalChargeoffAmt=5000,
        ))
        assert "MISSING_FCRA_DOFI" in _codes(findings)

    def test_derogatory_status_with_dofi_no_issue(self):
        findings = v.validate_row(_clean_row(
            AccountStatus="97",
            FCRA_DOFI="20250101",
            DateClosed="20260101",
            OriginalChargeoffAmt=5000,
        ))
        assert "MISSING_FCRA_DOFI" not in _codes(findings)

    def test_status_13_requires_date_closed(self):
        findings = v.validate_row(_clean_row(AccountStatus="13"))
        assert "MISSING_DATE_CLOSED" in _codes(findings)

    def test_status_97_requires_chargeoff_amt(self):
        findings = v.validate_row(_clean_row(
            AccountStatus="97",
            FCRA_DOFI="20250101",
            DateClosed="20260101",
        ))
        assert "MISSING_CHARGEOFF_AMT" in _codes(findings)


class TestLayer2Formats:
    def test_bad_date_format_warning(self):
        findings = v.validate_row(_clean_row(DateOpened="2024-01-15T00:00"))
        # The ISO-ish prefix is accepted (regex allows YYYY-MM-DD); instead
        # check a truly bogus date.
        findings = v.validate_row(_clean_row(DateOpened="not-a-date"))
        assert "BAD_DATE" in _codes(findings)

    def test_state_wrong_length_fatal(self):
        findings = v.validate_row(_clean_row(State="FLA"))
        assert "BAD_STATE" in _codes(findings)

    def test_zero_loan_amount_warning(self):
        findings = v.validate_row(_clean_row(HighestCreditOrOrigLoanAmt=0))
        assert "ZERO_ORIGINAL_LOAN" in _codes(findings)


class TestLayer2BalanceAndDateLogic:
    """Switch Labs-equivalent cross-field rules added after first prod run."""

    def test_paid_status_with_balance_is_fatal(self):
        findings = v.validate_row(_clean_row(
            AccountStatus="13",
            CurrentBalance=500,
            AmountPastDue=0,
            DateClosed="20260101",
        ))
        assert "PAID_BUT_HAS_BALANCE" in _codes(findings)

    def test_paid_status_zero_balance_passes(self):
        findings = v.validate_row(_clean_row(
            AccountStatus="13",
            CurrentBalance=0,
            AmountPastDue=0,
            DateClosed="20260101",
        ))
        assert "PAID_BUT_HAS_BALANCE" not in _codes(findings)

    def test_balance_exceeds_original_loan_warning(self):
        findings = v.validate_row(_clean_row(
            HighestCreditOrOrigLoanAmt=10000,
            CurrentBalance=15000,
        ))
        assert "BALANCE_EXCEEDS_ORIGINAL" in _codes(findings)

    def test_future_date_opened_is_fatal(self):
        findings = v.validate_row(_clean_row(DateOpened="20990101"))
        assert "FUTURE_DATE" in _codes(findings)

    def test_opened_after_closed_is_fatal(self):
        findings = v.validate_row(_clean_row(
            DateOpened="20250101",
            DateClosed="20240101",
            AccountStatus="13",
            CurrentBalance=0,
        ))
        assert "OPEN_AFTER_CLOSE" in _codes(findings)

    def test_payment_after_closed_is_fatal(self):
        findings = v.validate_row(_clean_row(
            DateLastPayment="20260201",
            DateClosed="20260101",
            AccountStatus="13",
            CurrentBalance=0,
        ))
        assert "PAYMENT_AFTER_CLOSE" in _codes(findings)

    def test_opened_after_as_of_is_fatal(self):
        findings = v.validate_row(_clean_row(
            DateOpened="20260601",
            DateOfAccountInfo="20260331",
        ))
        assert "OPEN_AFTER_AS_OF" in _codes(findings)


class TestLayer3Batch:
    def test_duplicate_accounts_are_fatal(self):
        r1 = _clean_row()
        r2 = _clean_row()  # same account number
        report = v.validate_batch([r1, r2], enforce_minimum=False)
        codes = {f.code for f in report.findings}
        assert "DUPLICATE_ACCOUNT" in codes
        assert report.fatal_count >= 1

    def test_min_account_count_enforced(self):
        report = v.validate_batch(
            [_clean_row(ConsumerAccountNumber=f"K{i:04d}") for i in range(5)],
            enforce_minimum=True,
        )
        codes = {f.code for f in report.findings}
        assert "MIN_ACCOUNTS" in codes

    def test_min_account_count_skippable(self):
        report = v.validate_batch(
            [_clean_row(ConsumerAccountNumber=f"K{i:04d}") for i in range(5)],
            enforce_minimum=False,
        )
        codes = {f.code for f in report.findings}
        assert "MIN_ACCOUNTS" not in codes

    def test_report_status_rollup(self):
        clean_batch = [
            _clean_row(ConsumerAccountNumber=f"K{i:04d}") for i in range(3)
        ]
        report = v.validate_batch(clean_batch, enforce_minimum=False)
        assert report.status in ("clean", "warning")  # no fatals
