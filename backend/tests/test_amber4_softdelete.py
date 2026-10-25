"""
Amber_4 — Soft-delete + Undo + Reupload + Re-analysis Banner

Covers backend endpoints:
- DELETE /api/cases/{case_id}/uploads/{upload_id}            soft-delete (3-min undo)
- POST   /api/cases/{case_id}/uploads/{upload_id}/undo       restore soft-deleted
- POST   /api/cases/{case_id}/uploads/{upload_id}/reupload   replace (old kept for undo)
- POST   /api/cases/{case_id}/upload                         new upload sets needs_reanalysis
- POST   /api/cases/{case_id}/analyze                        clears needs_reanalysis on success
- Background _undo_window_purger task (verified via past timestamp)
"""
import os
import time
import pytest
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SAMPLE_CSV = "/app/tests/sample_cdr_safvi_v2.csv"
SAMPLE_CSV_ALT = "/app/tests/sample_cdr_chakan_v2.csv"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


# ------------------------- Fixtures -------------------------

@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    return s


@pytest.fixture
def fresh_case(api):
    """Create a fresh case + 1 upload to keep tests isolated.
    Yields (case_id, upload_id). Deletes case at teardown."""
    r = api.post(f"{API}/cases", json={"name": "TEST_Amber4", "description": "amber4 test"})
    assert r.status_code == 200, r.text
    case_id = r.json()["id"]

    api.post(f"{API}/cases/{case_id}/subjects", json={"name": "Safvi", "phone": "9541476474"})

    with open(SAMPLE_CSV, "rb") as f:
        up = api.post(
            f"{API}/cases/{case_id}/upload",
            files={"file": ("safvi.csv", f, "text/csv")},
            data={"subject_name": "Safvi", "data_type": "cdr"},
        )
    assert up.status_code == 200, up.text
    upload_id = up.json()["upload"]["id"]

    yield case_id, upload_id

    api.delete(f"{API}/cases/{case_id}")


# ------------------------- Soft delete tests -------------------------

class TestSoftDelete:
    def test_soft_delete_keeps_upload_visible_with_flags(self, api, fresh_case):
        case_id, upload_id = fresh_case
        r = api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["upload_id"] == upload_id
        assert body["undo_window_seconds"] == 180
        assert "deletion_expires_at" in body

        # Upload should still appear in list with is_deleted=True
        lst = api.get(f"{API}/cases/{case_id}/uploads").json()
        target = next((u for u in lst if u["id"] == upload_id), None)
        assert target is not None, "soft-deleted upload should still be listed"
        assert target.get("is_deleted") is True
        assert target.get("deletion_reason") == "user_delete"
        assert target.get("deletion_expires_at")

    def test_soft_delete_sets_needs_reanalysis(self, api, fresh_case):
        case_id, upload_id = fresh_case
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        case = api.get(f"{API}/cases/{case_id}").json()
        assert case.get("needs_reanalysis") is True
        assert case.get("last_change_reason") == "upload deleted"

    def test_soft_delete_recomputes_counts(self, api, fresh_case):
        case_id, upload_id = fresh_case
        before = api.get(f"{API}/cases/{case_id}").json()
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        after = api.get(f"{API}/cases/{case_id}").json()
        assert after["upload_count"] == before["upload_count"] - 1
        assert after["record_count"] < before["record_count"]

    def test_double_soft_delete_returns_400(self, api, fresh_case):
        case_id, upload_id = fresh_case
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        r = api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        assert r.status_code == 400

    def test_soft_delete_nonexistent_returns_404(self, api, fresh_case):
        case_id, _ = fresh_case
        r = api.delete(f"{API}/cases/{case_id}/uploads/does-not-exist")
        assert r.status_code == 404


# ------------------------- Undo tests -------------------------

class TestUndo:
    def test_undo_restores_upload_and_records(self, api, fresh_case):
        case_id, upload_id = fresh_case
        before = api.get(f"{API}/cases/{case_id}").json()
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        r = api.post(f"{API}/cases/{case_id}/uploads/{upload_id}/undo")
        assert r.status_code == 200, r.text

        lst = api.get(f"{API}/cases/{case_id}/uploads").json()
        target = next(u for u in lst if u["id"] == upload_id)
        assert target.get("is_deleted") in (False, None)
        assert "deletion_expires_at" not in target
        assert "deletion_reason" not in target

        after = api.get(f"{API}/cases/{case_id}").json()
        assert after["upload_count"] == before["upload_count"]
        assert after["record_count"] == before["record_count"]

    def test_undo_not_deleted_returns_400(self, api, fresh_case):
        case_id, upload_id = fresh_case
        r = api.post(f"{API}/cases/{case_id}/uploads/{upload_id}/undo")
        assert r.status_code == 400

    def test_undo_nonexistent_returns_404(self, api, fresh_case):
        case_id, _ = fresh_case
        r = api.post(f"{API}/cases/{case_id}/uploads/no-such-id/undo")
        assert r.status_code == 404


# ------------------------- Reupload tests -------------------------

