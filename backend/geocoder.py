"""
Offline India Geocoder
======================
Forward geocoder (place name -> lat/lng) for India.

Strategy:
  1. Lookup in curated India-specific gazetteer (J&K, sensitive places)
  2. Fallback to geonamescache (3,767 Indian cities, fully offline)
  3. Normalised matching:
       - lowercase, strip punctuation/whitespace
       - try the full string first
       - then progressively strip trailing tokens (e.g. "Srinagar, J&K" -> "Srinagar")
       - then try the FIRST token only (e.g. "Bemina locality, Srinagar" -> "Bemina")

No internet calls anywhere. No graceful degradation needed — if it's not in
either dataset, returns None and the map skips that location.

Public API:
    geocode(text: str) -> {"lat", "lng", "display"} | None
    geodesic_km(lat1, lng1, lat2, lng2) -> float
"""
from __future__ import annotations

import logging
import math
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------
from india_places_data import INDIA_PLACES

_INDEX: dict[str, tuple[float, float, str]] = {}
_INITIALISED = False


def _norm(s: str) -> str:
    """Normalise a place string for dictionary lookup."""
    if not s:
        return ""
    s = s.lower().strip()
    # Strip common cruft
    s = re.sub(r"[^a-z0-9\s,&-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _initialise() -> None:
    """Build the merged in-memory index from curated + geonamescache."""
    global _INITIALISED
    if _INITIALISED:
        return

    # 1. Curated (highest priority — overwrites geonames)
    for name, (lat, lng, display) in INDIA_PLACES.items():
        _INDEX[_norm(name)] = (lat, lng, display)

    # 2. geonamescache India cities
    try:
        import geonamescache
        gc = geonamescache.GeonamesCache()
        cities = gc.get_cities()
        added = 0
        for c in cities.values():
            if c.get("countrycode") != "IN":
                continue
            name = c["name"]
            lat = float(c["latitude"])
            lng = float(c["longitude"])
            display = f"{name}, India"
            key = _norm(name)
            # Don't overwrite curated entries
            if key and key not in _INDEX:
                _INDEX[key] = (lat, lng, display)
                added += 1
        logger.info(
            f"Offline geocoder loaded: {len(INDIA_PLACES)} curated + "
            f"{added} geonames = {len(_INDEX)} total India entries"
        )
    except Exception as e:
        logger.warning(
            f"geonamescache unavailable ({e}); using {len(_INDEX)} curated entries only"
        )

    _INITIALISED = True


def _split_candidates(text: str) -> list[str]:
    """Yield progressively trimmed candidate strings to look up."""
    norm = _norm(text)
    if not norm:
        return []
    candidates = [norm]

    # Comma-split: try the most specific (first) part too
    parts = [p.strip() for p in norm.split(",") if p.strip()]
    if len(parts) > 1:
        # progressive: full, first, last
        candidates.append(parts[0])
        candidates.append(parts[-1])
        # middle bits, smallest first
        for p in parts[1:-1]:
            candidates.append(p)

    # Word-level fallback: first 2 words, first word
    tokens = norm.replace(",", " ").split()
    if len(tokens) >= 2:
        candidates.append(" ".join(tokens[:2]))
    if tokens:
        candidates.append(tokens[0])

    # De-dupe preserving order
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


@lru_cache(maxsize=4096)
def geocode(text: str) -> dict | None:
    """Look up a place name and return {lat, lng, display} or None."""
    if not text:
        return None
    _initialise()
    for cand in _split_candidates(text):
        hit = _INDEX.get(cand)
        if hit:
            lat, lng, display = hit
            return {"lat": lat, "lng": lng, "display": display}
    return None


def geodesic_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in km between two lat/lng pairs. No external deps."""
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def stats() -> dict:
    """Diagnostics — used by health-check endpoint."""
    _initialise()
    return {
        "total_indexed_places": len(_INDEX),
        "curated_count": len(INDIA_PLACES),
        "country_scope": "India only",
        "internet_required": False,
    }
