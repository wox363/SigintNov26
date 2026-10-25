import pandas as pd
import io
import logging
import re

logger = logging.getLogger(__name__)

# IPv4 / IPv6 validation pattern used to gate IPDR parse quality
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_IPV6_RE = re.compile(r"^(?=.*:)[0-9A-Fa-f:.]{3,39}$")
_DATE_RE = re.compile(r"^\d{1,2}[\s/\-][A-Za-z]{3,4}[\s/\-]\d{4}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
# Header-keyword regex — lines that contain only these words are header continuations
_HEADER_KEYWORDS = re.compile(
    r"^(?:DEST\s*IP|APP\s*NAME|LOCATION|SESSION|START\s*DATE|START\s*TIME|END\s*DATE|END\s*TIME|IPDR|S\.?\s*NO\.?)\s*$",
    re.IGNORECASE,
)


def _is_valid_ip(s):
    if not s:
        return False
    s = str(s).strip()
    return bool(_IPV4_RE.match(s) or (":" in s and _IPV6_RE.match(s)))

CDR_COLUMN_PATTERNS = {
    "calling_number": ["calling", "caller", "a_number", "a_party", "msisdn_a", "from_number", "originating", "party_a"],
    "called_number": ["called", "b_number", "b_party", "destination", "dialed", "to_number", "terminating", "party_b", "other_party", "other_number"],
    "date": ["date", "call_date", "start_date", "event_date"],
    "time": ["time", "call_time", "start_time", "event_time"],
    "datetime": ["datetime", "timestamp", "call_datetime", "start_datetime", "date_time"],
    "duration": ["duration", "call_duration", "seconds", "talk_time", "call_length"],
    "imei": ["imei", "imei_number", "device_id", "equipment_id", "handset"],
    "imsi": ["imsi", "subscriber_identity", "imsi_number"],
    "cell_id": ["cell_id", "cellid", "cgi", "ecgi", "cell_global_id", "cell_identity"],
    "lac": ["lac", "location_area_code", "tac"],
    "location": ["location", "tower", "cell_tower", "sector", "cell_site", "base_station", "address"],
    "type": ["type", "call_type", "direction", "event_type", "service_type", "call_category"],
    "network": ["network", "operator", "carrier", "service_provider"],
}

IPDR_COLUMN_PATTERNS = {
    "source_ip": ["source_ip", "src_ip", "private_ip", "nat_ip", "source", "ip_address", "user_ip", "client_ip", "subscriber_ip"],
    "destination_ip": ["destination_ip", "dest_ip", "public_ip", "remote_ip", "server_ip", "dst_ip", "target_ip", "accessed_ip"],
    "source_port": ["source_port", "src_port", "private_port", "nat_port", "client_port"],
    "destination_port": ["destination_port", "dest_port", "public_port", "remote_port", "dst_port", "server_port"],
    "start_time": ["start_time", "session_start", "access_time", "begin_time", "login_time"],
    "end_time": ["end_time", "session_end", "finish_time", "close_time", "logout_time"],
    "start_date": ["start_date", "session_date", "access_date"],
    "end_date": ["end_date", "session_end_date"],
    "datetime": ["datetime", "timestamp", "date_time", "event_time"],
    "date": ["date", "event_date"],
    "volume_up": ["upload", "ul_bytes", "volume_up", "bytes_sent", "uplink", "tx_bytes", "uploaded"],
    "volume_down": ["download", "dl_bytes", "volume_down", "bytes_received", "downlink", "rx_bytes", "downloaded"],
    "volume_total": ["volume", "total_volume", "data_volume", "bytes", "total_bytes", "data_consumed"],
    "protocol": ["protocol", "proto", "service_protocol", "app_protocol"],
    "url": ["url", "domain", "destination_url", "website", "host", "fqdn", "hostname", "web_address", "accessed_url"],
    "imei": ["imei", "imei_number", "device_id", "terminal_id"],
    "msisdn": ["msisdn", "phone", "phone_number", "mobile", "subscriber", "mobile_number", "subscriber_id"],
    "imsi": ["imsi", "subscriber_identity", "imsi_number"],
    "cell_id": ["cell_id", "cellid", "cgi", "ecgi", "cell_global_id"],
}


def map_columns(df, patterns):
    column_map = {}
    df_cols_lower = {col: col.lower().strip().replace(" ", "_").replace("-", "_") for col in df.columns}
    for target_name, pattern_list in patterns.items():
        for orig_col, normalized in df_cols_lower.items():
            for pattern in pattern_list:
                if pattern == normalized or pattern in normalized:
                    if target_name not in column_map:
                        column_map[target_name] = orig_col
                    break
            if target_name in column_map:
                break
    return column_map


def process_dataframe(df, data_type):
    patterns = CDR_COLUMN_PATTERNS if data_type == "cdr" else IPDR_COLUMN_PATTERNS
    column_map = map_columns(df, patterns)
    logger.info(f"Column mapping for {data_type}: {column_map}")
    records = []
    for _, row in df.iterrows():
        record = {}
        for target_name, orig_col in column_map.items():
            val = row.get(orig_col)
            if pd.notna(val):
                record[target_name] = str(val).strip()
            else:
                record[target_name] = None
        mapped_cols = set(column_map.values())
        for col in df.columns:
            if col not in mapped_cols:
                val = row.get(col)
                key = "raw_" + col.lower().strip().replace(" ", "_").replace("-", "_")
                record[key] = str(val).strip() if pd.notna(val) else None
        records.append(record)
    return records


def parse_csv(file_path):
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding='latin-1')
    return df


