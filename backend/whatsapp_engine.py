"""WhatsApp Analysis Engine — Phase 1.

Pure rule-based analysis over parsed WhatsApp messages + attachments. Produces:
  - Entities (phones, emails, URLs, INR amounts, places)
  - Per-participant statistics (volume, hours of activity, response gaps)
  - Hourly heatmap (24x7)
  - Silent periods (gaps > N hours)
  - Relationship graph (participants + extracted phones)
  - Cross-correlation with case CDR/IPDR subjects (phone-match)

Nothing fancy. Nothing AI. No claims we can't substantiate.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Entity-extraction regexes — kept conservative, false-positive rate is low.
# --------------------------------------------------------------------------- #
# Indian-style mobile (10-digit starting 6-9, optional +91 / 91 / 0 prefix) — primary
# Generic 11-15 digit international numbers — fallback
# Both forms forbid being part of a larger digit run AND must not be flanked by
# date-separators (-, /) so timestamps in filenames don't trigger us.
_PHONE_RE = re.compile(
    r"""
    (?<![\d/\-])                                    # not preceded by digit or date sep
    (?:
        (?:\+?91[\s\-]?)?[6-9]\d{9}                 # India mobile (with optional cc)
        |
        \+\d{10,14}                                 # leading-+ international
    )
    (?![\d/\-])                                     # not followed by digit or date sep
    """,
    re.VERBOSE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# URL: must start with http(s):// OR be a www. / known-domain hostname
_URL_RE = re.compile(
    r"""\b(?:
        https?://[^\s,\)\]\}]+
        |
        www\.[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?:/[^\s,\)\]\}]*)?
    )""",
    re.VERBOSE,
)
# Amount: ₹/Rs/INR/$ + number, OR a bare 3+ digit number followed by a recognized unit
_AMOUNT_RE = re.compile(
    r"""(?:(?:₹|Rs\.?|INR|USD|\$|€|£)\s?\d{1,3}(?:[,]\d{3})*(?:\.\d{1,2})?
       |\b\d{2,3}(?:,\d{3})+(?:\.\d{1,2})?\s?(?:rupees|rs|inr)?\b)""",
    re.VERBOSE | re.IGNORECASE,
)

# Small built-in India-focused gazetteer for place hints. Investigators can
# obviously extend this — but Phase 1 ships with the basics common to LEA cases.
_PLACE_GAZETTEER = [
    # J&K
    "Srinagar", "Jammu", "Kashmir", "Anantnag", "Baramulla", "Pulwama",
    "Pahalgam", "Gulmarg", "Sonmarg", "Sopore", "Kupwara", "Bandipora",
    "Budgam", "Doda", "Kishtwar", "Rajouri", "Poonch", "Udhampur",
    # Major hubs / transit
    "Delhi", "Mumbai", "Kolkata", "Chennai", "Bangalore", "Hyderabad",
    "Ahmedabad", "Pune", "Lucknow", "Patna", "Bhopal", "Indore",
    # Sensitive proximity
    "Pakistan", "Wagah", "LoC", "Line of Control",
    # Local examples in fixture
    "Dudhpatri", "Yousmarg", "Bemina", "Lal Chowk", "Nowgam", "Sumbal",
    "Wangipora", "Hazratbal", "Dal Lake",
]
_PLACE_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PLACE_GAZETTEER) + r")\b",
                       re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def analyze(parsed_export: dict, case_subjects: list[dict] | None = None) -> dict:
    """Take a parsed export (dict produced by whatsapp_parser.to_dict) and return
    a complete analysis payload ready for the UI / report layer.

    `case_subjects`: optional list of {name, phone, imei, ...} from the parent
    case so we can flag overlaps.
    """
    messages = parsed_export.get("messages", [])
    participants = parsed_export.get("participants", [])
    attachments = parsed_export.get("attachments", [])

    # Phase 1 — extract entities from every text/OCR'd body
    entities = _extract_entities(messages, attachments)

    # Per-participant stats
    per_participant = _participant_stats(messages)

    # Hourly heatmap (7 days x 24 hours)
    heatmap = _heatmap(messages)

    # Silent periods
    silent_periods = _silent_periods(messages, threshold_hours=24)

    # Conversation overview
    overview = _overview(messages, parsed_export)

    # Relationship graph — participants + their detected phones
    graph = _relationship_graph(participants, entities, case_subjects or [])

    # Cross-correlation with case CDR/IPDR subjects
    subject_links = _subject_links(participants, entities, case_subjects or [])

    # Suspicious indicators — explicitly low confidence, framed as such
    indicators = _indicators(messages, entities, silent_periods, per_participant)

    return {
        "overview": overview,
        "participants": participants,
        "entities": entities,
        "per_participant": per_participant,
        "heatmap": heatmap,
        "silent_periods": silent_periods,
        "relationship_graph": graph,
        "subject_links": subject_links,
        "indicators": indicators,
        "attachment_summary": _attachment_summary(attachments),
        "parse_warnings": parsed_export.get("parse_warnings", []),
        "media_review_queue": [
            {"filename": a["filename"], "mime": a["mime_hint"], "reason": a.get("review_reason")}
            for a in attachments if a.get("needs_manual_review")
        ],
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def _extract_entities(messages: list[dict], attachments: list[dict]) -> dict:
    """Scan message bodies + OCR text for entities. Returns counts and per-entity
    sample messages."""
    phones, emails, urls, amounts, places = Counter(), Counter(), Counter(), Counter(), Counter()
    samples = defaultdict(list)  # entity -> first 3 occurrences (line_no, sender, body snippet)

    def _scan(text: str, source_label: str):
        if not text:
            return
        for m in _PHONE_RE.findall(text):
            p = _normalize_phone(m)
            if 7 <= len(p) <= 15:
                phones[p] += 1
                if len(samples[f"phone:{p}"]) < 3:
                    samples[f"phone:{p}"].append({"source": source_label, "snippet": text[:120]})
        for e in _EMAIL_RE.findall(text):
            emails[e.lower()] += 1
            if len(samples[f"email:{e.lower()}"]) < 3:
                samples[f"email:{e.lower()}"].append({"source": source_label, "snippet": text[:120]})
        for u in _URL_RE.findall(text):
            url = u.lower().strip(".,);")
            urls[url] += 1
            if len(samples[f"url:{url}"]) < 3:
                samples[f"url:{url}"].append({"source": source_label, "snippet": text[:120]})
        for amt in _AMOUNT_RE.findall(text):
            amounts[amt.strip()] += 1
            if len(samples[f"amount:{amt.strip()}"]) < 3:
                samples[f"amount:{amt.strip()}"].append({"source": source_label, "snippet": text[:120]})
        for place in _PLACE_RE.findall(text):
            key = place.title()
            places[key] += 1
            if len(samples[f"place:{key}"]) < 3:
                samples[f"place:{key}"].append({"source": source_label, "snippet": text[:120]})

    for msg in messages:
        if msg.get("body"):
            label = f"msg L{msg.get('line_no')} ({msg.get('sender')})"
            _scan(msg["body"], label)

    # Also scan OCR text from image attachments
    for a in attachments:
        ocr = a.get("ocr_text")
        if ocr:
            _scan(ocr, f"OCR: {a['filename']}")

    return {
        "phones": [{"value": v, "count": c} for v, c in phones.most_common()],
        "emails": [{"value": v, "count": c} for v, c in emails.most_common()],
        "urls": [{"value": v, "count": c} for v, c in urls.most_common()],
        "amounts": [{"value": v, "count": c} for v, c in amounts.most_common()],
        "places": [{"value": v, "count": c} for v, c in places.most_common()],
        "samples": dict(samples),
    }


def _participant_stats(messages: list[dict]) -> dict:
    out = {}
    for msg in messages:
        sender = msg.get("sender")
        if not sender:
            continue
        stats = out.setdefault(sender, {
            "total_messages": 0,
            "text_messages": 0,
            "media_messages": 0,
            "deleted_count": 0,
            "first_message_ts": None,
            "last_message_ts": None,
            "active_hours": Counter(),
            "active_dow": Counter(),  # 0=Mon
            "body_chars_total": 0,
        })
        stats["total_messages"] += 1
        kind = msg.get("kind", "text")
        if kind == "text":
            stats["text_messages"] += 1
        elif kind == "media":
            stats["media_messages"] += 1
        elif kind == "deleted":
            stats["deleted_count"] += 1
        stats["body_chars_total"] += len(msg.get("body", "") or "")
        ts_str = msg.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if stats["first_message_ts"] is None or ts.isoformat() < stats["first_message_ts"]:
                    stats["first_message_ts"] = ts.isoformat()
                if stats["last_message_ts"] is None or ts.isoformat() > stats["last_message_ts"]:
                    stats["last_message_ts"] = ts.isoformat()
                stats["active_hours"][ts.hour] += 1
                stats["active_dow"][ts.weekday()] += 1
            except ValueError:
                continue
    for sender, s in out.items():
        s["active_hours"] = {str(k): v for k, v in s["active_hours"].items()}
        s["active_dow"] = {str(k): v for k, v in s["active_dow"].items()}
        s["avg_msg_length"] = (s["body_chars_total"] / s["total_messages"]) if s["total_messages"] else 0
    return out


def _heatmap(messages: list[dict]) -> dict:
    """7-day x 24-hour matrix of message counts (all participants)."""
    matrix = [[0] * 24 for _ in range(7)]
    for msg in messages:
        ts_str = msg.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            matrix[ts.weekday()][ts.hour] += 1
        except ValueError:
            continue
    return {"matrix": matrix, "row_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}


def _silent_periods(messages: list[dict], threshold_hours: int = 24) -> list[dict]:
    """Return list of (start, end, hours_silent) intervals where no message was sent."""
    timestamps = []
    for msg in messages:
        ts_str = msg.get("timestamp")
        if ts_str:
            try:
                timestamps.append(datetime.fromisoformat(ts_str))
            except ValueError:
                continue
    timestamps.sort()
    out = []
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        if gap >= timedelta(hours=threshold_hours):
            out.append({
                "start_ts": timestamps[i - 1].isoformat(),
                "end_ts": timestamps[i].isoformat(),
                "duration_hours": round(gap.total_seconds() / 3600, 1),
            })
    out.sort(key=lambda x: x["duration_hours"], reverse=True)
    return out[:25]


def _overview(messages: list[dict], parsed_export: dict) -> dict:
    timestamps = [
        datetime.fromisoformat(m["timestamp"]) for m in messages
        if m.get("timestamp")
    ]
    first = min(timestamps).isoformat() if timestamps else None
    last = max(timestamps).isoformat() if timestamps else None
    duration_days = (max(timestamps) - min(timestamps)).days if timestamps else 0
    return {
        "chat_filename": parsed_export.get("chat_filename"),
        "total_messages": len(messages),
        "total_participants": len(parsed_export.get("participants", [])),
        "first_message_ts": first,
        "last_message_ts": last,
        "duration_days": duration_days,
        "total_attachments": len(parsed_export.get("attachments", [])),
        "unparseable_lines": parsed_export.get("unparseable_lines", 0),
    }


def _relationship_graph(participants: list[str], entities: dict,
                        case_subjects: list[dict]) -> dict:
    """Build a small graph: participants + non-participant phone numbers
    referenced inside the chat.

    Phase-1 honest scope: we do NOT attempt to attribute *which* participant
    mentioned a given phone — that would require a per-message scan whose
    output we currently treat as low-confidence. Instead we emit:

      * One node per participant
      * One node per top-mentioned phone (with mention count as weight)
      * A single 'chat' hub node connecting all participants to the phones
        they collectively reference. This is visually honest: it shows
        'these phones surfaced inside this chat' without falsely linking
        each phone to each individual participant.
    """
    nodes = []
    links = []
    for p in participants:
        nodes.append({"id": f"p:{p}", "type": "participant", "label": p})

    # Anchor 'chat' node — participants connect TO it, phones connect FROM it.
    chat_node_id = "chat:hub"
    top_phones = entities.get("phones", [])[:10]
    if top_phones:
        nodes.append({
            "id": chat_node_id, "type": "chat",
            "label": "This chat",
            "weight": sum(e["count"] for e in top_phones),
        })
        for p in participants:
            links.append({"source": f"p:{p}", "target": chat_node_id, "type": "participates_in"})
        for entry in top_phones:
            node_id = f"phone:{entry['value']}"
            nodes.append({
                "id": node_id, "type": "phone", "label": entry["value"],
                "weight": entry["count"],
            })
            links.append({
                "source": chat_node_id, "target": node_id,
                "type": "mentioned", "count": entry["count"],
            })

    # Pin known case subjects
    for s in case_subjects:
        if s.get("phone"):
            ph = _normalize_phone(s["phone"])
            nid = f"phone:{ph}"
            if not any(n["id"] == nid for n in nodes):
                nodes.append({
                    "id": nid, "type": "subject",
                    "label": f"{s['name']} ({ph})", "is_case_subject": True,
                })
    return {"nodes": nodes, "links": links}


def _subject_links(participants: list[str], entities: dict,
                   case_subjects: list[dict]) -> dict:
    """Find: (a) WhatsApp participant names that match a case subject;
            (b) phones extracted from chat that match a case subject."""
    matched_by_phone = []
    chat_phones = {e["value"]: e["count"] for e in entities.get("phones", [])}
    for s in case_subjects:
        if not s.get("phone"):
            continue
        ph = _normalize_phone(s["phone"])
        if ph in chat_phones:
            matched_by_phone.append({
                "subject_name": s["name"],
                "subject_phone": s["phone"],
                "occurrences": chat_phones[ph],
                "inference": f"Subject's phone ({ph}) is mentioned in chat {chat_phones[ph]} time(s) — possible direct link",
            })
    matched_by_name = []
    sub_names_lower = {s["name"].lower(): s for s in case_subjects}
    for p in participants:
        if p.lower() in sub_names_lower:
            s = sub_names_lower[p.lower()]
            matched_by_name.append({
                "participant": p,
                "subject_name": s["name"],
                "inference": f"Chat participant name matches case subject {s['name']} — possible identity",
            })
    return {"by_phone": matched_by_phone, "by_name": matched_by_name}


def _indicators(messages: list[dict], entities: dict,
                silent_periods: list[dict], per_participant: dict) -> list[dict]:
    """Surface rule-based indicators. All explicitly low-confidence and labelled."""
    out = []
    # 1. Deleted-message density
    total = sum(s["total_messages"] for s in per_participant.values()) or 1
    total_deleted = sum(s["deleted_count"] for s in per_participant.values())
    if total_deleted >= 5 and (total_deleted / total) > 0.05:
        out.append({
            "tag": "DELETED_MARKERS",
            "severity": "LOW",
            "title": f"{total_deleted} deleted-message markers detected",
            "detail": (
                "Note: the export only retains the marker, not the content. "
                "More than 5% of messages were deleted — worth a manual scan of the surrounding context."
            ),
        })
    # 2. Long silent periods
    long_silents = [s for s in silent_periods if s["duration_hours"] >= 72]
    if long_silents:
        out.append({
            "tag": "LONG_SILENCE",
            "severity": "LOW",
            "title": f"{len(long_silents)} silent period(s) ≥ 3 days",
            "detail": f"Longest: {long_silents[0]['duration_hours']:.0f}h "
                      f"({long_silents[0]['start_ts'][:10]} → {long_silents[0]['end_ts'][:10]})",
        })
    # 3. Late-night activity (00:00–05:00)
    late_night_msgs = 0
    for msg in messages:
        ts_str = msg.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            if 0 <= ts.hour < 5:
                late_night_msgs += 1
        except ValueError:
            continue
    if late_night_msgs >= 10:
        out.append({
            "tag": "LATE_NIGHT_ACTIVITY",
            "severity": "LOW",
            "title": f"{late_night_msgs} messages between 00:00–05:00 local time",
            "detail": "Heavy late-night messaging is a weak operational-coordination hint.",
        })
    # 4. Foreign / sensitive-place mentions
    places = entities.get("places", [])
    sensitive = [p for p in places if p["value"].lower() in (
        "pakistan", "wagah", "loc", "line of control"
    )]
    if sensitive:
        out.append({
            "tag": "SENSITIVE_PLACE",
            "severity": "MEDIUM",
            "title": f"Sensitive-place mention(s): {', '.join(p['value'] for p in sensitive)}",
            "detail": "Cross-border / LoC mentions surfaced from chat or OCR text.",
        })
    # 5. Financial talk volume
    if len(entities.get("amounts", [])) >= 5:
        out.append({
            "tag": "FINANCIAL_TALK",
            "severity": "LOW",
            "title": f"{len(entities['amounts'])} distinct monetary amounts mentioned",
            "detail": "Frequent money references can indicate procurement, settlements or transactions — investigate context.",
        })
    return out


def _attachment_summary(attachments: list[dict]) -> dict:
    by_kind = Counter(a["mime_hint"] for a in attachments)
    # Detect duplicates by perceptual hash
    phash_groups = defaultdict(list)
    for a in attachments:
        if a.get("perceptual_hash"):
            phash_groups[a["perceptual_hash"]].append(a["filename"])
    duplicates = [
        {"perceptual_hash": h, "files": files}
        for h, files in phash_groups.items() if len(files) > 1
    ]
    return {
        "total": len(attachments),
        "by_kind": dict(by_kind),
        "duplicates": duplicates,
        "with_exif": sum(1 for a in attachments if a.get("exif_present")),
        "with_ocr_text": sum(1 for a in attachments if a.get("ocr_text")),
        "needs_manual_review": sum(1 for a in attachments if a.get("needs_manual_review")),
    }
