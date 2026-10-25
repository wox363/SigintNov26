"""Cross-Case Comparison Engine.

Extracts entity indices from each case's stored analysis and finds:
  - Phone numbers shared across cases (contacts)
  - IMEIs shared across cases
  - IMSIs shared across cases
  - Destination IPs / platforms shared across cases
  - Subject-name alias matches (fuzzy)

Pure rule-based, offline. Reuses already-stored analysis data — no re-analysis.
"""
from collections import defaultdict
from difflib import SequenceMatcher
import logging
import re

logger = logging.getLogger(__name__)

# Fuzzy match threshold for subject-name aliasing (0..1)
ALIAS_SIMILARITY_THRESHOLD = 0.72
# Minimum length for a subject name to be considered for fuzzy comparison
ALIAS_MIN_NAME_LENGTH = 3


def _normalize_phone(num):
    if not num:
        return None
    s = re.sub(r"\D", "", str(num))
    # Strip leading 91 (India country code) if present + length is 12
    if len(s) == 12 and s.startswith("91"):
        s = s[2:]
    if len(s) < 7:
        return None
    return s


def _normalize_imei(v):
    if not v:
        return None
    s = re.sub(r"\D", "", str(v))
    return s if len(s) >= 14 else None


def _normalize_imsi(v):
    if not v:
        return None
    s = re.sub(r"\D", "", str(v))
    return s if len(s) >= 14 else None


def _normalize_ip(v):
    if not v:
        return None
    s = str(v).strip()
    # Drop port if appended
    s = s.split(":")[0]
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", s):
        return s
    # IPv6 — accept as is
    if ":" in s and len(s) >= 4:
        return s
    return None


def _normalize_name(name):
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def extract_case_entities(case, analysis_data):
    """From one case's stored analysis output, produce a flat entity index:
       { 'phones': {phone: [subjects]}, 'imeis': {...}, 'imsis': {...}, 'ips': {...},
         'subjects': [names], 'case_id', 'case_name' }
    """
    entities = {
        "case_id": case["id"],
        "case_name": case.get("name", "Unknown case"),
        "phones": defaultdict(set),
        "imeis": defaultdict(set),
        "imsis": defaultdict(set),
        "ips": defaultdict(set),
        "subjects": [],
    }

    # Subjects of the case
    for s in case.get("subjects", []):
        if s.get("name"):
            entities["subjects"].append(s["name"])
            # Subject's own phone is a phone "of interest" too
            ph = _normalize_phone(s.get("phone"))
            if ph:
                entities["phones"][ph].add(s["name"])
            imei = _normalize_imei(s.get("imei"))
            if imei:
                entities["imeis"][imei].add(s["name"])

    # Pull contacts/phones from common_contacts.subject_contact_counts is just counts,
    # so we use pairwise_common.numbers + every subject's contact pool (stored in analysis)
    cc = (analysis_data or {}).get("common_contacts", {})
    # Numbers visible in pairwise pairs
    for pair_str, info in cc.get("pairwise_common", {}).items():
        for num in info.get("numbers", []):
            ph = _normalize_phone(num)
            if ph:
                # Attribute to both subjects in the pair
                for sub in pair_str.split(" <-> "):
                    entities["phones"][ph].add(sub.strip())
    for num in cc.get("common_across_all", []):
        ph = _normalize_phone(num)
        if ph:
            for sub in entities["subjects"]:
                entities["phones"][ph].add(sub)

    # Also pick up ALL contacts seen — but the analysis output keeps only
    # aggregate counts (privacy + size). We additionally inspect the
    # `priority_leads` list and `interrogation_questions` which embed numbers
    # in their value/text fields, plus relationship graph contact nodes.
    for lead in (analysis_data or {}).get("priority_leads", []):
        val = lead.get("value")
        ph = _normalize_phone(val)
        if ph:
            for s in lead.get("subjects", []):
                entities["phones"][ph].add(s)

    # Relationship graph contact nodes (their label is the full phone)
    rg = (analysis_data or {}).get("relationship_graph", {})
    contact_nodes = {n["id"]: n.get("label") for n in rg.get("nodes", []) if n.get("type") == "contact"}
    for link in rg.get("links", []):
        if link.get("type") == "contact":
            label = contact_nodes.get(link.get("target"))
            ph = _normalize_phone(label)
            if ph:
                entities["phones"][ph].add(link.get("source"))

    # IMEIs from imei_analysis
    imei_an = (analysis_data or {}).get("imei_analysis", {})
    for subject, imeis in imei_an.get("subject_imeis", {}).items():
        for imei in imeis.keys():
            n = _normalize_imei(imei)
            if n:
                entities["imeis"][n].add(subject)

    # IMSIs from sim_analysis
    sim_an = (analysis_data or {}).get("sim_analysis", {})
    for subject, info in sim_an.get("per_subject", {}).items():
        for entry in info.get("imsis", []):
            n = _normalize_imsi(entry.get("imsi"))
            if n:
                entities["imsis"][n].add(subject)

    # Destination IPs from funding_correlation samples + relationship/file_transfer
    funding = (analysis_data or {}).get("funding_correlation", {})
    for subject, activity in funding.get("subject_activity", {}).items():
        for hit in activity:
            ip = _normalize_ip(hit.get("ip"))
            if ip:
                entities["ips"][ip].add(subject)

    ft = (analysis_data or {}).get("file_transfer", {})
    for subject, activity in ft.get("subject_activity", {}).items():
        for hit in activity:
            ip = _normalize_ip(hit.get("ip"))
            if ip:
                entities["ips"][ip].add(subject)

    # Convert sets to sorted lists for JSON serialization
    for key in ("phones", "imeis", "imsis", "ips"):
        entities[key] = {k: sorted(v) for k, v in entities[key].items()}

    return entities


