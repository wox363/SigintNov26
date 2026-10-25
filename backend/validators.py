import re
import logging

logger = logging.getLogger(__name__)


def validate_records(records, data_type):
    """Validate parsed records and return a data quality report.
    Flags invalid phone numbers, dates, durations, and IPs."""
    issues = []
    valid_count = 0
    invalid_count = 0
    field_stats = {}

    for i, rec in enumerate(records):
        record_issues = []

        if data_type == "cdr":
            for field in ["calling_number", "called_number"]:
                val = rec.get(field)
                if val and not re.match(r'^\d{7,15}$', str(val).strip()):
                    record_issues.append(f"{field} invalid: '{val}'")
                if val:
                    field_stats[field] = field_stats.get(field, 0) + 1

            dt = rec.get("date")
            if dt and not re.match(r'\d{1,2}/\d{1,2}/\d{4}', str(dt)):
                record_issues.append(f"date format invalid: '{dt}'")
            if dt:
                field_stats["date"] = field_stats.get("date", 0) + 1

            dur = rec.get("duration")
            if dur:
                try:
                    d = int(dur)
                    if d < 0:
                        record_issues.append(f"negative duration: {dur}")
                except (ValueError, TypeError):
                    record_issues.append(f"non-numeric duration: '{dur}'")
                field_stats["duration"] = field_stats.get("duration", 0) + 1

        elif data_type == "ipdr":
            ip = rec.get("destination_ip") or rec.get("source_ip")
            if ip and not re.match(r'^[\da-fA-F.:]+$', str(ip).strip()):
                record_issues.append(f"invalid IP: '{ip}'")
            if ip:
                field_stats["ip"] = field_stats.get("ip", 0) + 1

            for field in ["start_date", "end_date", "date"]:
                val = rec.get(field)
                if val and str(val).strip():
                    field_stats[field] = field_stats.get(field, 0) + 1

        if record_issues:
            invalid_count += 1
            if len(issues) < 30:
                issues.append({"record": i + 1, "issues": record_issues})
        else:
            valid_count += 1

    total = len(records)
    return {
        "total_records": total,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "quality_score": round(valid_count / max(total, 1) * 100, 1),
        "field_coverage": {k: round(v / max(total, 1) * 100, 1) for k, v in field_stats.items()},
        "sample_issues": issues,
    }
