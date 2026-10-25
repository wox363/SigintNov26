"""PDF + DOCX export for Cross-Case Comparison Reports."""
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from datetime import datetime, timezone
import logging

from rubric_appendix import append_rubric_to_docx, append_rubric_to_pdf

logger = logging.getLogger(__name__)

# Bounded iteration caps to keep report size reasonable
_CAP_SHARED_ENTITIES = 100
_CAP_ALIASES = 50


def generate_compare_docx(comparison, output_path):
    doc = Document()
    title = doc.add_heading("Cross-Case Comparison Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    summary = comparison.get("summary", {})
    metadata = comparison.get("case_metadata", [])

    doc.add_paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    doc.add_paragraph(f"Cases compared: {summary.get('case_count', 0)}")
    doc.add_paragraph("-" * 70)

    # Cases involved
    doc.add_heading("Cases Compared", level=1)
    for m in metadata:
        doc.add_heading(m["case_name"], level=2)
        if m.get("description"):
            doc.add_paragraph(f"Description: {m['description']}")
        doc.add_paragraph(
            f"Subjects ({m['subject_count']}): {', '.join(m['subjects']) if m['subjects'] else 'None'}"
        )
        if m.get("high_risk_subjects"):
            doc.add_paragraph(f"High-risk subjects: {', '.join(m['high_risk_subjects'])}")
        doc.add_paragraph(
            f"Entity counts — Phones: {m['total_phones']} | IMEIs: {m['total_imeis']} | "
            f"IMSIs: {m['total_imsis']} | IPs: {m['total_ips']}"
        )
    doc.add_paragraph("-" * 70)

    # Executive Summary
    doc.add_heading("Executive Summary", level=1)
    for f in summary.get("key_findings", []):
        doc.add_paragraph(f, style="List Bullet")
    doc.add_paragraph("-" * 70)

    # Shared phones
    _docx_shared(doc, "1. Shared Phone Numbers", comparison.get("shared_phones", []), "phone")

    # Shared IMEIs
    _docx_shared(doc, "2. Shared IMEIs (Device Identity)", comparison.get("shared_imeis", []), "IMEI")

    # Shared IMSIs
    _docx_shared(doc, "3. Shared IMSIs (SIM Identity)", comparison.get("shared_imsis", []), "IMSI")

    # Shared IPs
    _docx_shared(doc, "4. Shared Destination IPs", comparison.get("shared_ips", []), "IP")

    # Subject-name aliases
    doc.add_heading("5. Subject Name Alias Matches", level=1)
    aliases = comparison.get("aliases", [])
    if not aliases:
        doc.add_paragraph("No alias matches detected.")
    else:
        doc.add_paragraph(
            "Subject names from different cases that are similar enough to suggest "
            "the same individual. EXACT = normalized names identical; STRONG = high similarity; "
            "POSSIBLE = moderate similarity (review recommended)."
        )
        for a in aliases[:_CAP_ALIASES]:
            doc.add_paragraph(
                f"[{a['match_strength']}] '{a['name1']}' (case: {a['case1_name']}) "
                f"<-> '{a['name2']}' (case: {a['case2_name']}) — similarity {a['similarity']}",
                style="List Bullet",
            )
    doc.add_paragraph("-" * 70)

    # Missing data
    if comparison.get("missing"):
        doc.add_heading("Cases Excluded", level=1)
        for m in comparison["missing"]:
            doc.add_paragraph(
                f"{m.get('case_name', m['case_id'])}: {m['reason']}",
                style="List Bullet",
            )

    # Appendix A — methodology / risk-scoring rubric
    append_rubric_to_docx(doc)

    doc.save(output_path)
    logger.info(f"Cross-case DOCX saved to {output_path}")


def _docx_shared(doc, title, items, label):
    doc.add_heading(title, level=1)
    if not items:
        doc.add_paragraph(f"No shared {label}s detected across the selected cases.")
        doc.add_paragraph("-" * 70)
        return
    doc.add_paragraph(
        f"Total shared {label}s: {len(items)} — each appears in 2 or more cases. "
        "Higher case_count = stronger cross-case lead."
    )
    for item in items[:_CAP_SHARED_ENTITIES]:
        doc.add_heading(f"{label}: {item['value']}  ({item['case_count']} cases)", level=2)
        for occ in item["occurrences"]:
            doc.add_paragraph(
                f"{occ['case_name']} — subjects: {', '.join(occ['subjects']) if occ['subjects'] else '—'}",
                style="List Bullet",
            )
    doc.add_paragraph("-" * 70)


def generate_compare_pdf(comparison, output_path):
    pdf = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("T", parent=styles["Title"], fontSize=16, textColor=HexColor("#1a1a1a"), spaceAfter=12)
    h1_s = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13, textColor=HexColor("#0047FF"), spaceBefore=14, spaceAfter=6)
    h2_s = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, textColor=HexColor("#333"), spaceBefore=10, spaceAfter=4)
    body_s = ParagraphStyle("B", parent=styles["Normal"], fontSize=9, leading=13, textColor=HexColor("#333"))
    bullet_s = ParagraphStyle("BL", parent=styles["Normal"], fontSize=9, leading=13, leftIndent=18, textColor=HexColor("#333"))

    story = []
    summary = comparison.get("summary", {})

    story.append(Paragraph("Cross-Case Comparison Report", title_s))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"Cases compared: {summary.get('case_count', 0)}",
        body_s,
    ))
    story.append(Spacer(1, 12))

    # Cases compared
    story.append(Paragraph("Cases Compared", h1_s))
    for m in comparison.get("case_metadata", []):
        story.append(Paragraph(f"<b>{m['case_name']}</b>", h2_s))
        story.append(Paragraph(f"Subjects ({m['subject_count']}): {', '.join(m['subjects']) or '—'}", bullet_s))
        if m.get("high_risk_subjects"):
            story.append(Paragraph(f"High-risk: {', '.join(m['high_risk_subjects'])}", bullet_s))
        story.append(Paragraph(
            f"Entities — Phones: {m['total_phones']} | IMEIs: {m['total_imeis']} | "
            f"IMSIs: {m['total_imsis']} | IPs: {m['total_ips']}",
            bullet_s,
        ))
    story.append(Spacer(1, 8))

    # Exec summary
    story.append(Paragraph("Executive Summary", h1_s))
    for f in summary.get("key_findings", []):
        story.append(Paragraph(f"&bull; {f}", bullet_s))
    story.append(Spacer(1, 8))

    # Shared entities
    _pdf_shared(story, "1. Shared Phone Numbers", comparison.get("shared_phones", []), "Phone", h1_s, h2_s, body_s, bullet_s)
    _pdf_shared(story, "2. Shared IMEIs (Device Identity)", comparison.get("shared_imeis", []), "IMEI", h1_s, h2_s, body_s, bullet_s)
    _pdf_shared(story, "3. Shared IMSIs (SIM Identity)", comparison.get("shared_imsis", []), "IMSI", h1_s, h2_s, body_s, bullet_s)
    _pdf_shared(story, "4. Shared Destination IPs", comparison.get("shared_ips", []), "IP", h1_s, h2_s, body_s, bullet_s)

    # Aliases
    story.append(Paragraph("5. Subject Name Alias Matches", h1_s))
    aliases = comparison.get("aliases", [])
    if not aliases:
        story.append(Paragraph("No alias matches detected.", body_s))
    else:
        story.append(Paragraph(
            "<i>Subject names from different cases that are similar enough to suggest the same individual. "
            "<b>EXACT</b> = normalized names identical; <b>STRONG</b> = high similarity; "
            "<b>POSSIBLE</b> = moderate similarity (review recommended).</i>",
            body_s,
        ))
        for a in aliases[:_CAP_ALIASES]:
            story.append(Paragraph(
                f"&bull; [<b>{a['match_strength']}</b>] '{a['name1']}' (case: {a['case1_name']}) "
                f"&lt;-&gt; '{a['name2']}' (case: {a['case2_name']}) — similarity {a['similarity']}",
                bullet_s,
            ))

    # Missing
    if comparison.get("missing"):
        story.append(Paragraph("Cases Excluded", h1_s))
        for m in comparison["missing"]:
            story.append(Paragraph(
                f"&bull; {m.get('case_name', m['case_id'])}: {m['reason']}",
                bullet_s,
            ))

    # Appendix A — methodology / risk-scoring rubric
    append_rubric_to_pdf(story, h1_s, h2_s, body_s, bullet_s)

    pdf.build(story)
    logger.info(f"Cross-case PDF saved to {output_path}")


def _pdf_shared(story, title, items, label, h1_s, h2_s, body_s, bullet_s):
    story.append(Paragraph(title, h1_s))
    if not items:
        story.append(Paragraph(f"<i>No shared {label}s detected across the selected cases.</i>", body_s))
        story.append(Spacer(1, 4))
        return
    story.append(Paragraph(
        f"Total shared {label}s: <b>{len(items)}</b> — each appears in 2 or more cases. "
        "Higher case_count = stronger cross-case lead.",
        body_s,
    ))
    for item in items[:_CAP_SHARED_ENTITIES]:
        story.append(Paragraph(f"<b>{label}: {item['value']}</b> ({item['case_count']} cases)", h2_s))
        for occ in item["occurrences"]:
            story.append(Paragraph(
                f"&bull; {occ['case_name']} — subjects: {', '.join(occ['subjects']) or '—'}",
                bullet_s,
            ))
    story.append(Spacer(1, 4))
