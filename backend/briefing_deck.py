"""
Briefing Deck Generator
-----------------------
Generates a downloadable .pptx for senior officer briefings.

Style:
  - Clean government / agency aesthetic
  - White background, navy primary (#0A2540), thin gold accent (#C8A951)
  - Formal sans-serif (Calibri)
  - Capability-pitch tone, leadership-friendly, use-case driven
"""
from io import BytesIO
from datetime import datetime, timezone

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
NAVY = RGBColor(0x0A, 0x25, 0x40)        # primary
NAVY_DARK = RGBColor(0x06, 0x18, 0x2C)   # header band
NAVY_SOFT = RGBColor(0xE8, 0xEE, 0xF5)   # soft tint backgrounds
GOLD = RGBColor(0xC8, 0xA9, 0x51)        # accent line
TEXT_DARK = RGBColor(0x1A, 0x1A, 0x1A)
TEXT_GRAY = RGBColor(0x55, 0x60, 0x6F)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
AMBER = RGBColor(0xB8, 0x6E, 0x00)

FONT = "Calibri"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _add_rect(slide, x, y, w, h, fill, line=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.75)
    shp.shadow.inherit = False
    return shp


def _add_text(slide, x, y, w, h, text, *,
              font_size=14, bold=False, color=TEXT_DARK,
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
    return tb


def _add_bullets(slide, x, y, w, h, items, *,
                 font_size=14, color=TEXT_DARK, leading=1.15, bullet_color=GOLD):
    """Custom bullets — a small gold square + text."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    for i, item in enumerate(items):
        if isinstance(item, tuple):
            head, sub = item
        else:
            head, sub = item, None
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_after = Pt(6)
        r1 = p.add_run()
        r1.text = "■  "
        r1.font.name = FONT
        r1.font.size = Pt(font_size)
        r1.font.color.rgb = bullet_color
        r1.font.bold = True
        r2 = p.add_run()
        r2.text = head
        r2.font.name = FONT
        r2.font.size = Pt(font_size)
        r2.font.color.rgb = color
        r2.font.bold = True
        if sub:
            r3 = p.add_run()
            r3.text = "  —  " + sub
            r3.font.name = FONT
            r3.font.size = Pt(font_size - 1)
            r3.font.color.rgb = TEXT_GRAY
            r3.font.bold = False
    return tb


def _slide_chrome(slide, *, title, eyebrow=None, page_num=None, total=None):
    """Standard slide chrome: navy header band, gold accent, title, footer."""
    # White background already default
    # Top navy band
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.55), NAVY_DARK)
    # Gold accent under band
    _add_rect(slide, Inches(0), Inches(0.55), SLIDE_W, Inches(0.04), GOLD)
    # Brand
    _add_text(
        slide, Inches(0.5), Inches(0.08), Inches(8), Inches(0.4),
        "AMBER  •  SIGINT FORENSIC PLATFORM",
        font_size=12, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE,
    )
    # Classification / status (right)
    _add_text(
        slide, Inches(9), Inches(0.08), Inches(4), Inches(0.4),
        "FOR OFFICIAL USE  •  OFFLINE SYSTEM",
        font_size=10, bold=True, color=GOLD,
        align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE,
    )
    # Eyebrow
    if eyebrow:
        _add_text(
            slide, Inches(0.5), Inches(0.85), Inches(10), Inches(0.3),
            eyebrow.upper(),
            font_size=11, bold=True, color=GOLD,
        )
    # Title
    _add_text(
        slide, Inches(0.5), Inches(1.1), Inches(12.3), Inches(0.7),
        title,
        font_size=32, bold=True, color=NAVY,
    )
    # Title underline (short navy bar)
    _add_rect(slide, Inches(0.5), Inches(1.85), Inches(0.7), Inches(0.06), NAVY)
    # Footer
    if page_num is not None and total is not None:
        _add_text(
            slide, Inches(0.5), Inches(7.15), Inches(6), Inches(0.3),
            "Briefing Deck  •  Senior Officer Review",
            font_size=9, color=TEXT_GRAY,
        )
        _add_text(
            slide, Inches(7.5), Inches(7.15), Inches(5.3), Inches(0.3),
            f"{page_num:02d} / {total:02d}",
            font_size=9, color=TEXT_GRAY, align=PP_ALIGN.RIGHT,
        )


def _stat_card(slide, x, y, w, h, *, number, label, sub=None, color=NAVY):
    _add_rect(slide, x, y, w, h, NAVY_SOFT)
    _add_rect(slide, x, y, Inches(0.06), h, color)  # left accent
    _add_text(
        slide, x + Inches(0.25), y + Inches(0.15), w - Inches(0.3), Inches(0.9),
        number, font_size=34, bold=True, color=color,
    )
    _add_text(
        slide, x + Inches(0.25), y + Inches(1.1), w - Inches(0.3), Inches(0.35),
        label.upper(), font_size=11, bold=True, color=TEXT_DARK,
    )
    if sub:
        _add_text(
            slide, x + Inches(0.25), y + Inches(1.4), w - Inches(0.3), Inches(0.4),
            sub, font_size=10, color=TEXT_GRAY,
        )


def _capability_card(slide, x, y, w, h, *, num, title, lines):
    _add_rect(slide, x, y, w, h, WHITE, line=NAVY_SOFT)
    # Number badge
    _add_rect(slide, x + Inches(0.2), y + Inches(0.2), Inches(0.5), Inches(0.5), NAVY)
    _add_text(
        slide, x + Inches(0.2), y + Inches(0.2), Inches(0.5), Inches(0.5),
        f"{num:02d}", font_size=14, bold=True, color=GOLD,
        align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
    )
    _add_text(
        slide, x + Inches(0.85), y + Inches(0.22), w - Inches(1.0), Inches(0.45),
        title, font_size=14, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE,
    )
    _add_rect(slide, x + Inches(0.2), y + Inches(0.85), w - Inches(0.4), Inches(0.02), GOLD)
    # Body
    body = slide.shapes.add_textbox(x + Inches(0.2), y + Inches(1.0), w - Inches(0.4), h - Inches(1.1))
    tf = body.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0); tf.margin_right = Emu(0)
    tf.margin_top = Emu(0); tf.margin_bottom = Emu(0)
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(4)
        r1 = p.add_run(); r1.text = "▸ "
        r1.font.name = FONT; r1.font.size = Pt(11); r1.font.bold = True
        r1.font.color.rgb = GOLD
        r2 = p.add_run(); r2.text = ln
        r2.font.name = FONT; r2.font.size = Pt(11); r2.font.color.rgb = TEXT_DARK


# ---------------------------------------------------------------------------
# Slide builders
# ---------------------------------------------------------------------------
def _slide_cover(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    # Full navy left band
    _add_rect(s, Inches(0), Inches(0), Inches(5.2), SLIDE_H, NAVY_DARK)
    # Gold vertical accent
    _add_rect(s, Inches(5.2), Inches(0), Inches(0.05), SLIDE_H, GOLD)
    # Left band content
    _add_text(s, Inches(0.6), Inches(0.7), Inches(4.4), Inches(0.4),
              "AMBER", font_size=22, bold=True, color=GOLD)
    _add_text(s, Inches(0.6), Inches(1.1), Inches(4.4), Inches(0.3),
              "SIGINT FORENSIC PLATFORM", font_size=11, bold=True, color=WHITE)
    _add_rect(s, Inches(0.6), Inches(1.55), Inches(0.7), Inches(0.04), GOLD)

    _add_text(s, Inches(0.6), Inches(5.3), Inches(4.4), Inches(0.4),
              "Prepared for", font_size=10, bold=True, color=GOLD)
    _add_text(s, Inches(0.6), Inches(5.6), Inches(4.4), Inches(0.4),
              "Senior Officer Review", font_size=14, bold=True, color=WHITE)
    _add_text(s, Inches(0.6), Inches(6.0), Inches(4.4), Inches(0.4),
              datetime.now(timezone.utc).strftime("%B %Y"),
              font_size=11, color=RGBColor(0xCC, 0xD3, 0xDD))
    _add_text(s, Inches(0.6), Inches(6.95), Inches(4.4), Inches(0.3),
              "FOR OFFICIAL USE  •  OFFLINE SYSTEM", font_size=8, bold=True, color=GOLD)

    # Right pane title
    _add_text(s, Inches(5.7), Inches(2.2), Inches(7.4), Inches(0.4),
              "PROJECT BRIEFING", font_size=12, bold=True, color=GOLD)
    _add_text(s, Inches(5.7), Inches(2.55), Inches(7.4), Inches(1.5),
              "An offline intelligence platform for\nCDR, IPDR, and WhatsApp triage.",
              font_size=30, bold=True, color=NAVY)
    _add_rect(s, Inches(5.7), Inches(4.4), Inches(0.7), Inches(0.06), GOLD)
    _add_text(s, Inches(5.7), Inches(4.6), Inches(7.4), Inches(1.5),
              "Turning weeks of manual log review into minutes of\nstructured, investigator-ready intelligence.",
              font_size=14, color=TEXT_GRAY)


def _slide_problem(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="Context", title="The investigator's bottleneck.", page_num=idx, total=total)
    # Two columns
    left_x = Inches(0.5); right_x = Inches(6.9)
    col_w = Inches(6.0); col_y = Inches(2.3); col_h = Inches(4.2)

    _add_rect(s, left_x, col_y, col_w, col_h, NAVY_SOFT)
    _add_text(s, left_x + Inches(0.3), col_y + Inches(0.25), col_w - Inches(0.4), Inches(0.4),
              "TODAY  —  MANUAL", font_size=12, bold=True, color=NAVY)
    _add_rect(s, left_x + Inches(0.3), col_y + Inches(0.7), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, left_x + Inches(0.3), col_y + Inches(0.95), col_w - Inches(0.6), Inches(3.2),
                 [
                     ("Raw CDR/IPDR PDFs", "Hundreds of pages per subject, scanned formats"),
                     ("WhatsApp ZIP exports", "Thousands of messages, mixed media, no index"),
                     ("Manual cross-checking", "Days of spreadsheet work per case"),
                     ("No cross-case visibility", "Same suspect in two cases? Goes unnoticed"),
                     ("No standard output", "Each officer writes a different report"),
                 ], font_size=12)

    _add_rect(s, right_x, col_y, col_w, col_h, WHITE, line=NAVY_SOFT)
    _add_text(s, right_x + Inches(0.3), col_y + Inches(0.25), col_w - Inches(0.4), Inches(0.4),
              "THE COST", font_size=12, bold=True, color=AMBER)
    _add_rect(s, right_x + Inches(0.3), col_y + Inches(0.7), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, right_x + Inches(0.3), col_y + Inches(0.95), col_w - Inches(0.6), Inches(3.2),
                 [
                     ("Time lost", "Triage of one WhatsApp export ≈ 2–3 days manually"),
                     ("Missed signals", "Bulk uploads, SIM swaps, co-location buried in noise"),
                     ("Inconsistent reports", "Hard to brief seniors, hard to compare across teams"),
                     ("Privacy risk", "Repeated copying of sensitive data across machines"),
                 ], font_size=12)


def _slide_solution(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="The platform", title="One offline workbench. Four capabilities.", page_num=idx, total=total)

    intro = ("AMBER ingests raw CDR, IPDR, and WhatsApp exports, runs rule-based "
             "intelligence analysis, scores risk, and produces investigator-ready "
             "reports — entirely on a local machine, with zero cloud dependency.")
    _add_text(s, Inches(0.5), Inches(2.05), Inches(12.3), Inches(0.7),
              intro, font_size=14, color=TEXT_GRAY)

    # 4 capability cards
    y = Inches(3.0); h = Inches(3.7); w = Inches(2.95); gap = Inches(0.15)
    x0 = Inches(0.5)
    _capability_card(s, x0 + (w + gap) * 0, y, w, h, num=1,
                     title="CDR Network Mapping",
                     lines=["Subject-to-subject contact graph",
                            "Alias detection across cases",
                            "Cell co-location & SIM-swap flags",
                            "Risk-scored top contacts"])
    _capability_card(s, x0 + (w + gap) * 1, y, w, h, num=2,
                     title="IPDR Triage",
                     lines=["Bulk upload / download alerts",
                            "Encrypted-app traffic markers",
                            "Long-session and odd-hour flags",
                            "Top destinations & domains"])
    _capability_card(s, x0 + (w + gap) * 2, y, w, h, num=3,
                     title="WhatsApp ZIP Triage",
                     lines=["Per-case local SQLite store",
                            "Financial-keyword highlighter",
                            "Image OCR + perceptual dedup",
                            "File-transfer & contact share map"])
    _capability_card(s, x0 + (w + gap) * 3, y, w, h, num=4,
                     title="Cross-Case Correlation",
                     lines=["Same number across cases",
                            "Alias / nickname matching",
                            "Shared contacts & towers",
                            "Single comparison report"])


def _slide_architecture(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="How it works", title="A single pipeline. Strict offline boundary.", page_num=idx, total=total)

    # 3 stages: Ingest -> Analyse -> Report
    stage_w = Inches(3.9); stage_h = Inches(3.4); y = Inches(2.6); gap = Inches(0.25)
    x0 = Inches(0.5)

    def stage(x, num, title, lines):
        _add_rect(s, x, y, stage_w, stage_h, WHITE, line=NAVY_SOFT)
        _add_rect(s, x, y, stage_w, Inches(0.55), NAVY)
        _add_text(s, x + Inches(0.3), y, Inches(0.6), Inches(0.55),
                  f"{num:02d}", font_size=18, bold=True, color=GOLD, anchor=MSO_ANCHOR.MIDDLE)
        _add_text(s, x + Inches(0.9), y, stage_w - Inches(1.0), Inches(0.55),
                  title, font_size=14, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
        _add_bullets(s, x + Inches(0.25), y + Inches(0.75), stage_w - Inches(0.5), stage_h - Inches(0.9),
                     lines, font_size=11)

    stage(x0 + (stage_w + gap) * 0, 1, "INGEST", [
        ("CDR / IPDR PDFs", "pdfplumber tabular extraction"),
        ("WhatsApp ZIP", "Chat + media, per-case SQLite"),
        ("Image OCR", "Tesseract, fully local"),
        ("Soft-delete", "3-min undo window"),
    ])
    stage(x0 + (stage_w + gap) * 1, 2, "ANALYSE", [
        ("Rule-based engine", "Deterministic, auditable"),
        ("Risk scoring", "Per subject & per contact"),
        ("Cross-correlation", "Aliases, towers, numbers"),
        ("Geospatial map", "If offline tiles available"),
    ])
    stage(x0 + (stage_w + gap) * 2, 3, "REPORT", [
        ("On-screen dashboards", "Charts, tables, network graph"),
        ("DOCX / PDF export", "Streaming, investigator-ready"),
        ("Comparison report", "Cross-case findings"),
        ("This briefing deck", "Auto-generated PPTX"),
    ])

    # Bottom strip: offline guarantee
    _add_rect(s, Inches(0.5), Inches(6.25), Inches(12.3), Inches(0.55), NAVY_SOFT)
    _add_text(s, Inches(0.75), Inches(6.25), Inches(12.0), Inches(0.55),
              "All processing happens on the local workstation. No data leaves the machine.",
              font_size=12, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)


def _capability_detail_slide(prs, idx, total, *, eyebrow, title, intro,
                             pillars, use_cases):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow=eyebrow, title=title, page_num=idx, total=total)

    _add_text(s, Inches(0.5), Inches(2.05), Inches(12.3), Inches(0.5),
              intro, font_size=13, color=TEXT_GRAY)

    # Left: what it does
    _add_rect(s, Inches(0.5), Inches(2.7), Inches(6.0), Inches(4.0), NAVY_SOFT)
    _add_text(s, Inches(0.75), Inches(2.85), Inches(5.5), Inches(0.4),
              "WHAT IT DOES", font_size=11, bold=True, color=NAVY)
    _add_rect(s, Inches(0.75), Inches(3.25), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, Inches(0.75), Inches(3.4), Inches(5.5), Inches(3.2),
                 pillars, font_size=12)

    # Right: use cases
    _add_rect(s, Inches(6.85), Inches(2.7), Inches(6.0), Inches(4.0), WHITE, line=NAVY_SOFT)
    _add_text(s, Inches(7.1), Inches(2.85), Inches(5.5), Inches(0.4),
              "USE CASES", font_size=11, bold=True, color=NAVY)
    _add_rect(s, Inches(7.1), Inches(3.25), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, Inches(7.1), Inches(3.4), Inches(5.5), Inches(3.2),
                 use_cases, font_size=12)


def _slide_cap_cdr(prs, idx, total):
    _capability_detail_slide(
        prs, idx, total,
        eyebrow="Capability 01",
        title="CDR Network Mapping & Alias Detection.",
        intro="Turn a stack of call logs into a labelled, risk-scored contact graph in minutes.",
        pillars=[
            ("Contact graph", "Auto-built per subject from raw CDR"),
            ("Top contacts ranked", "By call frequency, duration, odd-hour activity"),
            ("Alias detection", "Same number under different names across files"),
            ("Cell co-location", "Two subjects in the same tower at the same time"),
            ("SIM-swap flags", "IMSI/IMEI changes against the same number"),
        ],
        use_cases=[
            ("Suspect's inner circle", "Identify the 5–10 most frequent contacts instantly"),
            ("Hidden alias", "'Bhai' in one case = registered owner in another"),
            ("Meeting reconstruction", "Co-location at a tower confirms a physical meet"),
            ("Burner switch", "SIM-swap timing aligned with an event of interest"),
            ("Briefing chart", "Drop the network graph straight into a report"),
        ],
    )


def _slide_cap_ipdr(prs, idx, total):
    _capability_detail_slide(
        prs, idx, total,
        eyebrow="Capability 02",
        title="IPDR Bulk Transfer & Encrypted-Comms Triage.",
        intro="Surface the moments that matter inside thousands of data sessions.",
        pillars=[
            ("Bulk upload / download", "Sessions above a configurable byte threshold"),
            ("Encrypted-app markers", "Known VPN / messenger destination patterns"),
            ("Long-session flags", "Unusually long data sessions, odd-hour windows"),
            ("Top destinations", "Most-contacted IPs, ports, and domains"),
            ("Tabular PDF parsing", "Handles complex IPDR PDF layouts via pdfplumber"),
        ],
        use_cases=[
            ("Data exfiltration window", "Single 4-GB upload at 02:47 AM stands out"),
            ("Hidden channel", "Repeated traffic to encrypted-app endpoints"),
            ("Pattern of life", "Heavy late-night sessions vs daytime quiet"),
            ("Cross-reference", "Match IPDR session window with CDR call log"),
            ("Standardised summary", "Replace raw PDF with a 1-page IPDR brief"),
        ],
    )


def _slide_cap_whatsapp(prs, idx, total):
    _capability_detail_slide(
        prs, idx, total,
        eyebrow="Capability 03",
        title="WhatsApp ZIP Triage.",
        intro="Ingest a WhatsApp export and get a working intelligence summary, not just a text dump.",
        pillars=[
            ("Per-case local SQLite", "Chats stored locally, isolated per investigation"),
            ("Financial-keyword highlighter", "Transactions, amounts, wallet terms surfaced"),
            ("Image OCR", "Text inside screenshots becomes searchable evidence"),
            ("Perceptual de-duplication", "The same image forwarded 12 times = 1 finding"),
            ("File-transfer & contact share map", "Who sent what, to whom, when"),
        ],
        use_cases=[
            ("Money trail", "All amount / UPI / wallet mentions in one view"),
            ("Screenshot evidence", "OCR pulls bank slips, receipts, screenshots"),
            ("Repeat forwards", "Spot the original sender of a viral image"),
            ("Contact-sharing chains", "vCards passed between groups in sequence"),
            ("Timeline reconstruction", "Hour-by-hour activity for any participant"),
        ],
    )


def _slide_cap_compare(prs, idx, total):
    _capability_detail_slide(
        prs, idx, total,
        eyebrow="Capability 04",
        title="Cross-Case Correlation.",
        intro="Stop investigating in silos. See the same suspect across every case in the system.",
        pillars=[
            ("Same number, multiple cases", "Instant flag with case-level context"),
            ("Alias / nickname matching", "Fuzzy name match across investigations"),
            ("Shared contacts", "Common phone numbers between two cases"),
            ("Shared towers", "Same cell sites in both subjects' activity"),
            ("Single comparison report", "DOCX / PDF, ready to circulate"),
        ],
        use_cases=[
            ("Unknown overlap", "Two unrelated cases share a top-5 contact"),
            ("Network expansion", "One case's witness is another case's suspect"),
            ("Geographic overlap", "Both subjects active at the same tower cluster"),
            ("Alias confirmation", "'Sunny' in Case A = full name in Case B"),
            ("Leadership briefing", "One report, two cases, one narrative"),
        ],
    )


def _slide_roi(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="Return on effort", title="Hours, not days. Findings, not files.", page_num=idx, total=total)

    _add_text(s, Inches(0.5), Inches(2.05), Inches(12.3), Inches(0.5),
              "Indicative numbers from internal test runs on representative datasets.",
              font_size=12, color=TEXT_GRAY)

    # 4 stat cards
    y = Inches(2.7); h = Inches(1.85); w = Inches(2.95); gap = Inches(0.15)
    x0 = Inches(0.5)
    _stat_card(s, x0 + (w + gap) * 0, y, w, h,
               number="≈ 3 days  →  8 min",
               label="WhatsApp triage", sub="50k messages, with OCR & dedup")
    _stat_card(s, x0 + (w + gap) * 1, y, w, h,
               number="≈ 2 days  →  4 min",
               label="CDR network build", sub="One subject, multi-month CDR")
    _stat_card(s, x0 + (w + gap) * 2, y, w, h,
               number="≈ 1 day  →  2 min",
               label="IPDR triage", sub="Bulk + encrypted-comms flags")
    _stat_card(s, x0 + (w + gap) * 3, y, w, h,
               number="manual  →  one click",
               label="Cross-case correlation", sub="Compare any two cases")

    # Bottom narrative
    _add_rect(s, Inches(0.5), Inches(4.85), Inches(12.3), Inches(1.85), NAVY_SOFT)
    _add_text(s, Inches(0.8), Inches(4.95), Inches(11.5), Inches(0.4),
              "WHAT THAT MEANS IN PRACTICE", font_size=11, bold=True, color=NAVY)
    _add_rect(s, Inches(0.8), Inches(5.35), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, Inches(0.8), Inches(5.5), Inches(11.5), Inches(1.2),
                 [
                     ("One officer can triage a case in a single sitting", "Instead of a multi-day backlog"),
                     ("Findings are consistent across teams", "Same rules, same output format"),
                     ("Senior reviews get standard, comparable reports", "DOCX / PDF / this deck — auto-generated"),
                 ], font_size=12)


def _slide_privacy(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="Data handling", title="Strictly offline. By design.", page_num=idx, total=total)

    # Big assurance card
    _add_rect(s, Inches(0.5), Inches(2.1), Inches(12.3), Inches(1.5), NAVY)
    _add_text(s, Inches(0.8), Inches(2.25), Inches(11.7), Inches(0.5),
              "OFFLINE-FIRST GUARANTEE", font_size=12, bold=True, color=GOLD)
    _add_rect(s, Inches(0.8), Inches(2.75), Inches(0.7), Inches(0.04), GOLD)
    _add_text(s, Inches(0.8), Inches(2.9), Inches(11.7), Inches(0.7),
              "No cloud uploads. No external APIs in the analysis pipeline. "
              "Sensitive data stays on the local workstation.",
              font_size=16, bold=True, color=WHITE)

    # Two columns: what's local / what's not
    col_w = Inches(6.0); y = Inches(3.85); h = Inches(2.9)

    _add_rect(s, Inches(0.5), y, col_w, h, NAVY_SOFT)
    _add_text(s, Inches(0.8), y + Inches(0.15), col_w - Inches(0.4), Inches(0.4),
              "RUNS LOCALLY", font_size=11, bold=True, color=NAVY)
    _add_rect(s, Inches(0.8), y + Inches(0.55), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, Inches(0.8), y + Inches(0.7), col_w - Inches(0.6), Inches(2.1),
                 [
                     ("CDR / IPDR parsing", "PDF text + tables extracted on machine"),
                     ("WhatsApp ingestion", "ZIP unpacked into per-case local SQLite"),
                     ("Image OCR", "Tesseract, fully local"),
                     ("Rule-based analysis", "Deterministic, no model calls"),
                     ("Report generation", "DOCX / PDF / PPTX built locally"),
                 ], font_size=12)

    _add_rect(s, Inches(6.85), y, col_w, h, WHITE, line=NAVY_SOFT)
    _add_text(s, Inches(7.15), y + Inches(0.15), col_w - Inches(0.4), Inches(0.4),
              "OPERATIONAL CONTROLS", font_size=11, bold=True, color=NAVY)
    _add_rect(s, Inches(7.15), y + Inches(0.55), Inches(0.5), Inches(0.04), GOLD)
    _add_bullets(s, Inches(7.15), y + Inches(0.7), col_w - Inches(0.6), Inches(2.1),
                 [
                     ("Soft-delete with undo", "3-minute window before permanent purge"),
                     ("Per-case isolation", "WhatsApp data segmented by case ID"),
                     ("Re-analysis banner", "Visible warning after data changes"),
                     ("Auditable rules", "Logic is reviewable, not a black box"),
                     ("Map tiles (optional)", "If offline tile cache present"),
                 ], font_size=12)


def _slide_roadmap(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="What's next", title="Roadmap.", page_num=idx, total=total)

    _add_text(s, Inches(0.5), Inches(2.05), Inches(12.3), Inches(0.5),
              "Phase 1 is live. Phase 2 and Phase 3 are clearly marked as planned future work.",
              font_size=12, color=TEXT_GRAY)

    # 3 phase columns
    col_w = Inches(3.95); y = Inches(2.7); h = Inches(4.0); gap = Inches(0.2)
    x0 = Inches(0.5)

    def phase(x, tag, tag_color, title, lines, status, status_color):
        _add_rect(s, x, y, col_w, h, WHITE, line=NAVY_SOFT)
        _add_rect(s, x, y, col_w, Inches(0.5), tag_color)
        _add_text(s, x + Inches(0.25), y, col_w - Inches(0.5), Inches(0.5),
                  tag, font_size=12, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
        _add_text(s, x + Inches(0.25), y + Inches(0.7), col_w - Inches(0.5), Inches(0.5),
                  title, font_size=14, bold=True, color=NAVY)
        _add_rect(s, x + Inches(0.25), y + Inches(1.2), Inches(0.5), Inches(0.04), GOLD)
        _add_bullets(s, x + Inches(0.25), y + Inches(1.4), col_w - Inches(0.5), Inches(2.0),
                     lines, font_size=11)
        # Status pill at bottom
        _add_rect(s, x + Inches(0.25), y + h - Inches(0.7), col_w - Inches(0.5), Inches(0.4),
                  status_color)
        _add_text(s, x + Inches(0.25), y + h - Inches(0.7), col_w - Inches(0.5), Inches(0.4),
                  status, font_size=11, bold=True, color=WHITE,
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    phase(x0 + (col_w + gap) * 0, "PHASE 1", NAVY, "Triage & Reporting",
          [("CDR / IPDR analysis", "Live"),
           ("WhatsApp ZIP triage", "Live"),
           ("Cross-case correlation", "Live"),
           ("Offline India geocoding", "Live"),
           ("Windows installer", "Live"),
           ("DOCX / PDF / PPTX export", "Live")],
          "LIVE", GREEN)

    phase(x0 + (col_w + gap) * 1, "PHASE 2", GOLD, "Language Support",
          [("Offline translation", "Argos Translate"),
           ("Language detection", "lingua-py"),
           ("Custom keyword lexicon", "Per-case phrases of interest"),
           ("Note: low-resource languages flagged for manual review", None)],
          "PLANNED — FUTURE", AMBER)

    phase(x0 + (col_w + gap) * 2, "PHASE 3", GOLD, "Voice Notes",
          [("Offline speech-to-text", "Whisper, local"),
           ("Hindi / Urdu / Punjabi only", "Honest scope"),
           ("No speaker identification", "Out of scope"),
           ("No deleted-message recovery", "Not technically feasible")],
          "PLANNED — FUTURE", AMBER)


def _slide_closing(prs, idx, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _slide_chrome(s, eyebrow="In summary", title="One workbench. Four capabilities. Local-first.", page_num=idx, total=total)

    # Three key takeaways
    y = Inches(2.4); h = Inches(2.6); w = Inches(3.95); gap = Inches(0.2)
    x0 = Inches(0.5)

    def takeaway(x, num, title, body):
        _add_rect(s, x, y, w, h, NAVY_SOFT)
        _add_rect(s, x, y, w, Inches(0.06), GOLD)
        _add_text(s, x + Inches(0.3), y + Inches(0.3), Inches(1.0), Inches(0.6),
                  f"{num:02d}", font_size=36, bold=True, color=NAVY)
        _add_text(s, x + Inches(0.3), y + Inches(1.05), w - Inches(0.6), Inches(0.5),
                  title, font_size=14, bold=True, color=NAVY)
        _add_text(s, x + Inches(0.3), y + Inches(1.55), w - Inches(0.6), Inches(1.0),
                  body, font_size=12, color=TEXT_DARK)

    takeaway(x0 + (w + gap) * 0, 1, "Faster",
             "Triage that took days now takes minutes. Investigators spend time on findings, not on parsing PDFs.")
    takeaway(x0 + (w + gap) * 1, 2, "Connected",
             "Cases are no longer silos. Numbers, aliases, towers, and contacts surface across every case in the system.")
    takeaway(x0 + (w + gap) * 2, 3, "Safe",
             "Strictly offline. No cloud calls. Soft-delete with undo. Auditable rule-based logic.")

    # CTA strip
    _add_rect(s, Inches(0.5), Inches(5.4), Inches(12.3), Inches(1.3), NAVY)
    _add_text(s, Inches(0.8), Inches(5.5), Inches(11.7), Inches(0.4),
              "RECOMMENDED NEXT STEP", font_size=11, bold=True, color=GOLD)
    _add_rect(s, Inches(0.8), Inches(5.9), Inches(0.5), Inches(0.04), GOLD)
    _add_text(s, Inches(0.8), Inches(6.05), Inches(11.7), Inches(0.55),
              "Pilot on one live case  •  Compare against current manual workflow  •  Greenlight Phase 2 scope",
              font_size=14, bold=True, color=WHITE)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def build_briefing_deck() -> bytes:
    """Build the briefing deck and return raw .pptx bytes."""
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Order of slides
    builders = [
        _slide_cover,        # cover counts as 01 visually but we don't number it
        _slide_problem,
        _slide_solution,
        _slide_architecture,
        _slide_cap_cdr,
        _slide_cap_ipdr,
        _slide_cap_whatsapp,
        _slide_cap_compare,
        _slide_roi,
        _slide_privacy,
        _slide_roadmap,
        _slide_closing,
    ]
    total = len(builders) - 1  # excluding cover

    # Cover
    builders[0](prs)
    # Numbered slides
    for i, builder in enumerate(builders[1:], start=1):
        builder(prs, i, total)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()
