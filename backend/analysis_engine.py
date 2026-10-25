"""SIGINT Analysis Engine — Per-subject streaming architecture with evidence collection.

Architecture:
  1. process_subject() — processes one subject at a time, returns summary + evidence
  2. cross_correlate() — runs all cross-subject analysis using lightweight summaries
  3. Evidence stored separately in MongoDB for full audit traceability
"""
from collections import defaultdict
from datetime import datetime
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Load platform DB from external config (editable without code changes)
_platform_db_path = Path(__file__).parent / "platform_db.json"
try:
    with open(_platform_db_path) as f:
        PLATFORM_DB = json.load(f)
    logger.info(f"Loaded platform DB: {sum(len(p) for p in PLATFORM_DB.values())} platforms")
except Exception as e:
    logger.error(f"Failed to load platform_db.json: {e}")
    PLATFORM_DB = {}

# Geocoding setup — fully offline, India-only
from geocoder import geocode as _offline_geocode, geodesic_km as _offline_geodesic_km
_geocode_cache = {}  # kept for backwards-compat with any callers reading it

# ===========================================================================
# Volume / IMSI / Cell-ID helpers
# ===========================================================================

# Bulk-transfer thresholds (bytes)
BULK_ALERT_BYTES = 500 * 1024 * 1024     # >500 MB single session
BULK_HIGH_BYTES = 50 * 1024 * 1024       # 50 MB - 500 MB
BULK_MEDIUM_BYTES = 10 * 1024 * 1024     # 10 MB - 50 MB

# IMSI MCC (Mobile Country Code) → country.  India = 404/405/406. Anything else
# in a subject's records is a foreign-SIM red flag (especially neighbouring
# state-actor codes 410 PK, 414 MM, 470 BD, 419 KW, 425 IL).
MCC_COUNTRY = {
    "404": "India", "405": "India", "406": "India",
    "410": "Pakistan", "411": "Bhutan", "412": "Afghanistan", "413": "Sri Lanka",
    "414": "Myanmar", "415": "Lebanon", "416": "Jordan", "417": "Syria",
    "418": "Iraq", "419": "Kuwait", "420": "Saudi Arabia", "421": "Yemen",
    "422": "Oman", "424": "UAE", "425": "Israel", "426": "Bahrain",
    "427": "Qatar", "428": "Mongolia", "429": "Nepal", "470": "Bangladesh",
    "472": "Maldives", "454": "Hong Kong", "460": "China", "440": "Japan",
    "310": "USA", "311": "USA", "234": "UK", "262": "Germany", "208": "France",
}
# Cell-tower co-location time window
CELL_COLOC_WINDOW_SEC = 300