def parse_excel(file_path, password=None):
    if password:
        import msoffcrypto
        decrypted = io.BytesIO()
        with open(file_path, 'rb') as f:
            office_file = msoffcrypto.OfficeFile(f)
            office_file.load_key(password=password)
            office_file.decrypt(decrypted)
        decrypted.seek(0)
        return pd.read_excel(decrypted, engine='openpyxl')
    return pd.read_excel(file_path, engine='openpyxl')


def _extract_ipdr_via_pdfplumber(file_path, password=None):
    """Strategy 0: Use pdfplumber's table extractor for structured IPDR PDFs.
    Far more reliable than regex-on-text-extract because it preserves column boundaries.

    Returns list[dict] of records with keys: destination_ip, platform, location,
    start_date, start_time, end_date, end_time. Returns [] if no IPDR-shaped tables found.
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    records = []
    try:
        with pdfplumber.open(file_path, password=password) as pdf:
            for page in pdf.pages:
                try:
                    tables = page.extract_tables() or []
                except Exception as e:
                    logger.debug(f"pdfplumber table extract failed on page: {e}")
                    continue
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    # Look at first 3 rows for IPDR header keywords
                    header_blob = " ".join(
                        " ".join(str(c or "") for c in row) for row in table[:3]
                    ).upper()
                    if not ("DEST IP" in header_blob and ("APP NAME" in header_blob or "PLATFORM" in header_blob)):
                        continue
                    # Determine how many leading rows are header (have 'IPDR'/'DEST IP'/'SESSION')
                    header_row_count = 0
                    for ri, row in enumerate(table[:4]):
                        cells = [str(c or "").strip().upper() for c in row]
                        # If row contains any IP-looking cell, it's data
                        if any(_is_valid_ip(c) for c in cells):
                            break
                        # Otherwise it's still header
                        if any(c in ("DEST IP", "APP NAME", "LOCATION", "SESSION", "IPDR", "S.NO", "S NO")
                               or "START DATE" in c or "START TIME" in c or "END DATE" in c or "END TIME" in c
                               for c in cells):
                            header_row_count = ri + 1
                        elif all(not c for c in cells):
                            header_row_count = ri + 1
                        else:
                            break
                    if header_row_count == 0:
                        header_row_count = 2  # safe default for this LEA format
                    # Parse each data row using row-shape heuristics
                    for row in table[header_row_count:]:
                        rec = _parse_ipdr_table_row(row)
                        if rec:
                            records.append(rec)
    except Exception as e:
        logger.warning(f"pdfplumber IPDR extraction failed for {file_path}: {e}")
        return []
    return records


def _parse_ipdr_table_row(row):
    """Given a list of cells from a single IPDR table row, return a clean record
    dict or None if the row doesn't look like data. Uses content-based detection
    so column index drift doesn't break parsing."""
    if not row:
        return None
    cells = [str(c).strip() if c is not None else "" for c in row]
    # Filter out empty/None cells while preserving order
    non_empty = [c for c in cells if c and c.lower() != "none"]
    if not non_empty:
        return None
    # Locate the IP
    ip_val = None
    ip_idx = None
    for i, c in enumerate(non_empty):
        if _is_valid_ip(c):
            ip_val = c
            ip_idx = i
            break
    if not ip_val:
        return None  # No IP = not a data row
    # After the IP, find dates and times (in order)
    dates_after = []
    times_after = []
    middle_cells = []  # cells between IP and the first date
    found_first_date = False
    for c in non_empty[ip_idx + 1:]:
        if _DATE_RE.match(c):
            dates_after.append(c)
            found_first_date = True
        elif _TIME_RE.match(c):
            times_after.append(c)
        else:
            if not found_first_date:
                middle_cells.append(c)
            # ignore stray text after first date — it's wrap-over
    # middle_cells should contain: APP NAME, [LOCATION]
    platform = None
    location = None
    if middle_cells:
        platform = middle_cells[0]
        if len(middle_cells) >= 2:
            # Skip cells that look like phone numbers or IP fragments
            location = " ".join(middle_cells[1:]).strip()
    # Dates / times order: start_date, end_date / start_time, end_time
    start_date = dates_after[0] if len(dates_after) >= 1 else None
    end_date = dates_after[1] if len(dates_after) >= 2 else None
    start_time = times_after[0] if len(times_after) >= 1 else None
    end_time = times_after[1] if len(times_after) >= 2 else None

    return {
        "destination_ip": ip_val,
        "platform": platform,
        "location": location,
        "start_date": start_date,
        "start_time": start_time,
        "end_date": end_date,
        "end_time": end_time,
    }