async def extract_evidence_ips(case_id, db):
    """Augment IP entity index by pulling from the dedicated evidence collection
    which stores per-platform IP audit trails. Returns {ip: set(subjects)}."""
    ip_to_subjects = defaultdict(set)
    cursor = db.evidence.find({"case_id": case_id}, {"_id": 0, "subject": 1, "ips": 1})
    async for doc in cursor:
        subject = doc.get("subject")
        for ip in doc.get("ips", []) or []:
            n = _normalize_ip(ip)
            if n and subject:
                ip_to_subjects[n].add(subject)
    return {ip: sorted(v) for ip, v in ip_to_subjects.items()}


def find_alias_matches(case_entities_list):
    """Detect subject name aliases across cases using fuzzy matching.
    Returns list of {name1, case1, name2, case2, similarity} for pairs that
    look like the same person under different spellings."""
    # Build (case_id, case_name, subject_name) tuples for every subject
    rows = []
    for ce in case_entities_list:
        for s in ce["subjects"]:
            if len(s) >= ALIAS_MIN_NAME_LENGTH:
                rows.append((ce["case_id"], ce["case_name"], s, _normalize_name(s)))

    aliases = []
    seen = set()  # dedupe
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            c1, cn1, n1, norm1 = rows[i]
            c2, cn2, n2, norm2 = rows[j]
            if c1 == c2:
                continue  # same case, skip
            if not norm1 or not norm2:
                continue
            # Quick exact normalized match
            if norm1 == norm2:
                sim = 1.0
            else:
                sim = SequenceMatcher(None, norm1, norm2).ratio()
                if sim < ALIAS_SIMILARITY_THRESHOLD:
                    continue
            key = tuple(sorted([(c1, n1), (c2, n2)]))
            if key in seen:
                continue
            seen.add(key)
            aliases.append({
                "name1": n1, "case1_id": c1, "case1_name": cn1,
                "name2": n2, "case2_id": c2, "case2_name": cn2,
                "similarity": round(sim, 3),
                "match_strength": "EXACT" if sim >= 0.99 else "STRONG" if sim >= 0.85 else "POSSIBLE",
            })
    aliases.sort(key=lambda x: x["similarity"], reverse=True)
    return aliases


def correlate_entity(entity_type, case_entities_list):
    """Find an entity (phone/imei/imsi/ip) that appears across multiple cases.
    Returns list of {value, occurrences: [{case_id, case_name, subjects}], case_count}."""
    # entity_value -> list of (case_id, case_name, [subjects])
    entity_map = defaultdict(list)
    for ce in case_entities_list:
        entries = ce.get(entity_type, {})
        for value, subjects in entries.items():
            entity_map[value].append({
                "case_id": ce["case_id"],
                "case_name": ce["case_name"],
                "subjects": list(subjects),
            })

    shared = []
    for value, occurrences in entity_map.items():
        if len(occurrences) >= 2:
            shared.append({
                "value": value,
                "case_count": len(occurrences),
                "occurrences": occurrences,
            })
    # Sort by reach (most cases first, then alphabetical)
    shared.sort(key=lambda x: (-x["case_count"], x["value"]))
    return shared