def _to_bytes(val):
    """Convert volume value to bytes. Handles raw int/float, or strings like
    '12 MB', '1.5GB', '500K', or plain bytes."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s:
        return 0
    m = re.match(r"^([\d,.]+)\s*([kKmMgGtT]?)[bB]?$", s)
    if not m:
        try:
            return int(float(s.replace(",", "")))
        except (ValueError, TypeError):
            return 0
    num = float(m.group(1).replace(",", ""))
    suffix = m.group(2).upper()
    multiplier = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}.get(suffix, 1)
    return int(num * multiplier)


def _format_bytes(b):
    if b < 1024:
        return f"{b} B"
    if b < 1024 ** 2:
        return f"{b / 1024:.1f} KB"
    if b < 1024 ** 3:
        return f"{b / (1024 ** 2):.1f} MB"
    return f"{b / (1024 ** 3):.2f} GB"


def _imsi_country(imsi):
    """Return (mcc, country) tuple for an IMSI. Returns ('', 'Unknown') if invalid."""
    if not imsi:
        return ("", "Unknown")
    s = re.sub(r"\D", "", str(imsi))
    if len(s) < 5:
        return ("", "Unknown")
    mcc = s[:3]
    return (mcc, MCC_COUNTRY.get(mcc, "Unknown / Foreign"))


def _normalize_cell_id(cid):
    """Normalize a Cell ID for stable comparison across subjects."""
    if not cid:
        return None
    s = str(cid).strip().upper()
    # Strip common separators so '405-67-12345-6' and '4056712345-6' compare equal
    s = re.sub(r"[\s\-_:/]+", "-", s)
    return s if s and s.lower() != "nan" else None



def _geocode(location_str):
    """Offline geocoder. India-only. Returns {lat, lng, display} or None."""
    if not location_str:
        return None
    return _offline_geocode(location_str)


# Platform identification with cache
_platform_cache = {}


def identify_platform(ip=None, url=None):
    cache_key = (ip or "", url or "")
    if cache_key in _platform_cache:
        return _platform_cache[cache_key]
    matches = []
    if not ip and not url:
        _platform_cache[cache_key] = matches
        return matches
    ip_str = str(ip).strip() if ip else ""
    url_str = str(url).strip().lower() if url else ""
    for category, platforms in PLATFORM_DB.items():
        for name, ids in platforms.items():
            matched = False
            if ip_str:
                for prefix in ids.get("ips", []):
                    if ip_str == prefix or ip_str.startswith(prefix):
                        matches.append({"category": category, "platform": name, "matched_on": "ip"})
                        matched = True
                        break
            if not matched and url_str:
                for domain in ids.get("domains", []):
                    if domain in url_str:
                        matches.append({"category": category, "platform": name, "matched_on": "domain"})
                        break
    seen = set()
    deduped = []
    for m in matches:
        if m["platform"] not in seen:
            seen.add(m["platform"])
            deduped.append(m)
    _platform_cache[cache_key] = deduped
    return deduped


def parse_dt(record):
    dt_str = None
    if record.get("datetime"):
        dt_str = record["datetime"]
    elif record.get("start_date") and record.get("start_time"):
        dt_str = f"{record['start_date']} {record['start_time']}"
    elif record.get("date") and record.get("time"):
        dt_str = f"{record['date']} {record['time']}"
    elif record.get("date"):
        dt_str = record["date"]
    elif record.get("start_date"):
        dt_str = record["start_date"]
    elif record.get("start_time"):
        dt_str = record["start_time"]
    if not dt_str:
        return None
    for fmt in [
        "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M",
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y",
        "%Y/%m/%d %H:%M:%S", "%d %b %Y %H:%M:%S", "%d %B %Y %H:%M:%S",
    ]:
        try:
            return datetime.strptime(str(dt_str).strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


# ===========================================================================
# PHASE 1: Per-Subject Processing (streaming, one subject at a time)
# ===========================================================================

def process_subject(subject_name, raw_records):
    """Process a single subject's records. Returns summary + evidence.
    This is called once per subject, then the records are discarded from memory."""
    cdr_records = []
    ipdr_records = []
    for rec in raw_records:
        data = rec.get("data", {})
        rtype = rec.get("record_type", "unknown")
        if rtype == "cdr":
            cdr_records.append(data)
        else:
            ipdr_records.append(data)

    # --- Parse CDR datetimes ---
    for r in cdr_records:
        dt = parse_dt(r)
        r["_dt"] = dt.isoformat() if dt else None

    # --- IPDR: platform identification + evidence collection ---
    platform_hits = defaultdict(list)       # category -> [sample hits] (capped for display)
    platform_counts = defaultdict(lambda: defaultdict(int))  # category -> platform -> count
    # Evidence: full audit trail per platform per category
    evidence = defaultdict(lambda: defaultdict(lambda: {
        "count": 0, "ips": set(), "first_seen": None, "last_seen": None, "samples": []
    }))
    all_platforms = set()

    for r in ipdr_records:
        dt = parse_dt(r)
        r["_dt"] = dt.isoformat() if dt else None
        platforms = identify_platform(ip=r.get("destination_ip"), url=r.get("url"))
        r["_platforms"] = platforms
        for p in platforms:
            cat, pname = p["category"], p["platform"]
            all_platforms.add(pname)
            platform_counts[cat][pname] += 1
            # Full evidence
            ev = evidence[cat][pname]
            ev["count"] += 1
            dest_ip = r.get("destination_ip")
            if dest_ip:
                ev["ips"].add(dest_ip)
            ts = r.get("_dt")
            if ts:
                if not ev["first_seen"] or ts < ev["first_seen"]:
                    ev["first_seen"] = ts
                if not ev["last_seen"] or ts > ev["last_seen"]:
                    ev["last_seen"] = ts
            if len(ev["samples"]) < 200:
                ev["samples"].append({"ip": dest_ip, "url": r.get("url"), "timestamp": ts})
            # Display samples (limited)
            if len(platform_hits[cat]) < 50:
                platform_hits[cat].append({"platform": pname, "ip": dest_ip, "url": r.get("url"), "timestamp": ts})

    # --- Extract contacts from CDR (with day/time detail) ---
    contacts = defaultdict(lambda: {"count": 0, "times": []})
    for r in cdr_records:
        for field in ["called_number", "calling_number"]:
            num = r.get(field)
            if num:
                contacts[num]["count"] += 1
                if len(contacts[num]["times"]) < 20:
                    contacts[num]["times"].append({
                        "date": r.get("date", ""), "time": r.get("time", ""),
                        "type": r.get("type", ""), "duration": r.get("duration", ""),
                    })

    # --- Extract IMEIs ---
    imeis = {}
    for r in cdr_records + ipdr_records:
        imei = r.get("imei")
        if imei:
            if imei not in imeis:
                imeis[imei] = {"first_seen": r.get("_dt"), "last_seen": r.get("_dt"), "call_count": 0}
            imeis[imei]["call_count"] += 1
            ts = r.get("_dt")
            if ts:
                if not imeis[imei]["first_seen"] or ts < imeis[imei]["first_seen"]:
                    imeis[imei]["first_seen"] = ts
                if not imeis[imei]["last_seen"] or ts > imeis[imei]["last_seen"]:
                    imeis[imei]["last_seen"] = ts

    # --- Extract IMSIs (parallel to IMEI) ---
    imsis = {}
    imei_imsi_pairs = set()  # for SIM-swap detection at cross-correlation phase
    for r in cdr_records + ipdr_records:
        imsi = r.get("imsi")
        if imsi:
            imsi_clean = re.sub(r"\D", "", str(imsi))
            if len(imsi_clean) < 14:
                continue
            mcc, country = _imsi_country(imsi_clean)
            if imsi_clean not in imsis:
                imsis[imsi_clean] = {
                    "mcc": mcc, "country": country,
                    "first_seen": r.get("_dt"), "last_seen": r.get("_dt"),
                    "count": 0, "is_foreign": country not in ("India", "Unknown"),
                }
            imsis[imsi_clean]["count"] += 1
            ts = r.get("_dt")
            if ts:
                if not imsis[imsi_clean]["first_seen"] or ts < imsis[imsi_clean]["first_seen"]:
                    imsis[imsi_clean]["first_seen"] = ts
                if not imsis[imsi_clean]["last_seen"] or ts > imsis[imsi_clean]["last_seen"]:
                    imsis[imsi_clean]["last_seen"] = ts
            if r.get("imei"):
                imei_imsi_pairs.add((r.get("imei"), imsi_clean))

    # --- Bulk Data Transfer extraction (IPDR only) ---
    bulk_sessions = []        # list of high-volume sessions with platform attribution
    platform_volume = defaultdict(lambda: {"up": 0, "down": 0, "total": 0, "sessions": 0})
    total_up = 0
    total_down = 0
    for r in ipdr_records:
        up = _to_bytes(r.get("volume_up"))
        down = _to_bytes(r.get("volume_down"))
        total_explicit = _to_bytes(r.get("volume_total"))
        if total_explicit and not (up or down):
            # If only total provided, attribute it to download (typical for browsing)
            down = total_explicit
        total = up + down if (up or down) else total_explicit
        if total <= 0:
            continue
        total_up += up
        total_down += down
        plats = r.get("_platforms", [])
        plat_name = plats[0]["platform"] if plats else "Unknown"
        plat_cat = plats[0]["category"] if plats else "unknown"
        pv = platform_volume[plat_name]
        pv["up"] += up
        pv["down"] += down
        pv["total"] += total
        pv["sessions"] += 1
        if total >= BULK_MEDIUM_BYTES:
            severity = "ALERT" if total >= BULK_ALERT_BYTES else "HIGH" if total >= BULK_HIGH_BYTES else "MEDIUM"
            bulk_sessions.append({
                "timestamp": r.get("_dt"),
                "platform": plat_name,
                "category": plat_cat,
                "volume_up_bytes": up,
                "volume_down_bytes": down,
                "volume_total_bytes": total,
                "destination_ip": r.get("destination_ip"),
                "severity": severity,
                "is_upload_heavy": up > 0 and down > 0 and up >= 3 * down,  # exfiltration signature
            })
    # Sort by total volume desc, cap to top 100 per subject
    bulk_sessions.sort(key=lambda x: x["volume_total_bytes"], reverse=True)
    bulk_sessions = bulk_sessions[:100]
    platform_volume_serializable = {
        p: {**v} for p, v in platform_volume.items() if v["total"] > 0
    }

    # --- Cell-ID sessions (CDR primary, IPDR if available) for co-location ---
    cell_sessions = []
    for r in cdr_records + ipdr_records:
        cid = _normalize_cell_id(r.get("cell_id"))
        if cid and r.get("_dt"):
            cell_sessions.append({
                "cell_id": cid,
                "timestamp": r["_dt"],
                "type": "cdr" if r in cdr_records else "ipdr",
            })
    cell_sessions.sort(key=lambda x: x["timestamp"])
    cell_sessions = cell_sessions[:2000]  # cap for memory safety

    # --- Extract temporal events (limited for cross-correlation) ---
    events = []
    for r in ipdr_records:
        if r.get("_dt"):
            plats = r.get("_platforms", [])
            events.append({
                "timestamp": r["_dt"], "type": "ipdr",
                "platform": plats[0]["platform"] if plats else "Unknown",
                "category": plats[0]["category"] if plats else "unknown",
            })
    for r in cdr_records:
        if r.get("_dt"):
            events.append({"timestamp": r["_dt"], "type": "cdr", "platform": "Voice/SMS", "category": "telecom"})
    events.sort(key=lambda x: x["timestamp"])
    events = events[:500]

    # --- Serialize evidence (convert sets to lists for MongoDB) ---
    evidence_serializable = {}
    for cat, platforms_ev in evidence.items():
        evidence_serializable[cat] = {}
        for pname, ev in platforms_ev.items():
            evidence_serializable[cat][pname] = {
                "count": ev["count"],
                "ips": list(ev["ips"]),
                "first_seen": ev["first_seen"],
                "last_seen": ev["last_seen"],
                "samples": ev["samples"],
            }

    return {
        "subject": subject_name,
        "cdr_count": len(cdr_records),
        "ipdr_count": len(ipdr_records),
        "platform_hits": dict(platform_hits),
        "platform_counts": {cat: dict(counts) for cat, counts in platform_counts.items()},
        "all_platforms": list(all_platforms),
        "contacts": {num: {"count": info["count"], "times": info["times"][:10]} for num, info in contacts.items()},
        "imeis": imeis,
        "imsis": imsis,
        "imei_imsi_pairs": [list(p) for p in imei_imsi_pairs],
        "bulk_sessions": bulk_sessions,
        "platform_volume": platform_volume_serializable,
        "total_volume_up": total_up,
        "total_volume_down": total_down,
        "cell_sessions": cell_sessions,
        "events": events,
        "evidence": evidence_serializable,
    }


# ===========================================================================
# PHASE 2: Cross-Subject Correlation (uses lightweight summaries only)
# ===========================================================================

def _build_processed(summaries):
    """Adapt per-subject summaries to the format expected by analysis functions."""
    processed = {}
    for subject_name, s in summaries.items():
        processed[subject_name] = {
            "cdr": [],  # Raw records not needed
            "ipdr": [],
            "platform_hits": s.get("platform_hits", {}),
            "platform_counts": s.get("platform_counts", {}),
            "all_platforms": set(s.get("all_platforms", [])),
            "contacts": s.get("contacts", {}),
            "imeis": s.get("imeis", {}),
            "imsis": s.get("imsis", {}),
            "imei_imsi_pairs": s.get("imei_imsi_pairs", []),
            "bulk_sessions": s.get("bulk_sessions", []),
            "platform_volume": s.get("platform_volume", {}),
            "total_volume_up": s.get("total_volume_up", 0),
            "total_volume_down": s.get("total_volume_down", 0),
            "cell_sessions": s.get("cell_sessions", []),
            "events": s.get("events", []),
            "cdr_count": s.get("cdr_count", 0),
            "ipdr_count": s.get("ipdr_count", 0),
        }
    return processed


def cross_correlate(case, summaries):
    """Run all cross-subject analysis using per-subject summaries."""
    global _platform_cache
    _platform_cache = {}

    subjects = {s["name"]: s for s in case.get("subjects", [])}
    processed = _build_processed(summaries)
    subject_names = list(processed.keys())

    funding = _funding_correlation(processed)
    comm_prob = _communication_probability(processed)
    temporal = _temporal_overlap(processed)
    file_transfer = _file_transfer(processed)
    secure_msg = _secure_messaging(processed)
    location = _location_correlation(processed, subjects)
    comm_likelihood = _communication_likelihood(processed)
    graph = _relationship_graph(processed)
    behavioral = _behavioral_profiling(processed)
    common_contacts = _common_contacts(processed)
    imei_analysis = _imei_analysis(processed)
    bulk_transfer = _bulk_transfer_analysis(processed)
    cell_coloc = _cell_colocation(processed)
    sim_analysis = _sim_analysis(processed)
    risk_scores = _risk_scores(processed)
    priority_leads = _priority_leads(processed)
    questions = _interrogation_questions(processed)

    # Roll a few of the new findings into the executive summary
    extra_findings = []
    bulk_alerts = sum(s["alert_count"] + s["high_count"] for s in bulk_transfer["per_subject"].values())
    if bulk_alerts:
        extra_findings.append(f"{bulk_alerts} high-volume data transfer sessions flagged")
    if cell_coloc["total_events"]:
        extra_findings.append(f"{cell_coloc['total_events']} cell-tower co-location events detected")
    if sim_analysis["foreign_sims"]:
        extra_findings.append(f"{len(sim_analysis['foreign_sims'])} foreign-MCC SIM(s) detected")
    if sim_analysis["sim_swaps"]:
        extra_findings.append(f"{len(sim_analysis['sim_swaps'])} SIM-swap pattern(s) on shared device(s)")

    summary = {
        "total_subjects": len(subject_names),
        "high_risk_subjects": [s for s, r in risk_scores.items() if r["level"] in ["HIGH", "CRITICAL"]],
        "total_crypto_hits": funding.get("total_crypto_hits", 0),
        "total_temporal_overlaps": temporal.get("total_overlaps", 0),
        "total_common_contacts": common_contacts.get("total_common_contacts", 0),
        "total_bulk_transfers": bulk_alerts,
        "total_cell_colocations": cell_coloc["total_events"],
        "total_foreign_sims": len(sim_analysis["foreign_sims"]),
        "key_findings": [
            f"{len(subject_names)} subjects analyzed",
            f"{len([s for s, r in risk_scores.items() if r['level'] in ['HIGH', 'CRITICAL']])} flagged HIGH/CRITICAL risk",
            f"{funding.get('total_crypto_hits', 0)} cryptocurrency access events",
            f"{temporal.get('total_overlaps', 0)} temporal overlaps detected",
            f"{common_contacts.get('total_common_contacts', 0)} shared contacts found",
        ] + extra_findings,
    }

    return {
        "case_id": case["id"], "case_name": case["name"],
        "subjects": subject_names,
        "subject_details": {k: v for k, v in subjects.items()},
        "summary": summary,
        "funding_correlation": funding,
        "communication_probability": comm_prob,
        "temporal_overlap": temporal,
        "file_transfer": file_transfer,
        "secure_messaging": secure_msg,
        "location_correlation": location,
        "communication_likelihood": comm_likelihood,
        "relationship_graph": graph,
        "behavioral_profiling": behavioral,
        "common_contacts": common_contacts,
        "imei_analysis": imei_analysis,
        "bulk_transfer_analysis": bulk_transfer,
        "cell_colocation": cell_coloc,
        "sim_analysis": sim_analysis,
        "risk_scores": risk_scores,
        "priority_leads": priority_leads,
        "interrogation_questions": questions,
    }


# Legacy wrapper for backward compatibility
def run_analysis(case, records):
    """Legacy single-shot analysis. For background job, use process_subject + cross_correlate."""
    global _platform_cache
    _platform_cache = {}
    subjects = {s["name"]: s for s in case.get("subjects", [])}
    subject_records = defaultdict(list)
    for rec in records:
        subject_records[rec.get("subject_name", "Unknown")].append(rec)
    summaries = {}
    for sname, recs in subject_records.items():
        summaries[sname] = process_subject(sname, recs)
    return cross_correlate(case, summaries)


# ===========================================================================
# Analysis Functions (work with processed summaries)
# ===========================================================================

def _funding_correlation(processed):
    subject_crypto = {}
    for subject, data in processed.items():
        hits = data["platform_hits"].get("crypto", [])
        if hits:
            subject_crypto[subject] = hits[:20]
    correlations = []
    subs = list(subject_crypto.keys())
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            s1, s2 = subs[i], subs[j]
            p1 = set(h["platform"] for h in subject_crypto[s1])
            p2 = set(h["platform"] for h in subject_crypto[s2])
            shared_p = p1 & p2
            ip1 = set(h["ip"] for h in subject_crypto[s1] if h["ip"])
            ip2 = set(h["ip"] for h in subject_crypto[s2] if h["ip"])
            shared_ip = ip1 & ip2
            if shared_p or shared_ip:
                correlations.append({
                    "subjects": [s1, s2], "shared_platforms": list(shared_p),
                    "shared_ips": list(shared_ip),
                    "strength": "HIGH" if shared_ip else "MEDIUM",
                    "inference": f"Both accessed {', '.join(shared_p or shared_ip)}" +
                                 (f" via shared IP(s): {', '.join(shared_ip)}" if shared_ip else ""),
                })
    total = sum(
        sum(data.get("platform_counts", {}).get("crypto", {}).values())
        for data in processed.values()
    )
    return {"subject_activity": subject_crypto, "correlations": correlations, "total_crypto_hits": total}


def _communication_probability(processed):
    subject_platforms = {}
    for subject, data in processed.items():
        plats = set()
        for cat in ["messaging", "social", "email", "anonymous_chat", "live_streaming"]:
            for hit in data["platform_hits"].get(cat, []):
                plats.add(hit["platform"])
        subject_platforms[subject] = sorted(list(plats))
    all_plats = sorted(set(p for ps in subject_platforms.values() for p in ps))
    matrix = {}
    for subject, plats in subject_platforms.items():
        matrix[subject] = {p: p in plats for p in all_plats}
    return {"subject_platforms": subject_platforms, "platform_matrix": matrix, "all_platforms": all_plats}


def _temporal_overlap(processed):
    """Uses pre-extracted events from subject summaries."""
    subject_events = {}
    for subject, data in processed.items():
        subject_events[subject] = data.get("events", [])
    overlaps = []
    subs = list(subject_events.keys())
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            s1, s2 = subs[i], subs[j]
            for e1 in subject_events[s1][:300]:
                for e2 in subject_events[s2][:300]:
                    try:
                        t1 = datetime.fromisoformat(e1["timestamp"])
                        t2 = datetime.fromisoformat(e2["timestamp"])
                        diff = abs((t1 - t2).total_seconds())
                        if diff <= 3600:
                            overlaps.append({
                                "subjects": [s1, s2], "time_diff_seconds": diff,
                                "event1": {"subject": s1, **e1}, "event2": {"subject": s2, **e2},
                            })
                    except Exception:
                        continue
    overlaps.sort(key=lambda x: x["time_diff_seconds"])
    return {
        "overlapping_events": overlaps[:50], "total_overlaps": len(overlaps),
        "subject_event_counts": {s: len(e) for s, e in subject_events.items()},
    }


def _file_transfer(processed):
    subject_ft = {}
    for subject, data in processed.items():
        hits = data["platform_hits"].get("file_transfer", [])
        if hits:
            subject_ft[subject] = hits[:10]
    shared = []
    subs = list(subject_ft.keys())
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            s1, s2 = subs[i], subs[j]
            p1 = set(h["platform"] for h in subject_ft[s1])
            p2 = set(h["platform"] for h in subject_ft[s2])
            common = p1 & p2
            if common:
                shared.append({
                    "subjects": [s1, s2], "shared_platforms": list(common),
                    "inference": f"Both use {', '.join(common)} — potential encrypted P2P file exchange",
                })
    return {"subject_activity": subject_ft, "shared_usage": shared}


def _secure_messaging(processed):
    encrypted_set = {"Signal", "Telegram", "Wickr", "Threema", "Silent Phone", "ICQ New"}
    subject_msg = {}
    encryption_findings = {}
    for subject, data in processed.items():
        hits = data["platform_hits"].get("messaging", []) + data["platform_hits"].get("anonymous_chat", [])
        if hits:
            subject_msg[subject] = hits[:10]
            encrypted = [h for h in hits if h["platform"] in encrypted_set]
            if encrypted:
                counts = data.get("platform_counts", {})
                enc_total = sum(v for k, v in counts.get("messaging", {}).items() if k in encrypted_set)
                enc_total += sum(v for k, v in counts.get("anonymous_chat", {}).items() if k in encrypted_set)
                encryption_findings[subject] = {
                    "platforms": list(set(h["platform"] for h in encrypted)),
                    "session_count": enc_total,
                    "risk_note": "Uses end-to-end encrypted messaging — metadata minimized",
                }
    return {"subject_activity": subject_msg, "encryption_findings": encryption_findings}


def _location_correlation(processed, subjects):
    subject_locations = {}
    for name, details in subjects.items():
        if details.get("location"):
            subject_locations[name] = details["location"]
    geocoded = {}
    for subject, loc in subject_locations.items():
        coords = _geocode(loc)
        if coords:
            geocoded[subject] = {"lat": coords["lat"], "lng": coords["lng"], "display": coords["display"], "location": loc}
    comparisons = []
    subs = list(subject_locations.keys())
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            s1, s2 = subs[i], subs[j]
            dist_note = "Geospatial distance analysis recommended"
            distance_km = None
            if s1 in geocoded and s2 in geocoded:
                try:
                    distance_km = round(_offline_geodesic_km(
                        geocoded[s1]["lat"], geocoded[s1]["lng"],
                        geocoded[s2]["lat"], geocoded[s2]["lng"],
                    ), 1)
                    dist_note = f"Approx {distance_km} km apart"
                except Exception:
                    pass
            comparisons.append({
                "subjects": [s1, s2],
                "locations": {s1: subject_locations[s1], s2: subject_locations[s2]},
                "distance_km": distance_km, "note": dist_note,
            })
    return {"subject_locations": subject_locations, "geocoded": geocoded, "comparisons": comparisons}


def _communication_likelihood(processed):
    subject_plats = {}
    for subject, data in processed.items():
        plats = set()
        for cat in ["messaging", "social", "file_transfer", "crypto", "anonymous_chat", "live_streaming", "pakistan_isp"]:
            for hit in data["platform_hits"].get(cat, []):
                plats.add(hit["platform"])
        subject_plats[subject] = plats
    pairs = []
    subs = list(subject_plats.keys())
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            s1, s2 = subs[i], subs[j]
            shared = subject_plats[s1] & subject_plats[s2]
            total = subject_plats[s1] | subject_plats[s2]
            ratio = len(shared) / len(total) if total else 0
            likelihood = "LOW"
            if ratio > 0.5:
                likelihood = "HIGH"
            elif ratio > 0.2:
                likelihood = "MEDIUM"
            encrypted_shared = shared & {"Signal", "Telegram", "Wickr", "Silent Phone", "ICQ New"}
            if encrypted_shared and likelihood != "HIGH":
                likelihood = "HIGH" if likelihood == "MEDIUM" else "MEDIUM"
            pairs.append({
                "subject1": s1, "subject2": s2, "shared_platforms": list(shared),
                "overlap_ratio": round(ratio, 2), "likelihood": likelihood,
            })
    return {"pairs": pairs}


def _get_common_contacts(processed):
    """Find contacts shared between subjects using summary data."""
    subject_contacts = {}
    for subject, data in processed.items():
        subject_contacts[subject] = set(data.get("contacts", {}).keys())
    all_contacts = defaultdict(list)
    for subject, contacts in subject_contacts.items():
        for c in contacts:
            all_contacts[c].append(subject)
    return {k: v for k, v in all_contacts.items() if len(v) >= 2}


def _relationship_graph(processed):
    nodes = []
    links = []
    for subject in processed:
        nodes.append({"id": subject, "type": "subject", "label": subject})
    added_platforms = set()
    for subject, data in processed.items():
        for plat in data["all_platforms"]:
            if plat not in added_platforms:
                cat = "unknown"
                for c, ps in PLATFORM_DB.items():
                    if plat in ps:
                        cat = c
                        break
                nodes.append({"id": plat, "type": "platform", "category": cat, "label": plat})
                added_platforms.add(plat)
            links.append({"source": subject, "target": plat, "type": "uses"})
    common = _get_common_contacts(processed)
    for num, subs in list(common.items())[:15]:
        cid = f"C:{num[-6:]}" if len(num) > 6 else f"C:{num}"
        nodes.append({"id": cid, "type": "contact", "label": num})
        for s in subs:
            links.append({"source": s, "target": cid, "type": "contact"})
    return {"nodes": nodes, "links": links}


def _behavioral_profiling(processed):
    profiles = {}
    for subject, data in processed.items():
        counts = data.get("platform_counts", {})
        cats = {cat: sum(pc.values()) for cat, pc in counts.items()}
        cdr_count = data.get("cdr_count", len(data.get("cdr", [])))
        ipdr_count = data.get("ipdr_count", len(data.get("ipdr", [])))
        role = "Under Analysis"
        behavior = []
        if cats.get("crypto", 0) > 2:
            role = "Financial Handler"
            behavior.append("cryptocurrency")
        if cats.get("messaging", 0) > 5:
            if role == "Under Analysis": role = "Communicator"
            behavior.append("messaging")
        if cats.get("file_transfer", 0) > 2:
            if role == "Under Analysis": role = "Data Handler"
            behavior.append("file_transfer")
        if cats.get("vpn_proxy", 0) > 0:
            behavior.append("privacy-oriented")
        if cats.get("social", 0) > 3:
            behavior.append("social_media")
        if cats.get("anonymous_chat", 0) > 0:
            behavior.append("anonymous_chat")
        if cats.get("pakistan_isp", 0) > 0:
            behavior.append("pakistan_isp_contact")
        if cats.get("live_streaming", 0) > 0:
            behavior.append("live_streaming")
        if cdr_count > 30:
            if role == "Under Analysis": role = "Coordinator"
            behavior.append("high_call_volume")
        imeis = data.get("imeis", {})
        risk_indicators = []
        if "cryptocurrency" in behavior:
            risk_indicators.append("Cryptocurrency platform usage detected")
        if "privacy-oriented" in behavior:
            risk_indicators.append("VPN/Proxy usage — privacy awareness")
        if "anonymous_chat" in behavior:
            risk_indicators.append("Anonymous chat app usage (Whisper/BIGO)")
        if "pakistan_isp_contact" in behavior:
            risk_indicators.append("Pakistan ISP endpoint contact detected — HIGH PRIORITY")
        if len(imeis) > 1:
            risk_indicators.append(f"Multiple devices ({len(imeis)} IMEIs)")
        profiles[subject] = {
            "role": role, "behavior_type": behavior,
            "platforms_used": list(data["all_platforms"]),
            "category_counts": cats,
            "cdr_records": cdr_count, "ipdr_records": ipdr_count,
            "imeis": list(imeis.keys()), "risk_indicators": risk_indicators,
        }
    all_imeis = defaultdict(list)
    for subject, p in profiles.items():
        for imei in p["imeis"]:
            all_imeis[imei].append(subject)
    shared_devices = {k: v for k, v in all_imeis.items() if len(v) > 1}
    return {"profiles": profiles, "shared_devices": shared_devices}


def _common_contacts(processed):
    """Enhanced common contacts using pre-extracted contact summaries with day/time."""
    subject_contacts = {}
    for subject, data in processed.items():
        subject_contacts[subject] = data.get("contacts", {})
    subs = list(subject_contacts.keys())
    pairwise = {}
    for i in range(len(subs)):
        for j in range(i + 1, len(subs)):
            s1, s2 = subs[i], subs[j]
            nums1 = set(subject_contacts.get(s1, {}).keys())
            nums2 = set(subject_contacts.get(s2, {}).keys())
            shared = nums1 & nums2
            shared_details = []
            for num in list(shared)[:20]:
                detail = {"number": num}
                detail[f"{s1}_calls"] = subject_contacts[s1].get(num, {}).get("count", 0)
                detail[f"{s2}_calls"] = subject_contacts[s2].get(num, {}).get("count", 0)
                detail[f"{s1}_sample_times"] = subject_contacts[s1].get(num, {}).get("times", [])[:5]
                detail[f"{s2}_sample_times"] = subject_contacts[s2].get(num, {}).get("times", [])[:5]
                shared_details.append(detail)
            pairwise[f"{s1} <-> {s2}"] = {"count": len(shared), "numbers": list(shared)[:20], "details": shared_details}
    all_sets = [set(subject_contacts.get(s, {}).keys()) for s in subs]
    common_all = list(set.intersection(*all_sets))[:20] if all_sets and all(all_sets) else []
    total = len(_get_common_contacts(processed))
    return {
        "pairwise_common": pairwise, "common_across_all": common_all,
        "total_common_contacts": total,
        "subject_contact_counts": {s: len(c) for s, c in subject_contacts.items()},
    }


def _imei_analysis(processed):
    """IMEI cross-analysis using pre-extracted IMEI summaries."""
    subject_imeis = {}
    for subject, data in processed.items():
        subject_imeis[subject] = data.get("imeis", {})
    all_imeis = defaultdict(list)
    for subject, imeis in subject_imeis.items():
        for imei, info in imeis.items():
            all_imeis[imei].append({"subject": subject, **info})
    shared_imeis = []
    for imei, users in all_imeis.items():
        if len(users) > 1:
            shared_imeis.append({
                "imei": imei, "subjects": [u["subject"] for u in users],
                "users": users, "risk": "HIGH" if len(users) > 2 else "MEDIUM",
                "note": f"IMEI {imei} used by {', '.join(u['subject'] for u in users)} — possible device sharing/swapping",
            })
    return {
        "subject_imeis": subject_imeis, "shared_imeis": shared_imeis,
        "total_unique_imeis": len(all_imeis),
    }


def _bulk_transfer_analysis(processed):
    """Detect data-exfiltration / bulk-transfer patterns using IPDR volume metadata.

    Surfaces:
      - Per-subject top heavy-transfer sessions (capped)
      - Per-subject platform-level volume breakdown
      - Cross-subject pattern: same platform used heavily by multiple subjects
      - Upload-heavy sessions (volume_up >= 3x volume_down) — exfiltration signature
    """
    per_subject = {}
    has_any_volume = False
    for subject, data in processed.items():
        sessions = data.get("bulk_sessions", [])
        plat_vol = data.get("platform_volume", {})
        total_up = data.get("total_volume_up", 0)
        total_down = data.get("total_volume_down", 0)
        if sessions or plat_vol:
            has_any_volume = True
        # Format bytes for display
        formatted_sessions = []
        for s in sessions[:25]:
            formatted_sessions.append({
                **s,
                "volume_up_human": _format_bytes(s["volume_up_bytes"]),
                "volume_down_human": _format_bytes(s["volume_down_bytes"]),
                "volume_total_human": _format_bytes(s["volume_total_bytes"]),
            })
        # Top platforms by volume
        top_platforms = sorted(plat_vol.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
        top_plat_formatted = [
            {
                "platform": p,
                "total_bytes": v["total"],
                "up_bytes": v["up"],
                "down_bytes": v["down"],
                "sessions": v["sessions"],
                "total_human": _format_bytes(v["total"]),
                "up_human": _format_bytes(v["up"]),
                "down_human": _format_bytes(v["down"]),
            }
            for p, v in top_platforms
        ]
        upload_heavy = [s for s in formatted_sessions if s.get("is_upload_heavy")]
        per_subject[subject] = {
            "alert_count": sum(1 for s in sessions if s["severity"] == "ALERT"),
            "high_count": sum(1 for s in sessions if s["severity"] == "HIGH"),
            "medium_count": sum(1 for s in sessions if s["severity"] == "MEDIUM"),
            "total_up_bytes": total_up,
            "total_down_bytes": total_down,
            "total_up_human": _format_bytes(total_up),
            "total_down_human": _format_bytes(total_down),
            "top_sessions": formatted_sessions,
            "top_platforms": top_plat_formatted,
            "upload_heavy_sessions": upload_heavy[:10],
        }

    # Cross-subject correlation: which platforms are heavily used by multiple subjects?
    platform_subjects = defaultdict(list)
    for subject, info in per_subject.items():
        for p in info["top_platforms"]:
            if p["total_bytes"] >= BULK_HIGH_BYTES:
                platform_subjects[p["platform"]].append({"subject": subject, "total_human": p["total_human"]})
    shared_heavy = [
        {"platform": p, "subjects": users, "inference": f"{len(users)} subjects show heavy data activity on {p} — coordinated exfiltration channel?"}
        for p, users in platform_subjects.items() if len(users) > 1
    ]

    return {
        "per_subject": per_subject,
        "shared_heavy_platforms": shared_heavy,
        "has_volume_data": has_any_volume,
    }


def _cell_colocation(processed):
    """Detect when two subjects appear on the same cell tower within ±5 min.

    Returns events sorted by time-diff (closest first). Each event names the
    cell ID, both subjects, the timestamps and the gap. Strong signal of
    physical co-presence (much stronger than city-level geocoding)."""
    subject_sessions = {s: data.get("cell_sessions", []) for s, data in processed.items()}
    has_cell_data = any(subject_sessions.values())

    # Build cell_id → list of (subject, timestamp)
    cell_index = defaultdict(list)
    for subject, sessions in subject_sessions.items():
        for s in sessions:
            cell_index[s["cell_id"]].append({"subject": subject, "timestamp": s["timestamp"]})

    coloc_events = []
    seen_pairs = set()  # dedupe near-identical events at same cell within ~30s
    for cid, entries in cell_index.items():
        if len({e["subject"] for e in entries}) < 2:
            continue
        # Sort by time then sweep for cross-subject neighbours
        entries.sort(key=lambda e: e["timestamp"])
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                e1, e2 = entries[i], entries[j]
                if e1["subject"] == e2["subject"]:
                    continue
                try:
                    t1 = datetime.fromisoformat(e1["timestamp"])
                    t2 = datetime.fromisoformat(e2["timestamp"])
                    diff = abs((t2 - t1).total_seconds())
                except (ValueError, TypeError):
                    continue
                if diff > CELL_COLOC_WINDOW_SEC:
                    break  # entries sorted, no need to scan further
                pair_key = (cid, frozenset((e1["subject"], e2["subject"])), int(diff // 30))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                coloc_events.append({
                    "cell_id": cid,
                    "subjects": sorted([e1["subject"], e2["subject"]]),
                    "subject1": e1["subject"], "subject2": e2["subject"],
                    "timestamp1": e1["timestamp"], "timestamp2": e2["timestamp"],
                    "time_diff_seconds": diff,
                })

    coloc_events.sort(key=lambda x: x["time_diff_seconds"])

    # Per-pair tally
    pair_tally = defaultdict(lambda: {"count": 0, "cells": set(), "min_diff": float("inf")})
    for ev in coloc_events:
        key = " ⇄ ".join(ev["subjects"])
        pair_tally[key]["count"] += 1
        pair_tally[key]["cells"].add(ev["cell_id"])
        if ev["time_diff_seconds"] < pair_tally[key]["min_diff"]:
            pair_tally[key]["min_diff"] = ev["time_diff_seconds"]
    pair_summary = [
        {
            "pair": k,
            "count": v["count"],
            "unique_cells": len(v["cells"]),
            "min_diff_seconds": v["min_diff"],
            "cells_sample": list(v["cells"])[:5],
        }
        for k, v in pair_tally.items()
    ]
    pair_summary.sort(key=lambda x: x["count"], reverse=True)

    return {
        "events": coloc_events[:50],
        "total_events": len(coloc_events),
        "pair_summary": pair_summary,
        "subject_cell_counts": {s: len({c["cell_id"] for c in cs}) for s, cs in subject_sessions.items()},
        "has_cell_data": has_cell_data,
    }


def _sim_analysis(processed):
    """Detect SIM-swap behaviour, foreign SIMs, and shared SIMs across subjects.

    Three flags:
      1. Foreign SIM — IMSI MCC outside India (404/405/406)
      2. SIM-swap — a single IMEI used with multiple IMSIs (within or across subjects)
      3. Shared IMSI — same IMSI seen on records of multiple subjects
    """
    has_imsi_data = any(data.get("imsis") for data in processed.values())

    per_subject = {}
    foreign_sims = []
    multi_imsi_subjects = []
    for subject, data in processed.items():
        imsis = data.get("imsis", {})
        if not imsis:
            per_subject[subject] = {"imsi_count": 0, "imsis": [], "foreign_count": 0}
            continue
        imsi_list = []
        foreign_count = 0
        for imsi, info in imsis.items():
            entry = {"imsi": imsi, **info}
            imsi_list.append(entry)
            if info.get("is_foreign"):
                foreign_count += 1
                foreign_sims.append({"subject": subject, "imsi": imsi, **info})
        imsi_list.sort(key=lambda x: x.get("count", 0), reverse=True)
        per_subject[subject] = {
            "imsi_count": len(imsi_list),
            "imsis": imsi_list,
            "foreign_count": foreign_count,
        }
        if len(imsi_list) > 1:
            multi_imsi_subjects.append({
                "subject": subject,
                "imsi_count": len(imsi_list),
                "imsis": [e["imsi"] for e in imsi_list],
                "inference": f"{subject} used {len(imsi_list)} different SIMs — SIM-swap / multi-SIM behaviour",
            })

    # Cross-subject IMSI sharing
    imsi_to_subjects = defaultdict(list)
    for subject, info in per_subject.items():
        for entry in info["imsis"]:
            imsi_to_subjects[entry["imsi"]].append(subject)
    shared_imsis = [
        {"imsi": imsi, "subjects": list(set(subs)),
         "inference": f"IMSI {imsi} appears on records of {', '.join(set(subs))} — shared/relayed SIM"}
        for imsi, subs in imsi_to_subjects.items() if len(set(subs)) > 1
    ]

    # SIM-swap: IMEI seen with multiple IMSIs (using the imei_imsi_pairs we collected)
    imei_to_imsis = defaultdict(set)
    for subject, data in processed.items():
        for pair in data.get("imei_imsi_pairs", []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                imei, imsi = pair
                imei_to_imsis[imei].add(imsi)
    sim_swaps = [
        {"imei": imei, "imsis": list(imsis),
         "inference": f"Device {imei} swapped between {len(imsis)} SIMs — strong SIM-swap signal"}
        for imei, imsis in imei_to_imsis.items() if len(imsis) > 1
    ]

    return {
        "per_subject": per_subject,
        "foreign_sims": foreign_sims,
        "multi_imsi_subjects": multi_imsi_subjects,
        "shared_imsis": shared_imsis,
        "sim_swaps": sim_swaps,
        "has_imsi_data": has_imsi_data,
    }


def _risk_scores(processed):
    scores = {}
    for subject, data in processed.items():
        score = 0
        factors = []
        counts = data.get("platform_counts", {})
        crypto = sum(counts.get("crypto", {}).values())
        if crypto:
            score += min(crypto * 5, 30)
            factors.append(f"Cryptocurrency access ({crypto} sessions)")
        encrypted_set = {"Signal", "Telegram", "Wickr", "Threema", "Silent Phone", "ICQ New"}
        enc_count = sum(v for k, v in counts.get("messaging", {}).items() if k in encrypted_set)
        enc_count += sum(v for k, v in counts.get("anonymous_chat", {}).items() if k in encrypted_set)
        if enc_count:
            score += min(enc_count * 3, 20)
            factors.append(f"Encrypted messaging ({enc_count} sessions)")
        vpn = sum(counts.get("vpn_proxy", {}).values())
        if vpn:
            score += min(vpn * 5, 15)
            factors.append(f"VPN/Proxy usage ({vpn} sessions)")
        ft = sum(counts.get("file_transfer", {}).values())
        if ft:
            score += min(ft * 3, 15)
            factors.append(f"File transfer activity ({ft} sessions)")
        pak_isp = sum(counts.get("pakistan_isp", {}).values())
        if pak_isp:
            score += min(pak_isp * 10, 25)
            factors.append(f"Pakistan ISP contact ({pak_isp} sessions) — HIGH PRIORITY")
        anon = sum(counts.get("anonymous_chat", {}).values())
        if anon:
            score += min(anon * 4, 15)
            factors.append(f"Anonymous chat usage ({anon} sessions)")
        cdr_count = data.get("cdr_count", len(data.get("cdr", [])))
        ipdr_count = data.get("ipdr_count", len(data.get("ipdr", [])))
        total_recs = cdr_count + ipdr_count
        if total_recs > 100:
            score += 10
            factors.append(f"High activity volume ({total_recs:,} records)")

        # Bulk transfer signal — large outbound = exfiltration risk
        bulk_sessions = data.get("bulk_sessions", [])
        alert_sessions = sum(1 for s in bulk_sessions if s.get("severity") == "ALERT")
        upload_heavy = sum(1 for s in bulk_sessions if s.get("is_upload_heavy"))
        if alert_sessions:
            score += min(alert_sessions * 8, 20)
            factors.append(f"{alert_sessions} bulk transfer ALERT(s) (>500 MB)")
        if upload_heavy:
            score += min(upload_heavy * 6, 15)
            factors.append(f"{upload_heavy} upload-heavy session(s) — possible data exfiltration")

        # Foreign SIM signal
        imsis = data.get("imsis", {})
        foreign_imsis = [i for i, info in imsis.items() if info.get("is_foreign")]
        if foreign_imsis:
            score += min(len(foreign_imsis) * 12, 25)
            factors.append(f"Foreign SIM detected ({len(foreign_imsis)} IMSI, country: {imsis[foreign_imsis[0]].get('country')})")
        if len(imsis) > 1:
            score += 8
            factors.append(f"Multiple SIMs used ({len(imsis)} IMSIs) — SIM-swap behaviour")

        score = min(score, 100)
        level = "CRITICAL" if score >= 70 else "HIGH" if score >= 50 else "MEDIUM" if score >= 30 else "LOW"
        scores[subject] = {"score": score, "level": level, "factors": factors}
    return scores


def _priority_leads(processed):
    leads = []
    common = _get_common_contacts(processed)
    all_subjects = set(processed.keys())
    common_all = {k: v for k, v in common.items() if set(v) == all_subjects}
    for num, subs in sorted(common_all.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        leads.append({
            "type": "common_contact", "priority": "HIGH", "value": num, "subjects": subs,
            "action": f"Run subscriber details (CAF), tower history, IMEI history, financial KYC for {num}",
        })
    for num, subs in sorted(common.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        if num not in common_all:
            leads.append({
                "type": "shared_contact", "priority": "MEDIUM", "value": num, "subjects": subs,
                "action": f"Investigate relationship with {num} — shared between {', '.join(subs)}",
            })
    seen_ips = set()
    for subject, data in processed.items():
        for hit in data["platform_hits"].get("crypto", []):
            ip = hit.get("ip")
            if ip and ip not in seen_ips:
                seen_ips.add(ip)
                leads.append({
                    "type": "crypto_endpoint", "priority": "HIGH", "value": ip, "subjects": [subject],
                    "action": f"Obtain transaction logs for {hit['platform']} endpoint {ip}",
                })
    return leads[:20]


def _interrogation_questions(processed):
    questions = {}
    common = _get_common_contacts(processed)
    for subject, data in processed.items():
        qs = []
        crypto_plats = set()
        for cat_counts in [data.get("platform_counts", {}).get("crypto", {})]:
            crypto_plats.update(cat_counts.keys())
        if crypto_plats:
            qs.append(f"Do you have accounts on {', '.join(crypto_plats)}? What is the purpose?")
            qs.append("Have you transferred or received cryptocurrency from anyone? Provide transaction details.")
            qs.append("Who else has access to your cryptocurrency wallet(s)?")
        msg_plats = set()
        for cat in ["messaging", "anonymous_chat"]:
            msg_plats.update(data.get("platform_counts", {}).get(cat, {}).keys())
        if msg_plats:
            qs.append(f"Who do you communicate with on {', '.join(msg_plats)}?")
            encrypted = msg_plats & {"Signal", "Wickr", "Threema", "Silent Phone"}
            if encrypted:
                qs.append(f"Why do you prefer encrypted apps like {', '.join(encrypted)} over regular messaging?")
        ft_plats = set(data.get("platform_counts", {}).get("file_transfer", {}).keys())
        if ft_plats:
            qs.append(f"What files have you shared via {', '.join(ft_plats)}? Who were the recipients?")
        subject_common = [num for num, subs in common.items() if subject in subs]
        for num in subject_common[:3]:
            others = [s for s in common[num] if s != subject]
            qs.append(f"What is your relationship with the user of number {num}? (Also in records of {', '.join(others)})")
        if not qs:
            qs.append("Describe your regular communication patterns and devices you use.")
        questions[subject] = qs
    return questions
