"""Unit tests for metro2_builder - byte-exact header / base / trailer assembly.

These tests are pure-Python and do not require a database. They exercise
Layer 4 of the six-layer guardrail system.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import metro2_builder as builder
from app.services import metro2_schema as schema


# ─── Formatters ──────────────────────────────────────────────────────────────
class TestFormatters:
    def test_alphanumeric_left_justifies_uppercases_and_pads(self):
        out = builder.format_alphanumeric("maria", 10)
        assert out == "MARIA     "
        assert len(out) == 10

    def test_alphanumeric_truncates(self):
        out = builder.format_alphanumeric("ABCDEFGHIJKL", 5)
        assert out == "ABCDE"

    def test_alphanumeric_strips_newlines_tabs(self):
        out = builder.format_alphanumeric("A\nB\tC", 5)
        assert out == "A B C"

    def test_alphanumeric_none_is_blank(self):
        assert builder.format_alphanumeric(None, 4) == "    "

    def test_alphanumeric_non_ascii_replaced(self):
        out = builder.format_alphanumeric("CAFÉ", 4)
        assert len(out) == 4
        assert out.isascii()

    def test_numeric_right_justifies_zero_pads(self):
        assert builder.format_numeric(42, 5) == "00042"

    def test_numeric_handles_float(self):
        assert builder.format_numeric(42.7, 5) == "00043"

    def test_numeric_handles_str(self):
        assert builder.format_numeric("123", 5) == "00123"

    def test_numeric_coerces_blank_to_zero(self):
        assert builder.format_numeric("", 3) == "000"
        assert builder.format_numeric(None, 3) == "000"

    def test_numeric_clamps_negative_to_zero(self):
        assert builder.format_numeric(-5, 4) == "0000"

    def test_date_yyyymmdd_to_mmddyyyy(self):
        assert builder.format_date_yyyymmdd_to_mmddyyyy("20260331") == "03312026"

    def test_date_accepts_date_object(self):
        assert builder.format_date_yyyymmdd_to_mmddyyyy(date(2026, 3, 31)) == "03312026"

    def test_date_blank_becomes_spaces(self):
        assert builder.format_date_yyyymmdd_to_mmddyyyy("") == " " * 8
        assert builder.format_date_yyyymmdd_to_mmddyyyy(None) == " " * 8
        assert builder.format_date_yyyymmdd_to_mmddyyyy("00000000") == " " * 8

    def test_ssn_strips_dashes_pads_to_9(self):
        assert builder.format_ssn("123-45-6789") == "123456789"
        assert builder.format_ssn("1") == "000000001"
        assert builder.format_ssn("") == "000000000"
        assert builder.format_ssn(None) == "000000000"

    def test_phone_strips_nondigits_pads_to_10(self):
        assert builder.format_phone("(407) 555-1234") == "4075551234"
        assert builder.format_phone("") == "          "


# ─── Header / trailer ────────────────────────────────────────────────────────
class TestHeaderAndTrailer:
    def test_header_is_exactly_426_bytes(self):
        h = builder.build_header("20260331", "20260414")
        assert len(h) == 426

    def test_header_layout(self):
        h = builder.build_header("20260331", "20260414")
        assert h.startswith("0426HEADER")
        # Experian identifier lives at positions 33-37 (0-indexed 32:37).
        assert h[32:37] == "DBTNU"
        # Reporter name starts at position 80.
        assert h[79:79 + len(schema.REPORTER_NAME)].startswith("KINGDOM AUTO FINANCE")

    def test_trailer_is_exactly_426_bytes(self):
        t = builder.build_trailer(188, 1_250_000, 42_500)
        assert len(t) == 426

    def test_trailer_totals_encoded_correctly(self):
        t = builder.build_trailer(188, 1_250_000, 42_500, status_11_count=150)
        assert t.startswith("0426TRAILE")
        # Bytes 10-19 = record count, 19-28 = status 11, 28-37 = balance,
        # 37-46 = past due (0-indexed).
        assert t[10:19] == "000000188"
        assert t[19:28] == "000000150"
        assert t[28:37] == "001250000"
        assert t[37:46] == "000042500"


# ─── Base segment ────────────────────────────────────────────────────────────
def _sample_record():
    """Return a clean, fully-valid sample record dict keyed by Metro 2 names."""
    return {
        "ConsumerAccountNumber": "KAF-0001",
        "PortfolioType": "I",
        "AccountType": "00",
        "DateOpened": "20240115",
        "CreditLimit": "0",
        "HighestCreditOrOrigLoanAmt": "15000",
        "TermsDuration": "060",
        "TermsFrequency": "M",
        "ScheduledPaymentAmt": "375",
        "ActualPaymentAmt": "375",
        "AccountStatus": "11",
        "CurrentBalance": "12500",
        "AmountPastDue": "0",
        "OriginalChargeoffAmt": "0",
        "DateOfAccountInfo": "20260331",
        "DateLastPayment": "20260310",
        "InterestType": "F",
        "Surname": "GARCIA",
        "FirstName": "MARIA",
        "MiddleName": "",
        "SSN": "123456789",
        "DateOfBirth": "19850612",
        "PhoneNumber": "4075551234",
        "ECOACode": "1",
        "CountryCode": "US",
        "Address1": "123 MAIN ST",
        "Address2": "",
        "City": "ORLANDO",
        "State": "FL",
        "PostalCode": "328010000",
        "AddressIndicator": "C",
    }


class TestBaseSegment:
    def test_base_segment_is_exactly_426_bytes(self):
        seg = builder.build_base_segment(_sample_record(), "20260331")
        assert len(seg) == 426

    def test_base_segment_begins_with_record_descriptor(self):
        seg = builder.build_base_segment(_sample_record(), "20260331")
        assert seg.startswith("0426")

    def test_base_segment_puts_fields_at_correct_byte_positions(self):
        seg = builder.build_base_segment(_sample_record(), "20260331")

        # ConsumerAccountNumber starts at position 43 (index 42), 30 bytes.
        acct_field = schema.FIELDS_BY_NAME["ConsumerAccountNumber"]
        start, length = acct_field.position - 1, acct_field.length
        assert seg[start:start + length] == "KAF-0001".ljust(length)

        # AccountStatus at position 124.
        status_field = schema.FIELDS_BY_NAME["AccountStatus"]
        s = status_field.position - 1
        assert seg[s:s + status_field.length] == "11"

        # State at position 414, 2 bytes.
        state_field = schema.FIELDS_BY_NAME["State"]
        s = state_field.position - 1
        assert seg[s:s + 2] == "FL"

    def test_base_segment_date_of_account_info_defaults_to_as_of(self):
        rec = _sample_record()
        rec.pop("DateOfAccountInfo")
        seg = builder.build_base_segment(rec, "20260331")
        doa_field = schema.FIELDS_BY_NAME["DateOfAccountInfo"]
        s = doa_field.position - 1
        # YYYYMMDD in DB stored, MMDDYYYY on the wire.
        assert seg[s:s + 8] == "03312026"

    def test_base_segment_accepts_db_column_names(self):
        rec = {
            "consumer_account_number": "DB-0001",
            "account_status": "11",
            "current_balance": 5000,
            "amount_past_due": 0,
            "highest_credit_or_orig_loan": 10000,
            "surname": "DOE",
            "first_name": "JANE",
            "ssn": "111223333",
            "date_opened": "20230101",
            "terms_duration": "060",
            "terms_frequency": "M",
            "address_1": "1 WAY",
            "city": "ORLANDO",
            "state": "FL",
            "postal_code": "32801",
        }
        seg = builder.build_base_segment(rec, "20260331")
        assert len(seg) == 426

    def test_base_segment_rejects_when_length_would_be_wrong(self, monkeypatch):
        """Defensive: if someone mutates FIELDS incorrectly, the build fails."""
        # Patch a field to have an impossible length and ensure we raise.
        with pytest.raises(ValueError):
            # call into the internal check via build_base_segment w/ a field
            # length that would push total over 426. We simulate by calling
            # build_trailer with bad count text - it raises on length mismatch.
            original = builder.RECORD_LENGTH
            monkeypatch.setattr(builder, "RECORD_LENGTH", original + 1)
            builder.build_base_segment(_sample_record(), "20260331")


# ─── Full file assembly ──────────────────────────────────────────────────────
class TestBuildFile:
    def test_build_file_produces_header_body_trailer(self):
        records = [_sample_record() for _ in range(3)]
        out, meta = builder.build_file(records, "20260331")

        assert isinstance(out, bytes)
        # One header + 3 base + 1 trailer = 5 lines.
        lines = out.decode("ascii").strip().split("\n")
        assert len(lines) == 5
        assert lines[0].startswith("0426HEADER")
        assert lines[-1].startswith("0426TRAILE")
        for ln in lines:
            assert len(ln) == 426

        assert meta["record_count"] == 3
        assert meta["status_11_count"] == 3
        assert meta["total_current_balance"] == 12500 * 3

    def test_build_file_sums_trailer_totals(self):
        r1 = _sample_record()
        r1["CurrentBalance"] = "1000"
        r1["AmountPastDue"] = "0"
        r2 = _sample_record()
        r2["ConsumerAccountNumber"] = "KAF-0002"
        r2["CurrentBalance"] = "500"
        r2["AmountPastDue"] = "200"
        r2["AccountStatus"] = "71"   # so past-due > 0 is legal
        out, meta = builder.build_file([r1, r2], "20260331")

        assert meta["total_current_balance"] == 1500
        assert meta["total_past_due"] == 200
        assert meta["status_11_count"] == 1     # only r1 is status 11

    def test_build_file_ascii_only(self):
        out, _ = builder.build_file([_sample_record()], "20260331")
        # .decode strict raises on any non-ASCII bytes.
        text = out.decode("ascii", errors="strict")
        assert text.isascii()
