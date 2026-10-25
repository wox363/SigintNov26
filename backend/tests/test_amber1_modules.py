"""Amber_1 — Backend tests for new SIGINT modules: SIM/IMSI, Cell Co-Location, Bulk Transfer.

Covers:
- POST /api/cases/{id}/analyze (job kick-off, success status code)
- GET  /api/cases/{id}/analysis (3 new top-level keys + content sanity)
- GET  /api/cases/{id}/report/{docx,pdf} (status, magic bytes, section headings)
- Empty/missing data graceful handling using legacy case
"""
import io
import os
import time
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://connection-scout-4.preview.emergentagent.com").rstrip("/")
HAPPY_CASE = "77aa1a27-6e0e-4ba4-b84c-ebbfb3bbe669"
EMPTY_CASE = "7c958508-619b-42ce-bfd0-fc828415309b"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _run_analysis(session, case_id, wait=6):
    r = session.post(f"{BASE_URL}/api/cases/{case_id}/analyze", timeout=90)
    assert r.status_code == 200, f"analyze POST failed: {r.status_code} {r.text[:200]}"
    time.sleep(wait)
    g = session.get(f"{BASE_URL}/api/cases/{case_id}/analysis", timeout=60)
    assert g.status_code == 200, f"analysis GET failed: {g.status_code}"
    return g.json()


@pytest.fixture(scope="module")
def happy_analysis(session):
    return _run_analysis(session, HAPPY_CASE)


@pytest.fixture(scope="module")
def empty_analysis(session):
    return _run_analysis(session, EMPTY_CASE)


# ---------------- SIM / IMSI Analysis ----------------
class TestSimAnalysis:
    def test_top_level_key_present(self, happy_analysis):
        assert "sim_analysis" in happy_analysis

    def test_has_imsi_data_true(self, happy_analysis):
        assert happy_analysis["sim_analysis"]["has_imsi_data"] is True

    def test_foreign_sims_pakistan(self, happy_analysis):
        fs = happy_analysis["sim_analysis"]["foreign_sims"]
        assert isinstance(fs, list) and len(fs) >= 1
        pak = next((x for x in fs if x.get("mcc") == "410"), None)
        assert pak is not None, "Pakistan MCC 410 SIM not detected"
        assert pak["country"].lower() == "pakistan"
        assert pak["subject"] == "Safvi"
        assert pak["imsi"] == "410011234567890"

    def test_sim_swaps_three_imsis(self, happy_analysis):
        swaps = happy_analysis["sim_analysis"]["sim_swaps"]
        assert len(swaps) >= 1
        target = next((x for x in swaps if x["imei"] == "356938035643809"), None)
        assert target is not None, "Expected IMEI 356938035643809 not in sim_swaps"
        assert len(target["imsis"]) == 3

    def test_multi_imsi_subject_safvi(self, happy_analysis):
        multi = happy_analysis["sim_analysis"]["multi_imsi_subjects"]
        safvi = next((x for x in multi if x["subject"] == "Safvi"), None)
        assert safvi is not None
        assert safvi["imsi_count"] == 3

    def test_per_subject_roster(self, happy_analysis):
        ps = happy_analysis["sim_analysis"]["per_subject"]
        assert "Safvi" in ps and "Chakan" in ps


# ---------------- Cell Co-Location ----------------
class TestCellColocation:
    def test_top_level_key_present(self, happy_analysis):
        assert "cell_colocation" in happy_analysis

    def test_has_cell_data_true(self, happy_analysis):
        assert happy_analysis["cell_colocation"]["has_cell_data"] is True

    def test_total_events_positive(self, happy_analysis):
        assert happy_analysis["cell_colocation"]["total_events"] > 0

    def test_pair_summary_chakan_safvi(self, happy_analysis):
        pairs = happy_analysis["cell_colocation"]["pair_summary"]
        assert any("Chakan" in p["pair"] and "Safvi" in p["pair"] for p in pairs)

    def test_simultaneous_event(self, happy_analysis):
        evs = happy_analysis["cell_colocation"]["events"]
        assert any(e.get("cell_id") == "404-45-12345-1" and e.get("time_diff_seconds") == 0.0 for e in evs)