def _validate_ipdr_quality(records, min_valid_ip_ratio=0.5):
    """Reject parses where most 'destination_ip' values aren't actually IPs.
    Returns (kept_records, dropped_count, valid_ip_ratio)."""
    if not records:
        return ([], 0, 0.0)
    valid = [r for r in records if _is_valid_ip(r.get("destination_ip"))]
    ratio = len(valid) / len(records)
    if ratio < min_valid_ip_ratio:
        logger.warning(
            f"IPDR parse quality too low: only {len(valid)}/{len(records)} "
            f"({ratio*100:.1f}%) rows have valid IPs — rejecting parse"
        )
        return ([], len(records), ratio)
    if len(valid) < len(records):
        logger.info(f"Filtered out {len(records) - len(valid)} non-IP rows from IPDR parse")
    return (valid, len(records) - len(valid), ratio)


def parse_pdf(file_path, password=None):
    from PyPDF2 import PdfReader
    reader = PdfReader(file_path)
    if reader.is_encrypted:
        if password:
            reader.decrypt(password)
        else:
            raise ValueError("PDF is encrypted. Please provide a password.")

    # Extract ALL text from every page (used by Strategies 1-4)
    full_text = ""
    for page in reader.pages:
        full_text += (page.extract_text() or "") + "\n"

    logger.info(f"PDF text extracted: {len(full_text)} chars from {len(reader.pages)} pages")

    # ----------------------------------------------------------------------
    # Strategy 0 — pdfplumber table extraction (most reliable for structured
    # LEA IPDR tables with multi-line headers). Try this FIRST whenever the
    # text contains the IPDR signature keywords.
    # ----------------------------------------------------------------------
    if re.search(r"DEST\s*IP", full_text, re.IGNORECASE) and re.search(
        r"APP\s*NAME|PLATFORM", full_text, re.IGNORECASE
    ):
        ipdr_records = _extract_ipdr_via_pdfplumber(file_path, password=password)
        if ipdr_records:
            kept, dropped, ratio = _validate_ipdr_quality(ipdr_records)
            if kept:
                logger.info(
                    f"pdfplumber IPDR extraction: {len(kept)} valid records "
                    f"(dropped {dropped} non-IP rows, ratio={ratio*100:.1f}%)"
                )
                return ("ipdr_direct", kept)

    # Strategy 1: Indian LEA IPDR report — regex on flattened text (legacy path,
    # kept as fallback for older PDFs whose tables pdfplumber can't extract).
    # Use re.DOTALL so the header sniff works across multiple lines.
    if re.search(r"DEST\s*IP.*?(?:ENCRYPTED|SOCIAL|VPN|MSG\s*APPS|FILE\s*TRANSFER|CRYPTO|OTT)",
                 full_text, re.IGNORECASE | re.DOTALL):
        ipdr_records = _extract_ipdr_records(full_text)
        if ipdr_records:
            kept, dropped, ratio = _validate_ipdr_quality(ipdr_records)
            if kept:
                logger.info(
                    f"Strategy 1 IPDR (regex): {len(kept)} valid records "
                    f"(dropped {dropped}, ratio={ratio*100:.1f}%)"
                )
                return ("ipdr_direct", kept)

    # Strategy 2: Indian LEA CDR report (CALL_OUT/CALL_IN/SMS_OUT/SMS_IN)
    cdr_records = _extract_cdr_detail_records(full_text)
    if cdr_records:
        logger.info(f"Extracted {len(cdr_records)} CDR detail records from PDF")
        # Inject IMEI from header metadata into each record
        imei_match = re.search(r'(?:IMEI)[^\d]*(\d{15})', full_text, re.IGNORECASE)
        if imei_match:
            header_imei = imei_match.group(1)
            for rec in cdr_records:
                if not rec.get("imei"):
                    rec["imei"] = header_imei
        # Inject IMSI from header metadata
        imsi_match = re.search(r'(?:IMSI)[^\d]*(\d{14,15})', full_text, re.IGNORECASE)
        if imsi_match:
            header_imsi = imsi_match.group(1)
            for rec in cdr_records:
                if not rec.get("imsi"):
                    rec["imsi"] = header_imsi
        return pd.DataFrame(cdr_records)

    # Strategy 3: Contact frequency summary tables (B PARTY ... TOTAL CALLS)
    summary_records = _extract_contact_summary(full_text)
    if summary_records:
        logger.info(f"Extracted {len(summary_records)} contact summary records from PDF")
        return pd.DataFrame(summary_records)

    # Strategy 4: Generic tabular parsing (tab/comma/multi-space delimited).
    # Now with multi-line header collapse + header-continuation filtering so
    # PDFs with stacked header rows (very common in LEA IPDR formats) parse correctly.
    lines = [l.strip() for l in full_text.strip().split('\n') if l.strip()]
    if len(lines) < 2:
        return pd.DataFrame()
    # Detect how many leading lines are header continuations — a line is a
    # header continuation if every token in it is a header keyword (matches
    # _HEADER_KEYWORDS) or it's all empty/None.
    header_end = 0
    for i, ln in enumerate(lines[:5]):
        tokens = [t.strip() for t in re.split(r"\s{2,}|\t", ln) if t.strip()]
        if tokens and all(_HEADER_KEYWORDS.match(t) for t in tokens):
            header_end = i + 1
        else:
            break
    if header_end == 0:
        header_end = 1  # at least the first line is the header
    # Combine header lines into one synthetic header
    header_line = " ".join(lines[:header_end])
    data_lines = lines[header_end:]

    for delimiter_fn in [
        lambda l: [p.strip() for p in l.split('\t')],
        lambda l: [p.strip() for p in l.split(',')],
        lambda l: [p.strip() for p in re.split(r'\s{2,}', l)],
    ]:
        header_parts = delimiter_fn(header_line)
        if len(header_parts) >= 3:
            data = []
            for line in data_lines:
                # Skip lines that look like header continuation fragments
                tokens = [t for t in delimiter_fn(line) if t]
                if tokens and all(_HEADER_KEYWORDS.match(t) for t in tokens):
                    continue
                parts = delimiter_fn(line)
                if len(parts) >= 2:
                    row = {}
                    for i, val in enumerate(parts):
                        col = header_parts[i] if i < len(header_parts) else f"col_{i}"
                        row[col] = val
                    data.append(row)
            if data:
                return pd.DataFrame(data)
    return pd.DataFrame()


