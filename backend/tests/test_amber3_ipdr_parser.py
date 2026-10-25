"""Amber_3 — Regression tests for IPDR PDF parser fix (Hurra Family bug).

Tests the 4 fixes:
  1. pdfplumber Strategy 0 — proper table extraction
  2. Strategy 1 regex now uses re.DOTALL + more section variants
  3. Strategy 4 detects multi-line headers and skips header continuations
  4. Post-parse validation rejects parses with <50% valid IPs
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from parsers import (
    parse_file, parse_pdf, _is_valid_ip, _parse_ipdr_table_row,
    _validate_ipdr_quality, _extract_ipdr_via_pdfplumber,
)

FIXTURE_DIR = Path("/app/tests/ipdr_fixtures")
UMMER_PDF = FIXTURE_DIR / "ipdr_ummer.pdf"
ZAHID_PDF = FIXTURE_DIR / "ipdr_zahid.pdf"


class TestIPValidation:
    def test_valid_ipv4(self):
        assert _is_valid_ip("103.178.216.149")
        assert _is_valid_ip("8.8.8.8")
        assert _is_valid_ip("142.250.199.142")

    def test_invalid_ipv4(self):
        assert not _is_valid_ip("SESSION")
        assert not _is_valid_ip("FACEBOOK")
        assert not _is_valid_ip("VPN/ PROXY")
        assert not _is_valid_ip("10/MAY/2025")
        assert not _is_valid_ip("")
        assert not _is_valid_ip(None)

    def test_valid_ipv6(self):
        assert _is_valid_ip("2600:9000:A61F::1")


class TestPdfplumberExtraction:
    def test_ummer_extracts_5_records(self):
        records = _extract_ipdr_via_pdfplumber(str(UMMER_PDF))
        assert len(records) == 5
        # All should have valid IPs
        for r in records:
            assert _is_valid_ip(r["destination_ip"]), f"Bad IP: {r['destination_ip']}"

    def test_ummer_pakistan_isp_captured(self):
        records = _extract_ipdr_via_pdfplumber(str(UMMER_PDF))
        # First record should be the Pakistan ISP
        assert "PAK" in records[0]["platform"].upper()
        assert records[0]["destination_ip"] == "103.178.216.149"

    def test_ummer_vpn_captured(self):
        records = _extract_ipdr_via_pdfplumber(str(UMMER_PDF))
        vpn_recs = [r for r in records if "VPN" in (r.get("platform") or "").upper()]
        assert len(vpn_recs) == 1
        assert vpn_recs[0]["destination_ip"] == "74.125.24.84"

    def test_ummer_social_apps_captured(self):
        records = _extract_ipdr_via_pdfplumber(str(UMMER_PDF))
        platforms = {(r.get("platform") or "").upper() for r in records}
        assert "FACEBOOK" in platforms
        assert "INSTAGRAM" in platforms
        assert "WHATSAPP" in platforms

    def test_zahid_extracts_4_records(self):
        records = _extract_ipdr_via_pdfplumber(str(ZAHID_PDF))
        assert len(records) == 4
        for r in records:
            assert _is_valid_ip(r["destination_ip"])

    def test_zahid_no_garbage_in_ip_field(self):
        records = _extract_ipdr_via_pdfplumber(str(ZAHID_PDF))
        bad_values = {"SESSION", "FACEBOOK", "INSTAGRAM", "WHATSAPP", "VPN/", "START DATE", "END TIME"}
        for r in records:
            assert r["destination_ip"] not in bad_values, f"Garbage value in IP: {r['destination_ip']}"

    def test_dates_and_times_parsed(self):
        records = _extract_ipdr_via_pdfplumber(str(UMMER_PDF))
        # First record: 11/MAY/2025  15:18:48  11/MAY/2025  15:48:34
        r = records[0]
        assert r["start_date"] == "11/MAY/2025"
        assert r["start_time"] == "15:18:48"
        assert r["end_date"] == "11/MAY/2025"
        assert r["end_time"] == "15:48:34"


class TestParseIPDRRow:
    def test_row_with_pakistan_isp(self):
        row = [
            "7889733776:-\nUmmer Ahmad Hurrah", "", "103.178.216.149", "", "",
            "A.A NETWORKS PVT LTD (PAK)", "", "WANGIPORA SUMBAL", "",
            "11/MAY/2025", "", "", "15:18:48", "", "",
            "11/MAY/2025", "", "", "15:48:34", "",
        ]
        rec = _parse_ipdr_table_row(row)
        assert rec is not None
        assert rec["destination_ip"] == "103.178.216.149"
        assert "PAK" in rec["platform"]
        assert rec["start_date"] == "11/MAY/2025"

    def test_row_without_ip_returns_none(self):
        # Header continuation row
        row = [None, None, None, None, None, None, None, None, None,
               "START DATE", None, None, "START TIME", None, None,
               "END DATE", None, None, "END TIME", None]
        rec = _parse_ipdr_table_row(row)
        assert rec is None

    def test_empty_row_returns_none(self):
        assert _parse_ipdr_table_row([]) is None
        assert _parse_ipdr_table_row(["", "", ""]) is None
        assert _parse_ipdr_table_row([None, None]) is None


class TestQualityValidation:
    def test_high_quality_kept(self):
        records = [
            {"destination_ip": "1.1.1.1"},
            {"destination_ip": "2.2.2.2"},
            {"destination_ip": "3.3.3.3"},
            {"destination_ip": "GARBAGE"},
        ]
        kept, dropped, ratio = _validate_ipdr_quality(records)
        assert len(kept) == 3
        assert dropped == 1
        assert ratio == 0.75

    def test_low_quality_rejected(self):
        # Only 1 valid out of 10 = 10%, below the 50% threshold
        records = [{"destination_ip": "1.1.1.1"}] + [
            {"destination_ip": "SESSION"} for _ in range(9)
        ]
        kept, dropped, ratio = _validate_ipdr_quality(records)
        assert len(kept) == 0
        assert dropped == 10
        assert ratio == 0.1

    def test_empty_records(self):
        kept, dropped, ratio = _validate_ipdr_quality([])
        assert kept == []
        assert dropped == 0
        assert ratio == 0.0


class TestParseFileEndToEnd:
    """End-to-end parse_file() — what the upload endpoint actually calls."""

    def test_ummer_e2e(self):
        records = parse_file(str(UMMER_PDF), ".pdf", "ipdr")
        assert len(records) == 5
        valid_ips = sum(1 for r in records if _is_valid_ip(r.get("destination_ip")))
        assert valid_ips == 5, "100% of records should have valid IPs"

    def test_zahid_e2e(self):
        records = parse_file(str(ZAHID_PDF), ".pdf", "ipdr")
        assert len(records) == 4
        valid_ips = sum(1 for r in records if _is_valid_ip(r.get("destination_ip")))
        assert valid_ips == 4

    def test_ummer_intelligence_preserved(self):
        """The Pakistan ISP signal must reach the parsed output for rule engine to flag."""
        records = parse_file(str(UMMER_PDF), ".pdf", "ipdr")
        pak_records = [r for r in records if "PAK" in (r.get("platform") or "").upper()]
        assert len(pak_records) >= 1


class TestRegressionAgainstHurraFamily:
    """Regression: the EXACT garbage values from the bug report must NEVER appear in destination_ip."""

    BAD_VALUES = {"SESSION", "FACEBOOK", "INSTAGRAM", "WHATSAPP", "VPN/", "VPN/ PROXY",
                  "START DATE", "START TIME", "END DATE", "END TIME", "Ullah Dar",
                  "10/MAY/2025", "11/MAY/2025"}

    def test_ummer_no_bad_values_in_ip(self):
        records = parse_file(str(UMMER_PDF), ".pdf", "ipdr")
        for r in records:
            assert r.get("destination_ip") not in self.BAD_VALUES, \
                f"Found regression: '{r.get('destination_ip')}' in destination_ip field"

    def test_zahid_no_bad_values_in_ip(self):
        records = parse_file(str(ZAHID_PDF), ".pdf", "ipdr")
        for r in records:
            assert r.get("destination_ip") not in self.BAD_VALUES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
