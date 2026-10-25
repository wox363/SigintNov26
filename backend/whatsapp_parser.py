"""WhatsApp Export Parser — Phase 1 (Investigative triage only).

Handles WhatsApp "Email chat" export ZIPs and raw .txt chat files. Extracts:
  - messages (timestamp, sender, body, kind, attachment ref)
  - participants
  - attachment metadata (filename, size, sha256, perceptual hash for images,
    EXIF where present, OCR text for images)
  - voice notes: identified, flagged for manual review (no transcription in Phase 1)
  - deleted-message MARKERS (content unrecoverable from a ZIP export)

What this parser explicitly does NOT do (per Phase 1 contract):
  - Translation
  - Language detection
  - Voice transcription
  - Image tampering verdicts
  - Intent/sentiment classification
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Format regexes
# ---------------------------------------------------------------------------
# Examples this matches:
#   05/03/25, 2:32 pm - Imtiaz: Hello world
#   05/03/25, 2:32 PM - +91 98765 43210: Multi line body
#   12/04/26, 14:30 - System message text (no sender colon)
#   1/3/25, 9:09 - Imtiaz: foo
_MSG_RE = re.compile(
    r"""
    ^
    (?P<date>\d{1,2}/\d{1,2}/\d{2,4})    # date  e.g. 05/03/25
    ,\s+
    (?P<time>\d{1,2}:\d{2}(?::\d{2})?)    # time  e.g. 2:32 or 14:30:15
    \s*(?P<ampm>[apAP][mM])?              # am/pm optional (24h export has none)
    \s+[-–]\s+                            # - separator (or em-dash)
    (?P<rest>.*)$                         # rest = sender: body  OR  system text
    """,
    re.VERBOSE,
)
# Once we have `rest`, decide if it's "Sender: body" or a system line.
# System lines have NO colon between participant-name and body, or start with
# known telltale phrases.
_SYSTEM_PHRASES = (
    "Messages and calls are end-to-end encrypted",
    "is a contact",
    "added",
    "left",
    "removed",
    "created group",
    "changed the subject",
    "changed this group's icon",
    "changed their phone number",
    "joined using this group's invite link",
    "You're now an admin",
)
_DELETED_MARKERS = (
    "This message was deleted",
    "You deleted this message",
    "Missed voice call",
    "Missed video call",
)
_MEDIA_OMITTED_RE = re.compile(r"<Media omitted>|<attached:\s*(?P<filename>.+?)>",
                               re.IGNORECASE)

# ---------------------------------------------------------------------------
# Date parsing — WhatsApp uses many locale variants
# ---------------------------------------------------------------------------
_DATE_FORMATS_DDMM = ["%d/%m/%y", "%d/%m/%Y"]
_DATE_FORMATS_MMDD = ["%m/%d/%y", "%m/%d/%Y"]


def _parse_datetime(date_str: str, time_str: str, ampm: Optional[str],
                    prefer_ddmm: bool = True) -> Optional[datetime]:
    """Parse WhatsApp date+time into a UTC datetime. Returns None on failure.

    `prefer_ddmm`: most non-US locales (incl. India) use DD/MM. WhatsApp does
    not embed the locale in the export, so we default to DD/MM and only fall
    back to MM/DD if DD/MM fails.
    """
    fmt_order = _DATE_FORMATS_DDMM + _DATE_FORMATS_MMDD if prefer_ddmm \
        else _DATE_FORMATS_MMDD + _DATE_FORMATS_DDMM

    # Normalise time string
    t = time_str.strip()
    if ampm:
        t = f"{t} {ampm.upper()}"
        time_fmt = "%I:%M %p" if ":" in t and len(t.split(":")) == 2 else "%I:%M:%S %p"
    else:
        time_fmt = "%H:%M:%S" if t.count(":") == 2 else "%H:%M"

    for fmt in fmt_order:
        for tf in [time_fmt, "%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"]:
            try:
                dt = datetime.strptime(f"{date_str} {t}", f"{fmt} {tf}")
                # WhatsApp exports are local time. We do not have the source
                # timezone — store as naive then re-stamp as UTC to keep ISO
                # ordering consistent across the system. Callers needing the
                # ORIGINAL local time can read `local_time_str` from the message.
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Message:
    line_no: int                    # 1-based position in source .txt
    timestamp: Optional[str]        # ISO string, UTC-stamped
    local_time_str: str             # original "DD/MM/YY HH:MM ampm" as seen
    sender: Optional[str]           # None for system messages
    body: str
    kind: str                       # "text" | "media" | "deleted" | "system" | "call"
    attachment_filename: Optional[str] = None
    # Cross-correlation hooks (populated by engine, not parser)
    detected_phones: list = field(default_factory=list)
    detected_emails: list = field(default_factory=list)
    detected_urls: list = field(default_factory=list)


@dataclass
class Attachment:
    filename: str
    size_bytes: int
    sha256: str
    mime_hint: str                  # 'image' | 'audio' | 'video' | 'document' | 'other'
    perceptual_hash: Optional[str] = None  # only for images
    exif_present: bool = False
    exif: dict = field(default_factory=dict)
    ocr_text: Optional[str] = None
    needs_manual_review: bool = False
    review_reason: Optional[str] = None


@dataclass
class ParsedExport:
    messages: list[Message]
    participants: list[str]
    attachments: list[Attachment]
    parse_warnings: list[str]
    chat_filename: Optional[str]
    total_lines: int
    unparseable_lines: int


# ---------------------------------------------------------------------------
# Chat .txt parser
# ---------------------------------------------------------------------------
def _classify_rest(rest: str) -> tuple[str, Optional[str], str, Optional[str]]:
    """From the post-timestamp content of a line, return:
       (kind, sender, body, attachment_filename)
    """
    # System-message phrases (no sender:)
    for phrase in _SYSTEM_PHRASES:
        if phrase.lower() in rest.lower():
            return ("system", None, rest.strip(), None)

    # Find the FIRST colon — it separates sender from body. But contact names
    # can themselves contain colons rarely; we accept "sender" as everything
    # before the first ': '.
    m = re.match(r"^([^:]{1,80}):\s?(.*)$", rest, re.DOTALL)
    if not m:
        return ("system", None, rest.strip(), None)
    sender = m.group(1).strip()
    body = m.group(2).strip()

    # Deletion markers
    for d in _DELETED_MARKERS:
        if d.lower() in body.lower():
            kind = "call" if "call" in d.lower() else "deleted"
            return (kind, sender, body, None)

    # Media references
    media_match = _MEDIA_OMITTED_RE.search(body)
    if media_match:
        att = media_match.group("filename") if media_match.groupdict().get("filename") else None
        return ("media", sender, body, att)

    # Empty body — WhatsApp blanks out media on some exports
    if not body:
        return ("media", sender, "", None)

    return ("text", sender, body, None)


def parse_chat_text(text: str) -> tuple[list[Message], list[str], list[str]]:
    """Parse a WhatsApp chat .txt body. Returns (messages, participants, warnings)."""
    messages: list[Message] = []
    warnings: list[str] = []
    participants: set[str] = set()

    current: Optional[Message] = None
    unparseable_count = 0
    total = 0

    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r")
        if not line.strip():
            # Blank line — most likely a paragraph break inside the previous
            # message. Preserve it.
            if current is not None:
                current.body += "\n"
            continue
        total += 1
        m = _MSG_RE.match(line)
        if not m:
            # Continuation of the previous message
            if current is not None:
                current.body += "\n" + line
            else:
                unparseable_count += 1
            continue

        # Close out previous
        if current is not None:
            messages.append(current)

        date_str = m.group("date")
        time_str = m.group("time")
        ampm = m.group("ampm")
        rest = m.group("rest")
        dt = _parse_datetime(date_str, time_str, ampm)
        kind, sender, body, attachment = _classify_rest(rest)
        if sender:
            participants.add(sender)

        local_time = f"{date_str} {time_str}" + (f" {ampm.lower()}" if ampm else "")
        current = Message(
            line_no=i,
            timestamp=dt.isoformat() if dt else None,
            local_time_str=local_time,
            sender=sender,
            body=body,
            kind=kind,
            attachment_filename=attachment,
        )

    if current is not None:
        messages.append(current)

    if unparseable_count:
        warnings.append(
            f"{unparseable_count} lines could not be parsed (likely format drift). "
            "Treated as continuations of the previous message where possible."
        )
    logger.info(
        f"WhatsApp parse: {len(messages)} messages, {len(participants)} participants, "
        f"{unparseable_count} unparseable lines"
    )
    return messages, sorted(participants), warnings


# ---------------------------------------------------------------------------
# Attachment processing
# ---------------------------------------------------------------------------
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"}
_AUDIO_EXT = {".opus", ".m4a", ".ogg", ".mp3", ".aac", ".amr", ".wav"}
_VIDEO_EXT = {".mp4", ".mov", ".3gp", ".webm", ".mkv"}
_DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"}


def _mime_hint(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _DOC_EXT:
        return "document"
    return "other"


def _process_image(data: bytes, attachment: Attachment) -> None:
    """Compute perceptual hash, read EXIF, run Tesseract OCR. Mutates `attachment`.
    Best-effort — any failure logs a warning but does not abort the parse."""
    # Perceptual hash
    try:
        import imagehash
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        attachment.perceptual_hash = str(imagehash.phash(img))
    except Exception as e:
        logger.debug(f"perceptual hash failed for {attachment.filename}: {e}")

    # EXIF
    try:
        import exifread
        tags = exifread.process_file(io.BytesIO(data), details=False)
        useful_keys = [
            "Image DateTime", "EXIF DateTimeOriginal", "Image Make", "Image Model",
            "Image Software", "GPS GPSLatitude", "GPS GPSLongitude",
            "GPS GPSLatitudeRef", "GPS GPSLongitudeRef", "Image Orientation",
        ]
        exif = {k: str(v) for k, v in tags.items() if k in useful_keys}
        if exif:
            attachment.exif_present = True
            attachment.exif = exif
    except Exception as e:
        logger.debug(f"EXIF read failed for {attachment.filename}: {e}")

    # OCR — only attempt on common image formats, cap input size to avoid
    # spending forever on huge images.
    if len(data) > 8 * 1024 * 1024:
        logger.info(f"Skipping OCR on {attachment.filename}: >8MB")
        return
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        # Lowest-friction config; we don't pretend to support non-English yet
        text = pytesseract.image_to_string(img, lang="eng", timeout=15)
        text = text.strip()
        if text and len(text) > 4:
            attachment.ocr_text = text
    except Exception as e:
        logger.debug(f"OCR failed for {attachment.filename}: {e}")


# ---------------------------------------------------------------------------
# Top-level: parse a ZIP or a raw .txt
# ---------------------------------------------------------------------------
def parse_zip(zip_path: str, extract_attachments_to: Optional[str] = None) -> ParsedExport:
    """Parse a WhatsApp export ZIP. Optionally writes attachments to disk for
    later inspection. Returns ParsedExport."""
    messages: list[Message] = []
    participants: list[str] = []
    warnings: list[str] = []
    attachments: list[Attachment] = []
    chat_filename = None

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        # Find chat .txt (WhatsApp uses "WhatsApp Chat with X.txt" or "_chat.txt")
        txt_candidates = [n for n in names if n.lower().endswith(".txt")
                          and "chat" in n.lower()]
        if not txt_candidates and any(n.endswith(".txt") for n in names):
            txt_candidates = [n for n in names if n.endswith(".txt")]
        if not txt_candidates:
            warnings.append("No chat .txt file found inside ZIP — nothing to parse.")
            return ParsedExport(
                messages=[], participants=[], attachments=[],
                parse_warnings=warnings, chat_filename=None,
                total_lines=0, unparseable_lines=0,
            )

        chat_filename = txt_candidates[0]
        text = zf.read(chat_filename).decode("utf-8", errors="replace")
        messages, participants, warnings = parse_chat_text(text)
        total_lines = len(text.splitlines())
        unparseable = sum(1 for w in warnings if "could not be parsed" in w)

        # Walk attachments
        attachment_extract_dir = Path(extract_attachments_to) if extract_attachments_to else None
        if attachment_extract_dir:
            attachment_extract_dir.mkdir(parents=True, exist_ok=True)

        for name in names:
            if name == chat_filename:
                continue
            if name.endswith("/"):  # directory entry
                continue
            # Filter macOS / Windows ZIP cruft so they don't pollute the
            # attachment list. These are never genuine WhatsApp media.
            base = Path(name).name
            if (name.startswith("__MACOSX/")
                    or base in (".DS_Store", "Thumbs.db", "desktop.ini")
                    or base.startswith("._")):
                continue
            try:
                data = zf.read(name)
            except Exception as e:
                warnings.append(f"Could not read attachment {name}: {e}")
                continue
            sha = hashlib.sha256(data).hexdigest()
            mime = _mime_hint(name)
            att = Attachment(
                filename=name,
                size_bytes=len(data),
                sha256=sha,
                mime_hint=mime,
            )
            if mime == "image":
                _process_image(data, att)
            elif mime == "audio":
                # Phase 1: do NOT auto-transcribe. Flag for manual review.
                att.needs_manual_review = True
                att.review_reason = "Voice note — Phase 1 does not include offline transcription"
            elif mime == "video":
                att.needs_manual_review = True
                att.review_reason = "Video — Phase 1 does not include video analysis"

            # Persist file to disk if a target directory was requested
            if attachment_extract_dir is not None:
                out_path = attachment_extract_dir / Path(name).name
                with open(out_path, "wb") as f:
                    f.write(data)
            attachments.append(att)

    return ParsedExport(
        messages=messages,
        participants=participants,
        attachments=attachments,
        parse_warnings=warnings,
        chat_filename=chat_filename,
        total_lines=total_lines,
        unparseable_lines=unparseable,
    )


def parse_txt(txt_path: str) -> ParsedExport:
    """Parse a raw .txt chat file (no attachments)."""
    with open(txt_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    messages, participants, warnings = parse_chat_text(text)
    return ParsedExport(
        messages=messages,
        participants=participants,
        attachments=[],
        parse_warnings=warnings,
        chat_filename=Path(txt_path).name,
        total_lines=len(text.splitlines()),
        unparseable_lines=0,
    )


def to_dict(parsed: ParsedExport) -> dict:
    return {
        "chat_filename": parsed.chat_filename,
        "total_lines": parsed.total_lines,
        "unparseable_lines": parsed.unparseable_lines,
        "participants": parsed.participants,
        "messages": [asdict(m) for m in parsed.messages],
        "attachments": [asdict(a) for a in parsed.attachments],
        "parse_warnings": parsed.parse_warnings,
    }