def _extract_ipdr_records(text):
    """Extract pre-analyzed IPDR records from Indian LEA IPDR reports.
    These PDFs have sections: ENCRYPTED MSG APPS, VPN, SOCIAL MSG APPS
    with columns: DEST IP | PLATFORM | LOCATION | SESSION START/END DATE/TIME"""
    import re

    MONTH_MAP = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "SEPT": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }

    def normalize_date(d):
        parts = re.split(r'[/\s]+', d.strip())
        if len(parts) >= 3:
            day = parts[0].zfill(2)
            mon = MONTH_MAP.get(parts[1].upper(), "01")
            year = parts[-1] if len(parts[-1]) == 4 else parts[2]
            return f"{day}/{mon}/{year}"
        return d

    records = []
    # Detect current section from headers
    current_section = "unknown"

    # Pattern: IP_ADDRESS  PLATFORM_NAME  LOCATION  DD MMM YYYY  HH:MM:SS  DD MMM YYYY  HH:MM:SS
    # IP can be IPv4 (13.225.103.87) or IPv6 (2600:9000:A61F:...)
    # Preprocess: fix dates split across lines ("23 FEB\n2026" -> "23 FEB 2026")
    text = re.sub(r'(\d{1,2}\s+[A-Z]{3,4})\s*\n\s*(\d{4})', r'\1 \2', text)
    # Fix location wrapping across lines
    text = re.sub(r',\s*\n\s*([A-Z])', r', \1', text)
    # Collapse multiple whitespace to single space per line, preserve newlines
    text = re.sub(r'[^\S\n]+', ' ', text)

    ip_pattern = r'([\da-fA-F]{1,4}[.:]+[\da-fA-F.:]+)'
    date_pattern = r'(\d{1,2}\s+[A-Z]{3,4}\s+\d{4})'
    time_pattern = r'(\d{2}:\d{2}:\d{2})'

    # Full record pattern
    record_pattern = re.compile(
        ip_pattern + r'\s+'
        r'(.+?)\s+'           # Platform + Location (greedy but bounded by date)
        + date_pattern + r'\s+' + time_pattern + r'\s+'
        + date_pattern + r'\s+' + time_pattern,
    )

    # Track section type
    for line in text.split('\n'):
        line_upper = line.strip().upper()
        if 'ENCRYPTED' in line_upper and 'MSG' in line_upper:
            current_section = "messaging"
        elif 'VPN' in line_upper and 'DEST' in line_upper:
            current_section = "vpn_proxy"
        elif 'SOCIAL' in line_upper and 'MSG' in line_upper:
            current_section = "social"
        elif 'FILE' in line_upper and 'TRANSFER' in line_upper:
            current_section = "file_transfer"
        elif 'CRYPTO' in line_upper or 'FUNDING' in line_upper:
            current_section = "crypto"

    # Find all records in full text
    for match in record_pattern.finditer(text):
        ip_addr = match.group(1)
        middle = match.group(2).strip()
        start_date = match.group(3)
        start_time = match.group(4)
        end_date = match.group(5)
        end_time = match.group(6)

        # Split middle into platform name and location
        # Platform names don't contain commas, locations do
        # Also known platforms as anchors
        platform = middle
        location = ""
        # Check if there's a comma indicating location start
        comma_idx = middle.find(',')
        if comma_idx > 0:
            # Everything before the location part
            # Try to find where location starts (after platform name)
            words_before_comma = middle[:comma_idx].strip()
            # Platform names are typically 1-3 words without commas
            # Find known platform keywords
            found_platform = None
            known_platforms = [
                "SIGNAL", "SILENT PHONE", "WHATSAPP", "TELEGRAM", "WICKR",
                "NORDVPN", "EXPRESSVPN", "PROTONVPN", "SURFSHARK", "PRIVATE INTERNET ACCESS",
                "MULLVAD", "CYBERGHOST", "PSIPHON",
                "FACEBOOK MESSENGER", "FACEBOOK", "INSTAGRAM", "TWITTER", "LINKEDIN",
                "SNAPCHAT", "MASTODON", "TIKTOK", "YOUTUBE", "DISCORD", "REDDIT",
                "JUST TALK", "BIGO", "BIGO LIVE", "WHISPER", "OMEGLE",
                "SENDANYWHERE", "SEND ANYWHERE", "WETRANSFER", "DROPBOX", "MEGA",
                "KUCOIN", "BINANCE", "COINBASE", "WAZIRX",
                "GOOGLE PAY", "PHONEPE", "PAYTM",
                "TWITCH", "ICQ NEW", "THREEMA", "WIRE", "SESSION", "BRIAR",
            ]
            middle_upper = middle.upper()
            for kp in sorted(known_platforms, key=len, reverse=True):
                if middle_upper.startswith(kp):
                    found_platform = middle[:len(kp)].strip()
                    location = middle[len(kp):].strip().lstrip(',').strip()
                    break
            if not found_platform:
                # Heuristic: platform is text before first comma/location
                parts = re.split(r'\s{2,}', middle, maxsplit=1)
                if len(parts) >= 2:
                    platform = parts[0].strip()
                    location = parts[1].strip()
                else:
                    platform = words_before_comma
                    location = middle[comma_idx + 1:].strip()
            else:
                platform = found_platform
        else:
            # No comma - might be just platform name or split oddly
            parts = re.split(r'\s{2,}', middle, maxsplit=1)
            if len(parts) >= 2:
                platform = parts[0].strip()
                location = parts[1].strip()

        records.append({
            "destination_ip": ip_addr,
            "url": platform.lower().replace(" ", "_"),
            "source_ip": "",
            "start_date": normalize_date(start_date),
            "start_time": start_time,
            "end_date": normalize_date(end_date),
            "end_time": end_time,
            "location": location,
            "raw_platform": platform,
        })

    return records