async def compare_cases(case_ids, db):
    """Top-level orchestration. Pulls each case + its analysis, extracts entity
    indices, finds shared entities, and identifies subject-name aliases.
    Returns the full comparison payload."""
    case_entities_list = []
    case_metadata = []
    missing = []
    for cid in case_ids:
        case = await db.cases.find_one({"id": cid}, {"_id": 0})
        if not case:
            missing.append({"case_id": cid, "reason": "Case not found"})
            continue
        analysis = await db.analyses.find_one({"case_id": cid}, {"_id": 0})
        if not analysis:
            missing.append({"case_id": cid, "case_name": case.get("name"), "reason": "No analysis run yet"})
            continue
        data = analysis.get("data", {})
        entities = extract_case_entities(case, data)
        # Augment IPs via evidence collection
        evidence_ips = await extract_evidence_ips(cid, db)
        for ip, subs in evidence_ips.items():
            existing = set(entities["ips"].get(ip, []))
            existing.update(subs)
            entities["ips"][ip] = sorted(existing)
        case_entities_list.append(entities)

        risk = data.get("risk_scores", {})
        high_risk = [s for s, r in risk.items() if r.get("level") in ("HIGH", "CRITICAL")]
        case_metadata.append({
            "case_id": cid,
            "case_name": case.get("name"),
            "description": case.get("description"),
            "subject_count": len(entities["subjects"]),
            "subjects": entities["subjects"],
            "high_risk_subjects": high_risk,
            "total_phones": len(entities["phones"]),
            "total_imeis": len(entities["imeis"]),
            "total_imsis": len(entities["imsis"]),
            "total_ips": len(entities["ips"]),
        })

    if len(case_entities_list) < 2:
        return {
            "case_metadata": case_metadata,
            "missing": missing,
            "shared_phones": [],
            "shared_imeis": [],
            "shared_imsis": [],
            "shared_ips": [],
            "aliases": [],
            "summary": {
                "case_count": len(case_entities_list),
                "shared_phones_count": 0,
                "shared_imeis_count": 0,
                "shared_imsis_count": 0,
                "shared_ips_count": 0,
                "aliases_count": 0,
                "error": "Need at least 2 analyzed cases to compare",
            },
        }

    shared_phones = correlate_entity("phones", case_entities_list)
    shared_imeis = correlate_entity("imeis", case_entities_list)
    shared_imsis = correlate_entity("imsis", case_entities_list)
    shared_ips = correlate_entity("ips", case_entities_list)
    aliases = find_alias_matches(case_entities_list)

    # Top inferences for the exec summary
    key_findings = []
    if shared_phones:
        key_findings.append(
            f"{len(shared_phones)} phone number(s) appear across multiple cases — "
            f"top: {shared_phones[0]['value']} in {shared_phones[0]['case_count']} cases"
        )
    if shared_imeis:
        key_findings.append(
            f"{len(shared_imeis)} IMEI(s) shared across cases — same physical device(s) in unrelated investigations"
        )
    if shared_imsis:
        key_findings.append(
            f"{len(shared_imsis)} IMSI(s) shared across cases — same SIM in multiple investigations"
        )
    if shared_ips:
        key_findings.append(
            f"{len(shared_ips)} destination IP(s) shared — same network endpoint contacted by separate groups"
        )
    if aliases:
        exact = sum(1 for a in aliases if a["match_strength"] == "EXACT")
        key_findings.append(
            f"{len(aliases)} subject-name alias match(es) detected ({exact} exact, "
            f"{len(aliases) - exact} fuzzy) — possible repeat suspects across cases"
        )
    if not key_findings:
        key_findings.append("No cross-case entity overlaps detected in the selected cases.")

    return {
        "case_metadata": case_metadata,
        "missing": missing,
        "shared_phones": shared_phones,
        "shared_imeis": shared_imeis,
        "shared_imsis": shared_imsis,
        "shared_ips": shared_ips,
        "aliases": aliases,
        "summary": {
            "case_count": len(case_entities_list),
            "shared_phones_count": len(shared_phones),
            "shared_imeis_count": len(shared_imeis),
            "shared_imsis_count": len(shared_imsis),
            "shared_ips_count": len(shared_ips),
            "aliases_count": len(aliases),
            "key_findings": key_findings,
        },
    }