class TestReupload:
    def test_reupload_creates_new_id_and_soft_deletes_old(self, api, fresh_case):
        case_id, upload_id = fresh_case
        with open(SAMPLE_CSV_ALT, "rb") as f:
            r = api.post(
                f"{API}/cases/{case_id}/uploads/{upload_id}/reupload",
                files={"file": ("replacement.csv", f, "text/csv")},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        new_id = body["new_upload"]["id"]
        assert new_id != upload_id
        assert body["replaced_upload_id"] == upload_id
        assert body["undo_window_seconds"] == 180
        assert "deletion_expires_at" in body

        lst = api.get(f"{API}/cases/{case_id}/uploads").json()
        by_id = {u["id"]: u for u in lst}
        # New upload is live
        assert by_id[new_id].get("is_deleted") in (False, None)
        assert by_id[new_id].get("replaces") == upload_id
        # Old upload is soft-deleted as replaced
        old = by_id[upload_id]
        assert old.get("is_deleted") is True
        assert old.get("deletion_reason") == "replaced"
        assert old.get("replaced_by") == new_id

        # And needs_reanalysis was set
        case = api.get(f"{API}/cases/{case_id}").json()
        assert case.get("needs_reanalysis") is True

    def test_undo_after_reupload_restores_old_and_purges_new(self, api, fresh_case):
        case_id, upload_id = fresh_case
        with open(SAMPLE_CSV_ALT, "rb") as f:
            r = api.post(
                f"{API}/cases/{case_id}/uploads/{upload_id}/reupload",
                files={"file": ("replacement.csv", f, "text/csv")},
            )
        new_id = r.json()["new_upload"]["id"]

        undo = api.post(f"{API}/cases/{case_id}/uploads/{upload_id}/undo")
        assert undo.status_code == 200, undo.text

        lst = api.get(f"{API}/cases/{case_id}/uploads").json()
        ids = {u["id"] for u in lst}
        # Old should be restored, new replacement should be GONE
        assert upload_id in ids
        assert new_id not in ids, "replacement should be purged permanently after undo"

        # And old upload should not be soft-deleted any more
        old = next(u for u in lst if u["id"] == upload_id)
        assert old.get("is_deleted") in (False, None)
        assert "replaced_by" not in old

    def test_reupload_of_already_deleted_returns_400(self, api, fresh_case):
        case_id, upload_id = fresh_case
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")
        with open(SAMPLE_CSV_ALT, "rb") as f:
            r = api.post(
                f"{API}/cases/{case_id}/uploads/{upload_id}/reupload",
                files={"file": ("replacement.csv", f, "text/csv")},
            )
        assert r.status_code == 400


# ------------------------- New upload triggers banner -------------------------

class TestNewUploadTriggersReanalysis:
    def test_new_upload_sets_needs_reanalysis(self, api, fresh_case):
        case_id, _ = fresh_case
        # Add another subject + upload
        api.post(f"{API}/cases/{case_id}/subjects", json={"name": "Chakan", "phone": "9906123456"})
        with open(SAMPLE_CSV_ALT, "rb") as f:
            r = api.post(
                f"{API}/cases/{case_id}/upload",
                files={"file": ("chakan.csv", f, "text/csv")},
                data={"subject_name": "Chakan", "data_type": "cdr"},
            )
        assert r.status_code == 200
        case = api.get(f"{API}/cases/{case_id}").json()
        assert case.get("needs_reanalysis") is True
        assert case.get("last_change_reason") == "new upload"


# ------------------------- Analysis filtering + flag clearing -------------------------

class TestAnalysisExcludesDeleted:
    def test_analysis_excludes_soft_deleted_and_clears_flag(self, api, fresh_case):
        case_id, upload_id = fresh_case
        # Add a 2nd upload so case still has data after we delete the first
        api.post(f"{API}/cases/{case_id}/subjects", json={"name": "Chakan", "phone": "9906123456"})
        with open(SAMPLE_CSV_ALT, "rb") as f:
            api.post(
                f"{API}/cases/{case_id}/upload",
                files={"file": ("chakan.csv", f, "text/csv")},
                data={"subject_name": "Chakan", "data_type": "cdr"},
            )
        # Soft-delete first upload
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")

        r = api.post(f"{API}/cases/{case_id}/analyze")
        assert r.status_code == 200, r.text

        # Poll status
        for _ in range(30):
            st = api.get(f"{API}/cases/{case_id}/analyze/status").json()
            if st.get("status") in ("complete", "failed"):
                break
            time.sleep(1)
        assert st.get("status") == "complete", st

        case = api.get(f"{API}/cases/{case_id}").json()
        assert "needs_reanalysis" not in case or case.get("needs_reanalysis") is False, \
            f"flag should be cleared after analysis: {case}"


# ------------------------- Background purger -------------------------

class TestBackgroundPurger:
    def test_expired_upload_is_purged(self, api, fresh_case):
        """Manually rewrite deletion_expires_at to the past, then wait for the
        background task (60s tick) to permanently delete it."""
        case_id, upload_id = fresh_case
        api.delete(f"{API}/cases/{case_id}/uploads/{upload_id}")

        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        res = db.uploads.update_one(
            {"id": upload_id},
            {"$set": {"deletion_expires_at": past}},
        )
        assert res.modified_count == 1
        client.close()

        # Background tick is 60s; wait up to ~80s.
        gone = False
        for _ in range(16):
            time.sleep(5)
            lst = api.get(f"{API}/cases/{case_id}/uploads").json()
            if not any(u["id"] == upload_id for u in lst):
                gone = True
                break
        assert gone, "expired upload should be purged by background task"