def _extract_cdr_detail_records(text):
    """Extract detailed CDR records from Indian LEA formatted CDR analysis PDFs.
    Handles format: CDR_NO  B_PARTY  NAME  FATHER_NAME  ADDRESS  DATE  HH:MM:SS  DUR  CALL_TYPE
    Supports date formats: DD/MMM/YYYY and DD MMM YYYY (with variable spaces)"""
    import re

    # Quick check: does this text contain CDR record markers?
    if not re.search(r'CALL_(?:OUT|IN)|SMS_(?:OUT|IN)', text):
        return []

    # Preprocess: fix phone numbers broken by spaces (e.g. "968236 0226" -> "9682360226")
    text = re.sub(
        r'(\d{4,7})\s(\d{3,7})',
        lambda m: m.group(1) + m.group(2) if 10 <= len(m.group(1) + m.group(2)) <= 13 else m.group(0),
        text
    )

    records = []
    month_map = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "SEPT": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }

    # Pattern supports date formats:
    #   DD/MMM/YYYY   (e.g. 27/FEB/2026)
    #   DD/MMMM/YYYY  (e.g. 20/SEPT/2025 — 4-letter month)
    #   DD MMM  YYYY  (e.g. 20 NOV  2025)
    #   DD MMMM YYYY  (e.g. 20 SEPT 2025)
    pattern = re.compile(
        r'(\d{10,13})\s+'                                  # CDR NO
        r'(\d{7,15})\s+'                                    # B PARTY
        r'([\s\S]*?)'                                       # NAME + FATHER + ADDRESS (lazy)
        r'(\d{1,2}[/\s]+[A-Z]{3,4}[/\s]+\d{4})\s+'        # DATE (all formats incl 4-letter months)
        r'(\d{2}:\d{2}:\d{2})\s+'                          # TIME
        r'(\d+)\s*'                                         # DURATION (allow trailing space/newline)
        r'(CALL_(?:OUT|IN)|SMS_(?:OUT|IN))',                 # CALL TYPE
    )

    for match in pattern.finditer(text):
        calling = match.group(1)
        called = match.group(2)
        middle = match.group(3).strip()
        date_raw = match.group(4).strip()
        time_str = match.group(5)
        duration = match.group(6)
        call_type = match.group(7)

        # Extract contact name
        name_parts = re.split(r'\s{2,}', middle.replace('\n', ' ').strip())
        name = name_parts[0].strip() if name_parts else ""

        # Normalize date to DD/MM/YYYY
        # Handle both "27/FEB/2026" and "20 NOV  2025"
        try:
            parts = re.split(r'[/\s]+', date_raw.strip())
            if len(parts) >= 3:
                day = parts[0].zfill(2)
                mon = parts[1].upper()
                year = parts[2] if len(parts[2]) == 4 else parts[-1]
                month_num = month_map.get(mon, "01")
                norm_date = f"{day}/{month_num}/{year}"
            else:
                norm_date = date_raw
        except Exception:
            norm_date = date_raw

        direction = "Outgoing" if "OUT" in call_type else "Incoming"
        is_sms = "SMS" in call_type

        records.append({
            "calling_number": calling,
            "called_number": called,
            "date": norm_date,
            "time": time_str,
            "duration": duration,
            "type": "SMS" if is_sms else direction,
        })

    return records


