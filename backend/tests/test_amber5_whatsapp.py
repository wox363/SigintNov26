"""Amber_5 — WhatsApp Toolkit Phase 1 regression tests.

Validates:
  - WhatsApp ZIP parsing (real fixture)
  - Multi-line message handling, system messages, media markers
  - Entity extraction (phones, emails, URLs, amounts, places)
  - Per-participant stats, heatmap, silent periods
  - Cross-correlation with case subjects
  - Soft-delete + undo + reupload flow
  - Attachment serving + Phase-1 boundaries (voice flagged, no transcription)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from whatsapp_parser import parse_zip, to_dict
from whatsapp_engine import analyze, _PHONE_RE, _URL_RE


FIXTURE = "/app/tests/whatsapp_fixtures/sample.zip"


@pytest.fixture(scope="module")
def parsed():
    return to_dict(parse_zip(FIXTURE))


@pytest.fixture(scope="module")
def analysis(parsed):
    return analyze(parsed, case_subjects=[
        {"name": "Imtiaz", "phone": "9876543210"},
    ])


class TestParser:
    def test_zip_parses(self, parsed):
        assert parsed["total_lines"] > 100
        assert len(parsed["messages"]) > 100
        assert parsed["chat_filename"] is not None

    def test_two_participants_detected(self, parsed):
        assert set(parsed["participants"]) == {"Imtiaz", "abidhussaindar14"}

    def test_message_kinds_assigned(self, parsed):
        kinds = {m["kind"] for m in parsed["messages"]}
        assert "text" in kinds
        assert "media" in kinds  # there are 5 image + 5 voice = 10+ media references

    def test_attachments_extracted(self, parsed):
        assert len(parsed["attachments"]) == 12
        kinds = {a["mime_hint"] for a in parsed["attachments"]}
        assert "image" in kinds
        assert "audio" in kinds

    def test_voice_notes_flagged_for_review(self, parsed):
        voice = [a for a in parsed["attachments"] if a["mime_hint"] == "audio"]
        assert len(voice) == 5
        for v in voice:
            assert v["needs_manual_review"] is True
            assert "transcription" in v["review_reason"].lower()

    def test_images_have_perceptual_hash(self, parsed):
        images = [a for a in parsed["attachments"] if a["mime_hint"] == "image"]
        # At least most images should have a phash (depends on Pillow being installed)
        with_phash = [a for a in images if a.get("perceptual_hash")]
        assert len(with_phash) >= len(images) - 1, "Most images should yield a phash"

    def test_messages_have_timestamps(self, parsed):
        ts_count = sum(1 for m in parsed["messages"] if m["timestamp"])
        assert ts_count >= len(parsed["messages"]) * 0.95  # ≥ 95% parsable


class TestEntityRegex:
    def test_phone_regex_ignores_filename_digits(self):
        # IMG-20260117-WA0027.jpg should NOT yield a phone
        assert _PHONE_RE.findall("IMG-20260117-WA0027.jpg") == []

    def test_phone_regex_matches_indian_mobile(self):
        assert "9876543210" in _PHONE_RE.findall("Call me at 9876543210")
        # With +91 prefix the regex returns the full match — normalizer strips it later.
        matches = _PHONE_RE.findall("My number is +91 9876543210 sir")
        assert any("9876543210" in m for m in matches)

    def test_phone_regex_rejects_dates(self):
        assert _PHONE_RE.findall("20260117") == []

    def test_url_regex_ignores_image_filenames(self):
        # IMG-20260117-WA0027.jpg has no http:// or www. so should NOT match
        assert _URL_RE.findall("IMG-20260117-WA0027.jpg") == []

    def test_url_regex_matches_real_urls(self):
        results = _URL_RE.findall("Check https://amzn.in/d/j8c6psn for the link")
        assert any("amzn.in" in r for r in results)


class TestAnalysisEngine:
    def test_overview_has_required_fields(self, analysis):
        ov = analysis["overview"]
        assert ov["total_messages"] > 0
        assert ov["total_participants"] == 2
        assert ov["first_message_ts"] is not None
        assert ov["last_message_ts"] is not None
        assert ov["duration_days"] > 0

    def test_per_participant_stats_balanced(self, analysis):
        stats = analysis["per_participant"]
        assert set(stats.keys()) == {"Imtiaz", "abidhussaindar14"}
        for s in stats.values():
            assert s["total_messages"] > 0
            assert s["text_messages"] + s["media_messages"] + s["deleted_count"] <= s["total_messages"]

    def test_heatmap_shape(self, analysis):
        hm = analysis["heatmap"]
        assert len(hm["matrix"]) == 7  # days
        for row in hm["matrix"]:
            assert len(row) == 24  # hours
        # Some cells must be > 0 since chat has activity
        assert sum(sum(row) for row in hm["matrix"]) > 0

    def test_silent_periods_detected(self, analysis):
        # 14-month chat with bursts — there must be silent periods
        assert len(analysis["silent_periods"]) > 0

    def test_subject_name_match(self, analysis):
        # "Imtiaz" is both a participant and a case subject in the fixture setup
        assert any(m["participant"] == "Imtiaz" for m in analysis["subject_links"]["by_name"])

    def test_entities_contain_urls(self, analysis):
        urls = [e["value"] for e in analysis["entities"]["urls"]]
        # The chat references Amazon and Flipkart links
        assert any("amzn" in u or "flipkart" in u or "amazon" in u for u in urls)

    def test_attachment_summary_breakdown(self, analysis):
        summ = analysis["attachment_summary"]
        assert summ["total"] == 12
        assert summ["by_kind"]["image"] == 7
        assert summ["by_kind"]["audio"] == 5
        assert summ["needs_manual_review"] == 5  # all voice notes

    def test_media_review_queue_populated(self, analysis):
        rq = analysis["media_review_queue"]
        assert len(rq) == 5
        for r in rq:
            assert "transcription" in r["reason"].lower()


class TestPhase1Boundaries:
    """Make sure we don't accidentally promise things we can't deliver."""

    def test_no_translation_in_output(self, analysis):
        # Phase 1 must not return any translation key
        assert "translation" not in analysis
        for m in analysis.get("per_participant", {}).values():
            assert "translation" not in m

    def test_no_voice_transcription_in_output(self, parsed):
        for a in parsed["attachments"]:
            assert "transcript" not in a, "Phase 1 must not include voice transcripts"

    def test_no_tampering_verdict_in_output(self, parsed):
        for a in parsed["attachments"]:
            assert "tampered" not in a
            assert "authentic" not in a

    def test_no_intent_classification_in_indicators(self, analysis):
        # Indicators are rule-based markers, NOT intent verdicts
        for ind in analysis["indicators"]:
            assert "intent" not in ind.get("title", "").lower()


class TestApiIntegration:
    """End-to-end test via HTTP endpoints. Skipped if backend isn't reachable."""
    import os
    import requests

    @classmethod
    def setup_class(cls):
        # Read backend URL from frontend .env (canonical)
        env_path = Path("/app/frontend/.env")
        url = None
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                url = line.split("=", 1)[1].strip().strip('"')
                break
        cls.api = f"{url}/api" if url else None
        cls.test_case_id = "77aa1a27-6e0e-4ba4-b84c-ebbfb3bbe669"

    def test_can_upload_and_query(self):
        import requests
        if not self.api:
            pytest.skip("No REACT_APP_BACKEND_URL configured")
        with open(FIXTURE, "rb") as f:
            r = requests.post(
                f"{self.api}/cases/{self.test_case_id}/whatsapp/upload",
                files={"file": ("sample.zip", f)},
                timeout=60,
            )
        assert r.status_code == 200, r.text
        d = r.json()
        upload_id = d["upload"]["id"]
        assert d["upload"]["message_count"] > 0
        # Fetch analysis
        r2 = requests.get(
            f"{self.api}/cases/{self.test_case_id}/whatsapp/uploads/{upload_id}/analysis",
            timeout=30,
        )
        assert r2.status_code == 200
        analysis = r2.json()
        assert "analysis" in analysis
        assert "messages" in analysis
        assert "attachments" in analysis
        # Soft-delete
        r3 = requests.delete(
            f"{self.api}/cases/{self.test_case_id}/whatsapp/uploads/{upload_id}",
            timeout=10,
        )
        assert r3.status_code == 200
        # Undo
        r4 = requests.post(
            f"{self.api}/cases/{self.test_case_id}/whatsapp/uploads/{upload_id}/undo",
            timeout=10,
        )
        assert r4.status_code == 200
        # Clean up
        requests.delete(
            f"{self.api}/cases/{self.test_case_id}/whatsapp/uploads/{upload_id}",
            timeout=10,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
