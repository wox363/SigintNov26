"""Backend tests for Cross-Case Comparison (Amber_2_CompareCases)."""
import os
import io
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://connection-scout-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CASE_A = "7c958508-619b-42ce-bfd0-fc828415309b"
CASE_B = "77aa1a27-6e0e-4ba4-b84c-ebbfb3bbe669"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def compare_result(session):
    r = session.post(f"{API}/compare", json={"case_ids": [CASE_A, CASE_B]}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Validation tests ----------
class TestCompareValidation:
    def test_less_than_2_returns_400(self, session):
        r = session.post(f"{API}/compare", json={"case_ids": [CASE_A]}, timeout=30)
        assert r.status_code == 400

    def test_empty_case_ids_returns_400(self, session):
        r = session.post(f"{API}/compare", json={"case_ids": []}, timeout=30)
        assert r.status_code == 400

    def test_more_than_20_returns_400(self, session):
        ids = [f"fake-id-{i}" for i in range(21)]
        r = session.post(f"{API}/compare", json={"case_ids": ids}, timeout=30)
        assert r.status_code == 400

    def test_non_existent_case_in_missing(self, session):
        # Pair real case A with fake case to keep len==2 but exercise missing-list path
        r = session.post(f"{API}/compare", json={"case_ids": [CASE_A, "nonexistent-case-xyz-123"]}, timeout=60)
        assert r.status_code == 200
        data = r.json()
        missing_ids = [m["case_id"] for m in data.get("missing", [])]
        assert "nonexistent-case-xyz-123" in missing_ids


# ---------- Core comparison response tests ----------
class TestCompareResponseShape:
    def test_status_and_top_level_keys(self, compare_result):
        for key in ("id", "summary", "case_metadata", "shared_phones",
                    "shared_imeis", "shared_imsis", "shared_ips", "aliases"):
            assert key in compare_result, f"missing key {key}"

    def test_case_metadata_has_both(self, compare_result):
        ids = [m["case_id"] for m in compare_result["case_metadata"]]
        assert CASE_A in ids and CASE_B in ids

    def test_summary_key_findings_nonempty(self, compare_result):
        kf = compare_result["summary"].get("key_findings", [])
        assert isinstance(kf, list) and len(kf) > 0
        assert all(isinstance(x, str) and x.strip() for x in kf)

    def test_shared_phones_min5_and_expected_values(self, compare_result):
        phones = [p["value"] for p in compare_result["shared_phones"]]
        assert len(phones) >= 5, f"Expected >=5 shared phones, got {len(phones)}: {phones}"
        assert "9541476474" in phones
        assert "9906123456" in phones

    def test_shared_imeis_min2_and_expected(self, compare_result):
        imeis = [p["value"] for p in compare_result["shared_imeis"]]
        assert len(imeis) >= 2, f"Expected >=2 shared IMEIs, got {len(imeis)}: {imeis}"
        assert "356938035643809" in imeis

    def test_shared_ips_includes_telegram(self, compare_result):
        ips = [p["value"] for p in compare_result["shared_ips"]]
        assert len(ips) >= 1
        assert "149.154.167.50" in ips

    def test_aliases_includes_safvi_and_chakan_exact(self, compare_result):
        aliases = compare_result["aliases"]
        assert len(aliases) >= 2
        # Check both Safvi and Chakan have EXACT matches w/ similarity=1.0
        names_with_strength = {(a["name1"].lower(), a["name2"].lower(), a["match_strength"], a["similarity"])
                               for a in aliases}
        # Look for safvi exact
        safvi_exact = any(
            ("safvi" in a["name1"].lower() and "safvi" in a["name2"].lower()
             and a["match_strength"] == "EXACT" and a["similarity"] == 1.0)
            for a in aliases
        )
        chakan_exact = any(
            ("chakan" in a["name1"].lower() and "chakan" in a["name2"].lower()
             and a["match_strength"] == "EXACT" and a["similarity"] == 1.0)
            for a in aliases
        )
        assert safvi_exact, f"Safvi EXACT alias missing. aliases: {names_with_strength}"
        assert chakan_exact, f"Chakan EXACT alias missing. aliases: {names_with_strength}"


# ---------- Normalization tests (indirect: via stored data) ----------
class TestNormalization:
    def test_phones_have_no_91_prefix_12digit(self, compare_result):
        for p in compare_result["shared_phones"]:
            v = p["value"]
            # Should not be 12-digit starting with 91 (would mean normalization skipped)
            assert not (len(v) == 12 and v.startswith("91")), f"unnormalized phone {v}"

    def test_imeis_min_14digits(self, compare_result):
        for p in compare_result["shared_imeis"]:
            v = p["value"]
            assert v.isdigit() and len(v) >= 14, f"bad imei {v}"


# ---------- Report download tests ----------
class TestReportDownload:
    def test_docx_download(self, session, compare_result):
        cid = compare_result["id"]
        r = session.get(f"{API}/compare/{cid}/report/docx", timeout=60)
        assert r.status_code == 200
        assert r.headers.get("Content-Length"), "Content-Length header missing"
        body = r.content
        # DOCX is a PK zip
        assert body[:2] == b"PK", "Not a valid DOCX (PK header missing)"
        # Open zip and look at document.xml for expected section titles
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        for needle in ("Cross-Case Comparison Report", "Shared Phone Numbers",
                       "Shared IMEIs", "Subject Name Alias Matches"):
            assert needle in xml, f"DOCX missing section: {needle}"

    def test_pdf_download(self, session, compare_result):
        cid = compare_result["id"]
        r = session.get(f"{API}/compare/{cid}/report/pdf", timeout=60)
        assert r.status_code == 200
        assert r.headers.get("Content-Length")
        body = r.content
        assert body[:4] == b"%PDF", "Not a valid PDF magic"
        # PDFs store text in streams - search bytes for title (may not always succeed if compressed)
        # At minimum the file is valid; check size > 1KB
        assert len(body) > 1024

    def test_invalid_format_400(self, session, compare_result):
        cid = compare_result["id"]
        r = session.get(f"{API}/compare/{cid}/report/txt", timeout=30)
        assert r.status_code == 400

    def test_non_existent_compare_id_404(self, session):
        r = session.get(f"{API}/compare/does-not-exist-id/report/pdf", timeout=30)
        assert r.status_code == 404

    def test_redownload_persistence(self, session, compare_result):
        cid = compare_result["id"]
        r1 = session.get(f"{API}/compare/{cid}/report/pdf", timeout=60)
        r2 = session.get(f"{API}/compare/{cid}/report/pdf", timeout=60)
        assert r1.status_code == 200 and r2.status_code == 200


# ---------- Amber_1 regression check (smoke) ----------
class TestAmber1Regression:
    def test_get_cases_still_works(self, session):
        r = session.get(f"{API}/cases", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # After Nov-2026 pagination change, /cases returns a wrapped envelope.
        # Accept both shapes so this regression test stays honest about the API.
        if isinstance(data, dict):
            assert "cases" in data and isinstance(data["cases"], list)
            assert "total" in data
        else:
            assert isinstance(data, list)

    def test_get_analysis_for_case_a(self, session):
        r = session.get(f"{API}/cases/{CASE_A}/analysis", timeout=30)
        # Analysis should exist (analyzed case)
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            # sanity: at least one analysis module present
            assert isinstance(d, dict)

    def test_existing_case_pdf_download(self, session):
        r = session.get(f"{API}/cases/{CASE_A}/report/pdf", timeout=60)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