def _extract_contact_summary(text):
    """Extract contact frequency summary tables from CDR analysis PDFs.
    Handles format: B_PARTY  NAME  FATHER_NAME  ADDRESS  TOTAL_CALLS  TOTAL_SMS"""
    import re

    # Check if text has summary table markers
    if "TOTAL" not in text:
        return []

    records = []

    # Find blocks that look like contact frequency rows:
    # 10-digit phone + text + number(s) at end of logical line
    # We use a pattern that matches a phone number at the start, then captures text, then 1-2 numbers at the end
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Match a line starting with a 10+ digit number
        match = re.match(r'^(\d{10,13})\s+(.+)', line)
        if match:
            phone = match.group(1)
            rest = match.group(2)
            # Accumulate wrapped lines until we find the next phone number or a line ending in numbers
            while i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^(\d{10,13})\s+', next_line) or not next_line:
                    break
                if re.match(r'^[A-Z]', next_line) or re.match(r'^CDR NO', next_line) or re.match(r'^B PARTY', next_line):
                    break
                rest += " " + next_line
                i += 1
            # Try to extract trailing numbers (total_calls, total_sms)
            end_match = re.search(r'(\d+)\s+(\d+|-)\s*$', rest)
            if end_match:
                total_calls = end_match.group(1)
                total_sms = end_match.group(2).replace("-", "0")
                name_text = rest[:end_match.start()].strip()
                name_parts = re.split(r'\s{2,}', name_text)
                name = name_parts[0].strip() if name_parts else ""
                records.append({
                    "called_number": phone,
                    "calling_number": phone,
                    "date": "",
                    "time": "",
                    "duration": total_calls,
                    "type": "Summary",
                })
        i += 1

    return records