# ---------------- Bulk Data Transfer ----------------
class TestBulkTransfer:
    def test_top_level_key_present(self, happy_analysis):
        assert "bulk_transfer_analysis" in happy_analysis

    def test_has_volume_data_true(self, happy_analysis):
        assert happy_analysis["bulk_transfer_analysis"]["has_volume_data"] is True

    def test_safvi_alert_count(self, happy_analysis):
        s = happy_analysis["bulk_transfer_analysis"]["per_subject"]["Safvi"]
        assert s["alert_count"] == 4

    def test_safvi_top_platform_dropbox(self, happy_analysis):
        plats = happy_analysis["bulk_transfer_analysis"]["per_subject"]["Safvi"]["top_platforms"]
        assert plats[0]["platform"] == "Dropbox"
        assert "GB" in plats[0]["total_human"]

    def test_safvi_severity_alert_present(self, happy_analysis):
        sevs = [t.get("severity") for t in happy_analysis["bulk_transfer_analysis"]["per_subject"]["Safvi"]["top_sessions"]]
        assert "ALERT" in sevs

    def test_upload_heavy_sessions_present(self, happy_analysis):
        uh = happy_analysis["bulk_transfer_analysis"]["per_subject"]["Safvi"]["upload_heavy_sessions"]
        assert isinstance(uh, list) and len(uh) > 0


# ---------------- Risk + Summary ----------------
class TestRiskAndSummary:
    def test_safvi_risk_level_high_or_critical(self, happy_analysis):
        rs = happy_analysis["risk_scores"]["Safvi"]
        assert rs["level"] in ("HIGH", "CRITICAL")
        joined = " ".join(rs["factors"]).lower()
        assert "foreign sim" in joined
        assert "bulk transfer alert" in joined
        assert "upload-heavy" in joined

    def test_key_findings_contains_new_signals(self, happy_analysis):
        kf = " ".join(happy_analysis["summary"]["key_findings"]).lower()
        assert "high-volume data transfer" in kf
        assert "cell-tower co-location" in kf
        assert "foreign-mcc sim" in kf
        assert "sim-swap pattern" in kf


# ---------------- Empty/missing data ----------------
class TestEmptyDataGraceful:
    def test_no_crash_on_legacy_case(self, empty_analysis):
        # Endpoint did not 500 (fixture would fail otherwise)
        assert "sim_analysis" in empty_analysis
        assert "cell_colocation" in empty_analysis
        assert "bulk_transfer_analysis" in empty_analysis

    def test_has_imsi_data_false(self, empty_analysis):
        assert empty_analysis["sim_analysis"]["has_imsi_data"] is False

    def test_has_cell_data_false(self, empty_analysis):
        assert empty_analysis["cell_colocation"]["has_cell_data"] is False


# ---------------- Reports (DOCX / PDF) ----------------
class TestReports:
    def test_docx_status_and_magic(self, session):
        r = session.get(f"{BASE_URL}/api/cases/{HAPPY_CASE}/report/docx", timeout=120)
        assert r.status_code == 200
        assert r.content[:4] == b"PK\x03\x04"
        assert "content-length" in {k.lower() for k in r.headers}
        assert int(r.headers["content-length"]) > 0
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert "word/document.xml" in zf.namelist()
        xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        for needle in [
            "SIM / IMSI Analysis", "Cell Tower Co-Location", "Bulk Data Transfer Alerts",
            "PAKISTAN", "SIM-Swap", "UPLOAD-HEAVY", "SIMULTANEOUS",
        ]:
            assert needle in xml, f"DOCX missing {needle!r}"

    def test_pdf_status_and_magic(self, session):
        r = session.get(f"{BASE_URL}/api/cases/{HAPPY_CASE}/report/pdf", timeout=120)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        assert "content-length" in {k.lower() for k in r.headers}
        assert int(r.headers["content-length"]) > 0
        try:
            from pdfminer.high_level import extract_text
            txt = extract_text(io.BytesIO(r.content))
        except Exception:
            txt = r.content.decode("latin-1", errors="ignore")
        for needle in [
            "SIM / IMSI Analysis", "Cell Tower Co-Location", "Bulk Data Transfer Alerts",
            "PAKISTAN", "SIM-Swap", "UPLOAD-HEAVY", "SIMULTANEOUS",
        ]:
            assert needle in txt, f"PDF missing {needle!r}"
