"""
Risk-Scoring Rubric — Appendix for AMBER reports
=================================================
Documents the EXACT rules that produce every severity tag and risk indicator
in the report, so a senior reviewer can verify each finding against its trigger.

Single source of truth. Update this file when any rule in analysis_engine.py,
compare_engine.py, or whatsapp_engine.py changes its threshold.

Public API:
    append_rubric_to_docx(doc) -> None       (mutates the python-docx Document)
    append_rubric_to_pdf(story, styles) -> None   (mutates reportlab story list)
    rubric_rows() -> list[dict]              (raw data; used by both renderers)
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# The rubric — one row per rule that emits a severity or risk tag.
# Every "trigger" string is the LITERAL rule encoded in the corresponding
# engine file. If you change the engine, change this. Reviewers will check.
# ---------------------------------------------------------------------------
_RUBRIC: list[dict] = [
    # --- CDR / IPDR : platform-category hits (analysis_engine.py) -----------
    {
        "section": "Communications & Channels (CDR / IPDR)",
        "indicator": "PAKISTAN_ISP_HIT",
        "severity": "HIGH",
        "source": "analysis_engine.process_subject → platform_hits['pakistan_isp']",
        "trigger": "Any IPDR session whose destination IP / ASN matches the Pakistan-ISP block list in platform_db.json.",
        "why_it_matters": "Direct cross-border connectivity is a strong operational signal — investigate session timing and volume.",
    },
    {
        "section": "Communications & Channels (CDR / IPDR)",
        "indicator": "CRYPTO_PLATFORM_HIT",
        "severity": "HIGH",
        "source": "analysis_engine.process_subject → platform_hits['crypto']",
        "trigger": "Any IPDR session to a known cryptocurrency exchange / wallet endpoint (Binance, Coinbase, WazirX, KuCoin, etc.).",
        "why_it_matters": "Cryptocurrency access events correlate with hawala-style value transfer.",
    },
    {
        "section": "Communications & Channels (CDR / IPDR)",
        "indicator": "FILE_TRANSFER_HIT",
        "severity": "MEDIUM",
        "source": "analysis_engine.process_subject → platform_hits['file_transfer']",
        "trigger": "Session to a large-file-sharing endpoint (SendAnywhere, WeTransfer, MEGA, Dropbox).",
        "why_it_matters": "Bulk file movement is a recurring pattern in document exfiltration and image-share networks.",
    },
    {
        "section": "Communications & Channels (CDR / IPDR)",
        "indicator": "ANONYMOUS_CHAT_HIT",
        "severity": "MEDIUM",
        "source": "analysis_engine.process_subject → platform_hits['anonymous_chat']",
        "trigger": "Session to anonymous / ephemeral chat services (Wickr, Session, Briar, Threema, Wire).",
        "why_it_matters": "Use of anonymous channels alongside mainstream apps suggests intent to evade scrutiny.",
    },
    {
        "section": "Communications & Channels (CDR / IPDR)",
        "indicator": "VPN / PROXY HIT",
        "severity": "LOW",
        "source": "analysis_engine.process_subject → platform_hits['vpn_proxy']",
        "trigger": "Session to a known VPN / proxy endpoint (NordVPN, ExpressVPN, ProtonVPN, etc.).",
        "why_it_matters": "VPN use is widespread; treated as low-severity context, escalated only when paired with other indicators.",
    },

    # --- Bulk data transfer ----------------------------------------------
    {
        "section": "Bulk Data Transfer (IPDR)",
        "indicator": "BULK_UPLOAD",
        "severity": "MEDIUM",
        "source": "analysis_engine._bulk_transfer_analysis",
        "trigger": "Single session upload volume ≥ 100 MB.",
        "why_it_matters": "Large outbound transfers in a single session warrant timeline correlation with CDR calls.",
    },
    {
        "section": "Bulk Data Transfer (IPDR)",
        "indicator": "BULK_DOWNLOAD",
        "severity": "LOW",
        "source": "analysis_engine._bulk_transfer_analysis",
        "trigger": "Single session download volume ≥ 500 MB.",
        "why_it_matters": "Common with streaming; useful only when destination is non-streaming or odd-hour.",
    },

    # --- SIM / IMSI / IMEI ------------------------------------------------
    {
        "section": "Device & Subscriber (CDR)",
        "indicator": "SIM_SWAP",
        "severity": "HIGH",
        "source": "analysis_engine._sim_analysis",
        "trigger": "Same MSISDN observed against two or more distinct IMSI values inside the case window.",
        "why_it_matters": "SIM swap timing often aligns with operational events; aliased identity risk.",
    },
    {
        "section": "Device & Subscriber (CDR)",
        "indicator": "IMEI_CHANGE",
        "severity": "MEDIUM",
        "source": "analysis_engine._sim_analysis",
        "trigger": "Same MSISDN observed against two or more distinct IMEI values.",
        "why_it_matters": "Handset switching can indicate burner-device use.",
    },

    # --- Cell co-location -------------------------------------------------
    {
        "section": "Geographical (CDR)",
        "indicator": "CELL_COLOCATION",
        "severity": "MEDIUM",
        "source": "analysis_engine._cell_colocation",
        "trigger": "Two subjects' CDR records share the same cell-id within a 60-minute window.",
        "why_it_matters": "Sub-tower co-presence is much stronger evidence of physical meeting than city-level geocoding.",
    },

    # --- WhatsApp indicators (whatsapp_engine._indicators) ----------------
    {
        "section": "WhatsApp Triage",
        "indicator": "DELETED_MARKERS",
        "severity": "LOW",
        "source": "whatsapp_engine._indicators",
        "trigger": "≥ 5 deleted-message markers AND > 5 % of all messages.",
        "why_it_matters": "Marker only — the deleted content is unrecoverable from a ZIP export. Worth a manual scan of surrounding context.",
    },
    {
        "section": "WhatsApp Triage",
        "indicator": "LONG_SILENCE",
        "severity": "LOW",
        "source": "whatsapp_engine._indicators",
        "trigger": "One or more silent periods ≥ 72 hours.",
        "why_it_matters": "Long inactivity can mark operational windows or device handover.",
    },
    {
        "section": "WhatsApp Triage",
        "indicator": "LATE_NIGHT_ACTIVITY",
        "severity": "LOW",
        "source": "whatsapp_engine._indicators",
        "trigger": "≥ 10 messages between 00:00–05:00 local time.",
        "why_it_matters": "Heavy late-night messaging is a weak operational-coordination hint.",
    },
    {
        "section": "WhatsApp Triage",
        "indicator": "SENSITIVE_PLACE",
        "severity": "MEDIUM",
        "source": "whatsapp_engine._indicators",
        "trigger": "Mention of 'Pakistan', 'Wagah', 'LoC', or 'Line of Control' in chat body or image OCR text.",
        "why_it_matters": "Direct cross-border / border-region reference surfaced by the gazetteer.",
    },
    {
        "section": "WhatsApp Triage",
        "indicator": "FINANCIAL_TALK",
        "severity": "LOW",
        "source": "whatsapp_engine._indicators",
        "trigger": "≥ 5 distinct monetary amounts (₹, Rs, INR, USD) mentioned in chat.",
        "why_it_matters": "Frequent money references may indicate procurement, settlements, or transactions.",
    },

    # --- Cross-case correlation -----------------------------------------
    {
        "section": "Cross-Case Correlation",
        "indicator": "SHARED_PHONE",
        "severity": "MEDIUM",
        "source": "compare_engine.compare_cases",
        "trigger": "Same phone number appears in two or more cases.",
        "why_it_matters": "Same individual surfacing across investigations — expand the network.",
    },
    {
        "section": "Cross-Case Correlation",
        "indicator": "SHARED_IMEI",
        "severity": "HIGH",
        "source": "compare_engine.compare_cases",
        "trigger": "Same IMEI (handset) appears in two or more cases.",
        "why_it_matters": "Same physical device across cases is much stronger than a shared number (numbers can change hands).",
    },
    {
        "section": "Cross-Case Correlation",
        "indicator": "ALIAS_MATCH",
        "severity": "MEDIUM",
        "source": "compare_engine alias detector",
        "trigger": "Name token from one case matches a contact name in another case with similarity ≥ threshold.",
        "why_it_matters": "Nickname / alias surfacing across cases — same identity, different label.",
    },
]


_PREAMBLE = (
    "How to read this report. "
    "Every finding in the preceding sections carries one of three severity tags: "
    "HIGH, MEDIUM, or LOW. These tags are NOT a composite score and are NOT machine-learned. "
    "They are the deterministic output of fixed rules executed by the AMBER rule-based engine. "
    "The table below documents the exact rule that triggers each tag. A reviewer can match any "
    "finding in this report back to its trigger row, verify the threshold, and decide independently "
    "whether the underlying signal is meaningful in case context."
)

_CAVEATS = [
    "A LOW tag does not mean unimportant — late-night messaging plus financial talk plus a "
    "sensitive-place hit, all LOW individually, together warrant immediate attention.",
    "Conversely, a HIGH tag is a signal, not a verdict. SIM-swap can occur for legitimate "
    "reasons; cryptocurrency access can be retail trading.",
    "The engine does not output a single overall case score. Compositing signals across "
    "Communications, Financial, Geographical, and Operational domains into one number would "
    "falsely conflate independent evidence types. Reviewer judgement weighs them in context.",
    "All thresholds are configurable. Current values are defaults intended for typical LEA "
    "cases; the methodology table reflects what is actually running in the build that produced "
    "this report.",
]


def rubric_rows() -> list[dict]:
    """Return the raw rubric data for callers that need it (UI, tests, exports)."""
    return list(_RUBRIC)


# ---------------------------------------------------------------------------
# DOCX renderer
# ---------------------------------------------------------------------------
def append_rubric_to_docx(doc) -> None:
    """Append the rubric appendix to a python-docx Document."""
    doc.add_page_break()
    doc.add_heading("Appendix A — Risk-Scoring Rubric (Methodology)", level=1)
    doc.add_paragraph(_PREAMBLE)

    # Group by section
    sections: dict[str, list[dict]] = {}
    for row in _RUBRIC:
        sections.setdefault(row["section"], []).append(row)

    for section, rows in sections.items():
        doc.add_heading(section, level=2)
        table = doc.add_table(rows=1, cols=3)
        table.style = "Light Grid Accent 1"
        hdr = table.rows[0].cells
        hdr[0].text = "Indicator"
        hdr[1].text = "Severity"
        hdr[2].text = "Trigger rule"
        for row in rows:
            cells = table.add_row().cells
            cells[0].text = row["indicator"]
            cells[1].text = row["severity"]
            cells[2].text = row["trigger"]

    doc.add_heading("Reviewer caveats", level=2)
    for c in _CAVEATS:
        doc.add_paragraph(c, style="List Bullet")

    doc.add_paragraph()
    doc.add_paragraph(
        "Source files: analysis_engine.py · compare_engine.py · whatsapp_engine.py · "
        "platform_db.json. This appendix is auto-generated; any change to the engine "
        "must be reflected in rubric_appendix.py."
    ).italic = True


# ---------------------------------------------------------------------------
# PDF renderer (reportlab)
# ---------------------------------------------------------------------------
def append_rubric_to_pdf(story, h1_s, h2_s, body_s, bullet_s) -> None:
    """Append the rubric appendix to a reportlab story list."""
    from reportlab.platypus import PageBreak, Table, TableStyle, Spacer, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    story.append(PageBreak())
    story.append(Paragraph("Appendix A — Risk-Scoring Rubric (Methodology)", h1_s))
    story.append(Paragraph(_PREAMBLE, body_s))
    story.append(Spacer(1, 8))

    sections: dict[str, list[dict]] = {}
    for row in _RUBRIC:
        sections.setdefault(row["section"], []).append(row)

    for section, rows in sections.items():
        story.append(Paragraph(section, h2_s))
        data = [["Indicator", "Severity", "Trigger rule"]]
        for r in rows:
            data.append([
                Paragraph(r["indicator"], body_s),
                Paragraph(r["severity"], body_s),
                Paragraph(r["trigger"], body_s),
            ])
        t = Table(data, colWidths=[1.6 * inch, 0.8 * inch, 4.5 * inch], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0047FF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#888")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F5F7FA")),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    story.append(Paragraph("Reviewer caveats", h2_s))
    for c in _CAVEATS:
        story.append(Paragraph(f"&bull; {c}", bullet_s))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<i>Source files: analysis_engine.py · compare_engine.py · whatsapp_engine.py · "
        "platform_db.json. This appendix is auto-generated.</i>",
        body_s,
    ))