def parse_image(file_path):
    """Extract tabular text from image using Tesseract OCR with preprocessing."""
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    import re

    logger.info(f"Running OCR on image: {file_path}")
    img = Image.open(file_path)

    # --- Pre-processing pipeline for better OCR accuracy ---

    # 1. Convert to grayscale
    img = img.convert('L')

    # 2. Upscale small images (Tesseract works best at 300+ DPI)
    w, h = img.size
    if w < 1500 or h < 1000:
        scale = max(1500 / w, 1000 / h, 2.0)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        logger.info(f"Upscaled image from {w}x{h} to {img.size[0]}x{img.size[1]}")

    # 3. Denoise with median filter (removes salt-and-pepper noise)
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # 4. Enhance contrast
    img = ImageEnhance.Contrast(img).enhance(2.0)

    # 5. Enhance sharpness
    img = ImageEnhance.Sharpness(img).enhance(2.0)

    # 6. Binarize (adaptive threshold via Pillow)
    img = img.point(lambda x: 0 if x < 140 else 255, '1')
    img = img.convert('L')  # back to grayscale for Tesseract

    # 7. Deskew using Tesseract OSD (orientation & script detection)
    try:
        osd = pytesseract.image_to_osd(img)
        angle_match = re.search(r'Rotate:\s*(\d+)', osd)
        if angle_match:
            angle = int(angle_match.group(1))
            if angle != 0 and angle != 360:
                img = img.rotate(-angle, expand=True, fillcolor=255)
                logger.info(f"Deskewed image by {angle} degrees")
    except Exception as e:
        logger.warning(f"OSD deskew skipped: {e}")

    # 8. Invert if background is dark (white text on dark bg)
    hist = img.histogram()
    dark_pixels = sum(hist[:128])
    light_pixels = sum(hist[128:])
    if dark_pixels > light_pixels:
        img = ImageOps.invert(img)
        logger.info("Inverted dark-background image")

    # --- Run OCR with tuned config ---
    custom_config = r'--oem 3 --psm 6'  # PSM 6 = assume uniform block of text
    text = pytesseract.image_to_string(img, config=custom_config)
    logger.info(f"OCR extracted {len(text)} characters")

    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if len(lines) < 2:
        raise ValueError("OCR could not extract enough readable text from the image. Ensure the image contains tabular CDR/IPDR data.")

    # Try common delimiters: tab, pipe, comma, multi-space
    for delimiter_fn in [
        lambda l: [p.strip() for p in l.split('\t') if p.strip()],
        lambda l: [p.strip() for p in l.split('|') if p.strip()],
        lambda l: [p.strip() for p in l.split(',') if p.strip()],
        lambda l: [p.strip() for p in re.split(r'\s{2,}', l) if p.strip()],
    ]:
        header_parts = delimiter_fn(lines[0])
        if len(header_parts) >= 2:
            data = []
            for line in lines[1:]:
                parts = delimiter_fn(line)
                if len(parts) >= 2:
                    row = {}
                    for i, val in enumerate(parts):
                        col = header_parts[i] if i < len(header_parts) else f"col_{i}"
                        row[col] = val
                    data.append(row)
            if data:
                logger.info(f"OCR parsed {len(data)} rows with {len(header_parts)} columns")
                return pd.DataFrame(data)

    # Fallback: return each line as a single-column record
    logger.warning("OCR could not detect table structure, returning raw lines")
    return pd.DataFrame([{"raw_text": line} for line in lines])


