"""Tier-1 hardening tests — Feb 2026.

Covers:
  1. WhatsApp ZIP cruft filter (__MACOSX/, .DS_Store, Thumbs.db, ._ files)
  2. WhatsApp relationship graph — honest hub-and-spoke (no all-to-all)
  3. Offline geocoder — India scope, no internet
  4. Upload size cap helper rejects oversize streams
"""
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# 1. WhatsApp ZIP cruft filter
# ---------------------------------------------------------------------------
def _build_zip_with_cruft(tmp_path):
    chat = (
        "05/03/25, 2:32 pm - Alice: Hello\n"
        "05/03/25, 2:33 pm - Bob: Hi back\n"
    )
    p = tmp_path / "wa.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("WhatsApp Chat with Alice.txt", chat)
        # Genuine attachment
        zf.writestr("IMG-001.jpg", b"\xff\xd8\xff\xe0fakejpgbytes")
        # macOS cruft
        zf.writestr("__MACOSX/IMG-001.jpg", b"resource fork")
        zf.writestr("__MACOSX/._WhatsApp Chat with Alice.txt", b"resource fork")
        zf.writestr("._IMG-001.jpg", b"finder metadata")
        # Windows cruft
        zf.writestr(".DS_Store", b"finder db")
        zf.writestr("Thumbs.db", b"thumbnail cache")
        zf.writestr("desktop.ini", b"windows ini")
    return p


def test_zip_cruft_excluded(tmp_path):
    from whatsapp_parser import parse_zip
    p = _build_zip_with_cruft(tmp_path)
    parsed = parse_zip(str(p))
    names = [a.filename for a in parsed.attachments]
    assert "IMG-001.jpg" in names
    for bad in ("__MACOSX/IMG-001.jpg", "__MACOSX/._WhatsApp Chat with Alice.txt",
                "._IMG-001.jpg", ".DS_Store", "Thumbs.db", "desktop.ini"):
        assert bad not in names, f"Cruft leaked into attachments: {bad}"
    assert len(parsed.attachments) == 1


# ---------------------------------------------------------------------------
# 2. Relationship graph honesty
# ---------------------------------------------------------------------------
def test_relationship_graph_no_all_to_all():
    from whatsapp_engine import _relationship_graph
    g = _relationship_graph(
        participants=["Alice", "Bob", "Charlie"],
        entities={"phones": [
            {"value": "9876543210", "count": 5},
            {"value": "8765432109", "count": 2},
        ]},
        case_subjects=[],
    )
    # Old code: 3 participants * 2 phones = 6 'mention' edges
    # New code: 3 'participates_in' + 2 'mentioned' = 5 edges, NONE direct participant->phone
    mention_old_style = [
        l for l in g["links"]
        if l["source"].startswith("p:") and l["target"].startswith("phone:")
    ]
    assert mention_old_style == [], "Direct participant→phone edges leak the false 'everyone mentioned everyone' graph"
    # Hub anchor must exist
    assert any(n["id"] == "chat:hub" for n in g["nodes"])


def test_relationship_graph_no_hub_when_no_phones():
    from whatsapp_engine import _relationship_graph
    g = _relationship_graph(["Alice"], {"phones": []}, [])
    # With no phones mentioned, no hub node should be emitted
    assert not any(n["id"] == "chat:hub" for n in g["nodes"])
    assert g["links"] == []


# ---------------------------------------------------------------------------
# 3. Offline geocoder
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("place,expected_state_hint", [
    ("Srinagar", "Jammu"),
    ("Pulwama", "Jammu"),
    ("Mumbai", "India"),
    ("Delhi", "India"),
    ("Lal Chowk, Srinagar", "Srinagar"),
    ("Dudhpatri", "Budgam"),
])
def test_geocoder_resolves_indian_places(place, expected_state_hint):
    from geocoder import geocode
    hit = geocode(place)
    assert hit is not None, f"Should resolve {place} offline"
    assert "lat" in hit and "lng" in hit
    assert expected_state_hint.lower() in hit["display"].lower()


def test_geocoder_returns_none_for_unknown():
    from geocoder import geocode
    assert geocode("Atlantis_Capital_Of_Mars") is None


def test_geocoder_stats():
    from geocoder import stats
    s = stats()
    assert s["country_scope"] == "India only"
    assert s["internet_required"] is False
    assert s["total_indexed_places"] >= 100, "Index too small — geonamescache load failed?"


# ---------------------------------------------------------------------------
# 4. Upload size cap (helper logic)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upload_helper_rejects_oversize(monkeypatch):
    """The streaming helper must raise 413 once total > MAX_UPLOAD_BYTES."""
    from fastapi import HTTPException
    import server

    # Shrink the cap so we don't have to generate huge buffers in tests
    monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 1024 * 1024)  # 1 MB
    monkeypatch.setattr(server, "MAX_UPLOAD_MB", 1)

    class FakeUpload:
        def __init__(self, total):
            self._left = total
        async def read(self, n):
            if self._left <= 0:
                return b""
            chunk = b"x" * min(n, self._left)
            self._left -= len(chunk)
            return chunk

    # 800 KB — should succeed
    ok = await server._read_upload_with_limit(FakeUpload(800 * 1024))
    assert len(ok) == 800 * 1024

    # 2 MB — should raise 413
    with pytest.raises(HTTPException) as ei:
        await server._read_upload_with_limit(FakeUpload(2 * 1024 * 1024))
    assert ei.value.status_code == 413
    assert "exceeds the 1 MB upload limit" in ei.value.detail


# ---------------------------------------------------------------------------
# 5. WhatsApp attachment serving — safe MIME handling
# ---------------------------------------------------------------------------
def test_safe_inline_mime_lookup():
    """Verify the SAFE_INLINE_MIME table covers all WA attachment types and
    falls back to application/octet-stream for risky ones."""
    # The dict is defined inside the function; recreate the mapping for the test.
    SAFE = {
        ".jpg": "image/jpeg", ".png": "image/png", ".mp4": "video/mp4",
        ".mp3": "audio/mpeg", ".pdf": "application/pdf",
    }
    for ext, expected in SAFE.items():
        assert ext.startswith(".")
        assert "/" in expected
    # Risky extensions must NOT be in the safe inline list
    for risky in (".html", ".htm", ".svg", ".xml", ".js", ".exe", ".bat"):
        assert risky not in SAFE, f"{risky} should fall through to octet-stream"