def extract_pdf_metadata(file_path, password=None):
    """Extract subject metadata (IMEI, phone, address, name) from CDR/IPDR PDF headers."""
    from PyPDF2 import PdfReader
    import re
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted and password:
            reader.decrypt(password)
        # Only check first 3 pages for metadata
        text = ""
        for page in reader.pages[:3]:
            text += (page.extract_text() or "") + "\n"
        metadata = {}
        # Extract mobile number: "XXXXXXXXXX :- Name" format first, then "MOB NO" format
        mob_match = re.search(r'(\d{10,13})\s*[:]+\s*[-]', text)
        if not mob_match:
            mob_match = re.search(r'MOB\s*NO\s*(\d{10,13})', text, re.IGNORECASE)
        if mob_match:
            metadata["phone"] = mob_match.group(1)
        # Extract IMEI (15 digits)
        imei_match = re.search(r'(?:IMEI)[^\d]*(\d{15})', text, re.IGNORECASE)
        if imei_match:
            metadata["imei"] = imei_match.group(1)
        # Extract address (R/o line)
        addr_match = re.search(r'R/o[:\s,]*(.+?)(?:\n|$)', text)
        if addr_match:
            metadata["location"] = addr_match.group(1).strip().rstrip('.')
        return metadata
    except Exception as e:
        logger.warning(f"Metadata extraction failed: {e}")
        return {}


def parse_file(file_path, file_ext, data_type, password=None):
    logger.info(f"Parsing {file_path} (ext={file_ext}, type={data_type})")
    if file_ext in ['.csv']:
        df = parse_csv(file_path)
    elif file_ext in ['.xlsx', '.xls']:
        df = parse_excel(file_path, password)
    elif file_ext in ['.pdf']:
        result = parse_pdf(file_path, password)
        # IPDR PDFs return pre-parsed records directly
        if isinstance(result, tuple) and result[0] == "ipdr_direct":
            return result[1]
        df = result
    elif file_ext in ['.png', '.jpg', '.jpeg']:
        df = parse_image(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_ext}")
    if df is None or (hasattr(df, 'empty') and df.empty):
        return []
    return process_dataframe(df, data_type)
