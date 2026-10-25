from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
import logging

from rubric_appendix import append_rubric_to_docx, append_rubric_to_pdf

logger = logging.getLogger(__name__)

# Bounded iteration caps to keep report generation memory-safe on huge cases.
# The analysis JSON itself is already pre-aggregated, but defensively cap any list
# we render to keep generated DOCX/PDF sizes manageable for investigators.
_REPORT_FUNDING_HITS_PER_SUBJECT = 5
_REPORT_TEMPORAL_CAP = 25
_REPORT_FT_PLATFORMS_PER_SUBJECT = 25
_REPORT_BEHAVIORAL_RISK_INDICATORS = 15
_REPORT_COMMON_CONTACTS_NUMBERS = 15
_REPORT_PRIORITY_LEADS = 30
_REPORT_INTERROGATION_QUESTIONS = 20


def generate_docx_report(case, analysis, output_path):
    doc = Document()
    title = doc.add_heading("CDR & IPDR Intelligence Analysis Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Case: {case['name']}")
    doc.add_paragraph(f"Description: {case.get('description', '')}")
    doc.add_paragraph(f"Subjects: {', '.join(analysis.get('subjects', []))}")
    doc.add_paragraph("-" * 70)

    # Executive Summary
    doc.add_heading("Executive Summary", level=1)
    summary = analysis.get("summary", {})
    for finding in summary.get("key_findings", []):
        doc.add_paragraph(finding, style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 1. Funding Correlation
    doc.add_heading("1. Funding Correlation", level=1)
    funding = analysis.get("funding_correlation", {})
    for subject, activity in funding.get("subject_activity", {}).items():
        doc.add_heading(f"Subject: {subject}", level=2)
        for hit in activity[:_REPORT_FUNDING_HITS_PER_SUBJECT]:
            doc.add_paragraph(
                f"Platform: {hit.get('platform', 'N/A')} | IP: {hit.get('ip', 'N/A')} | Time: {hit.get('timestamp', 'N/A')}",
                style='List Bullet')
    for corr in funding.get("correlations", []):
        p = doc.add_paragraph()
        run = p.add_run(f"[{corr['strength']}] ")
        run.bold = True
        p.add_run(corr['inference'])
    doc.add_paragraph("-" * 70)

    # 2. Communication Probability
    doc.add_heading("2. Communication Probability Analysis", level=1)
    comm = analysis.get("communication_probability", {})
    all_plats = comm.get("all_platforms", [])
    matrix = comm.get("platform_matrix", {})
    if all_plats and matrix:
        table = doc.add_table(rows=1 + len(matrix), cols=1 + len(all_plats))
        table.style = 'Table Grid'
        table.cell(0, 0).text = "Subject"
        for i, plat in enumerate(all_plats):
            table.cell(0, i + 1).text = plat
        for row_idx, (subject, plat_map) in enumerate(matrix.items(), start=1):
            table.cell(row_idx, 0).text = subject
            for col_idx, plat in enumerate(all_plats):
                table.cell(row_idx, col_idx + 1).text = "Y" if plat_map.get(plat) else ""
    doc.add_paragraph("-" * 70)

    # 3. Temporal Overlap
    doc.add_heading("3. Temporal Overlap Analysis", level=1)
    temporal = analysis.get("temporal_overlap", {})
    # Explanation brief
    intro = doc.add_paragraph()
    intro.add_run(
        "Temporal Overlap detects events from different subjects that occur close in time "
        "(within a 60-minute correlation window). Such proximity is a strong indicator of "
        "coordination, attendance at the same event, or relayed activity. Lower the time "
        "difference, stronger the coordination signal."
    )
    bands_p = doc.add_paragraph()
    bands_p.add_run("Severity bands: ").bold = True
    bands_p.add_run(
        "CRITICAL (<1 min) — strong coordination; "
        "HIGH (1-5 min) — likely coordinated; "
        "MEDIUM (5-30 min) — possible coordination; "
        "LOW (30-60 min) — weak coincidence."
    )
    doc.add_paragraph(f"Total overlapping events: {temporal.get('total_overlaps', 0)}")

    # Per-band tally
    events_all = temporal.get("overlapping_events", [])
    bands = [("CRITICAL", 60), ("HIGH", 300), ("MEDIUM", 1800), ("LOW", 3600)]
    band_tally = {b[0]: 0 for b in bands}
    for ev in events_all:
        diff = ev.get("time_diff_seconds", 9999)
        for label, mx in bands:
            if diff <= mx:
                band_tally[label] += 1
                break
    tally_line = " | ".join(f"{lbl}: {band_tally[lbl]}" for lbl, _ in bands)
    doc.add_paragraph(f"Distribution — {tally_line}")

    for event in events_all[:_REPORT_TEMPORAL_CAP]:
        e1, e2 = event["event1"], event["event2"]
        diff = event["time_diff_seconds"]
        band_label = next((lbl for lbl, mx in bands if diff <= mx), "LOW")
        doc.add_paragraph(
            f"[{band_label}] {e1['subject']} ({e1.get('platform', 'N/A')}) at {e1['timestamp']} <-> "
            f"{e2['subject']} ({e2.get('platform', 'N/A')}) at {e2['timestamp']} "
            f"[{diff:.0f}s apart]", style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 4. File Transfer
    doc.add_heading("4. File Transfer Indicators", level=1)
    ft = analysis.get("file_transfer", {})
    for subject, activity in ft.get("subject_activity", {}).items():
        plats = set(a["platform"] for a in activity)
        doc.add_paragraph(f"{subject}: Uses {', '.join(plats)}", style='List Bullet')
    for shared in ft.get("shared_usage", []):
        doc.add_paragraph(shared["inference"], style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 5. Secure Messaging
    doc.add_heading("5. Secure Messaging Usage", level=1)
    sm = analysis.get("secure_messaging", {})
    for subject, findings in sm.get("encryption_findings", {}).items():
        doc.add_paragraph(
            f"{subject}: {', '.join(findings['platforms'])} - {findings['risk_note']}",
            style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 6. Location Correlation
    doc.add_heading("6. Location Correlation", level=1)
    loc = analysis.get("location_correlation", {})
    for subject, location in loc.get("subject_locations", {}).items():
        doc.add_paragraph(f"{subject}: {location}", style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 7. Communication Likelihood
    doc.add_heading("7. Communication Likelihood Matrix", level=1)
    cl = analysis.get("communication_likelihood", {})
    for pair in cl.get("pairs", []):
        doc.add_paragraph(
            f"{pair['subject1']} <-> {pair['subject2']}: {pair['likelihood']} "
            f"(Shared: {', '.join(pair['shared_platforms'])})", style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 8. Behavioral Profiling
    doc.add_heading("8. Behavioral Pattern Analysis", level=1)
    bp = analysis.get("behavioral_profiling", {})
    for subject, profile in bp.get("profiles", {}).items():
        doc.add_heading(f"Subject: {subject}", level=2)
        doc.add_paragraph(f"Role: {profile['role']}")
        doc.add_paragraph(f"Platforms: {', '.join(profile['platforms_used'][:_REPORT_FT_PLATFORMS_PER_SUBJECT])}")
        doc.add_paragraph(f"Behavior: {', '.join(profile['behavior_type'])}")
        if profile.get("imeis"):
            doc.add_paragraph(f"IMEI(s): {', '.join(list(profile['imeis'])[:10])}")
        for ind in profile.get("risk_indicators", [])[:_REPORT_BEHAVIORAL_RISK_INDICATORS]:
            doc.add_paragraph(f"WARNING: {ind}", style='List Bullet')
    if bp.get("shared_devices"):
        doc.add_heading("Shared Devices", level=2)
        for imei, subjects in bp["shared_devices"].items():
            doc.add_paragraph(f"IMEI {imei}: Used by {', '.join(subjects)}", style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 9. Common Contacts
    doc.add_heading("9. Common Contacts Analysis", level=1)
    cc = analysis.get("common_contacts", {})
    doc.add_paragraph(f"Total shared contacts: {cc.get('total_common_contacts', 0)}")
    for pair, data in cc.get("pairwise_common", {}).items():
        doc.add_paragraph(f"{pair}: {data['count']} common contacts", style='List Bullet')
        if data.get("numbers"):
            doc.add_paragraph(f"  Numbers: {', '.join(data['numbers'][:_REPORT_COMMON_CONTACTS_NUMBERS])}")
    if cc.get("common_across_all"):
        doc.add_heading("Numbers Common Across ALL Subjects", level=2)
        for num in cc["common_across_all"][:_REPORT_COMMON_CONTACTS_NUMBERS]:
            doc.add_paragraph(num, style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 10. SIM / IMSI Analysis
    doc.add_heading("10. SIM / IMSI Analysis", level=1)
    sim = analysis.get("sim_analysis", {})
    if not sim.get("has_imsi_data"):
        doc.add_paragraph("No IMSI metadata available in uploaded records.")
    else:
        doc.add_paragraph(
            "IMSI tracking detects foreign-issued SIMs (MCC outside India 404/405/406), "
            "SIM-swap behaviour (one IMEI used with multiple IMSIs), and IMSIs shared across "
            "subjects (passed-around / relay SIMs)."
        )
        if sim.get("foreign_sims"):
            doc.add_heading(f"Foreign-SIM Detections ({len(sim['foreign_sims'])})", level=2)
            for f in sim["foreign_sims"][:20]:
                doc.add_paragraph(
                    f"[{f['country'].upper()}] {f['subject']} — IMSI {f['imsi']} (MCC {f['mcc']}) — {f['count']} sessions",
                    style='List Bullet')
        if sim.get("sim_swaps"):
            doc.add_heading(f"SIM-Swap Patterns ({len(sim['sim_swaps'])})", level=2)
            for s in sim["sim_swaps"][:20]:
                doc.add_paragraph(
                    f"IMEI {s['imei']} used with {len(s['imsis'])} IMSIs: {', '.join(s['imsis'][:5])}",
                    style='List Bullet')
        if sim.get("multi_imsi_subjects"):
            doc.add_heading(f"Multi-SIM Subjects ({len(sim['multi_imsi_subjects'])})", level=2)
            for m in sim["multi_imsi_subjects"][:20]:
                doc.add_paragraph(m["inference"], style='List Bullet')
        if sim.get("shared_imsis"):
            doc.add_heading(f"Shared IMSIs across subjects ({len(sim['shared_imsis'])})", level=2)
            for s in sim["shared_imsis"][:20]:
                doc.add_paragraph(s["inference"], style='List Bullet')
        # Per-subject roster
        doc.add_heading("Per-Subject SIM Roster", level=2)
        for subject, info in sim.get("per_subject", {}).items():
            doc.add_paragraph(
                f"{subject}: {info['imsi_count']} IMSI(s), {info['foreign_count']} foreign",
                style='List Bullet')
            for imsi in info.get("imsis", [])[:5]:
                doc.add_paragraph(
                    f"  IMSI {imsi['imsi']} — {imsi['country']} (MCC {imsi['mcc']}) — {imsi['count']} sessions"
                    + ("  [FOREIGN]" if imsi.get("is_foreign") else ""))
    doc.add_paragraph("-" * 70)

    # 11. Cell Tower Co-Location
    doc.add_heading("11. Cell Tower Co-Location", level=1)
    coloc = analysis.get("cell_colocation", {})
    if not coloc.get("has_cell_data"):
        doc.add_paragraph("No Cell-ID metadata available in uploaded records.")
    else:
        doc.add_paragraph(
            "Co-location detects when two subjects appear on the same cell tower within ±5 minutes — "
            "strong evidence of physical co-presence (sub-km radius, much stronger than city-level geocoding). "
            "High-priority pairs are those appearing together at multiple distinct cell towers."
        )
        doc.add_paragraph(f"Total co-location events: {coloc.get('total_events', 0)}")
        if coloc.get("pair_summary"):
            doc.add_heading("Co-located Pairs", level=2)
            for p in coloc["pair_summary"][:10]:
                doc.add_paragraph(
                    f"{p['pair']}: {p['count']} meetings across {p['unique_cells']} distinct cells, closest gap {p['min_diff_seconds']:.0f}s",
                    style='List Bullet')
        if coloc.get("events"):
            doc.add_heading("Closest Co-location Events (top 25)", level=2)
            for ev in coloc["events"][:25]:
                diff = ev["time_diff_seconds"]
                tier = "SIMULTANEOUS" if diff <= 60 else "VERY CLOSE" if diff <= 180 else "CLOSE"
                doc.add_paragraph(
                    f"[{tier}] cell {ev['cell_id']}: {ev['subject1']} @ {ev['timestamp1']} <-> "
                    f"{ev['subject2']} @ {ev['timestamp2']} [{diff:.0f}s apart]",
                    style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 12. Bulk Data Transfer Alerts
    doc.add_heading("12. Bulk Data Transfer Alerts", level=1)
    bulk = analysis.get("bulk_transfer_analysis", {})
    if not bulk.get("has_volume_data"):
        doc.add_paragraph("No upload/download volume metadata available in uploaded IPDR records.")
    else:
        doc.add_paragraph(
            "Severity bands: ALERT (>500 MB single session) | HIGH (50–500 MB) | MEDIUM (10–50 MB). "
            "Upload-heavy sessions (upload >= 3x download) are a strong data-exfiltration signature."
        )
        for subject, info in bulk.get("per_subject", {}).items():
            doc.add_heading(
                f"{subject} — Up: {info['total_up_human']} / Down: {info['total_down_human']}  "
                f"[{info['alert_count']} ALERT, {info['high_count']} HIGH, {info['medium_count']} MED]",
                level=2)
            if info.get("top_platforms"):
                doc.add_paragraph("Top platforms by volume:")
                for p in info["top_platforms"][:5]:
                    doc.add_paragraph(
                        f"{p['platform']}: total {p['total_human']} (up {p['up_human']} / down {p['down_human']}) — {p['sessions']} sessions",
                        style='List Bullet')
            if info.get("top_sessions"):
                doc.add_paragraph("Heaviest sessions:")
                for s in info["top_sessions"][:8]:
                    upload_flag = "  [UPLOAD-HEAVY: possible exfiltration]" if s.get("is_upload_heavy") else ""
                    doc.add_paragraph(
                        f"[{s['severity']}] {s['platform']} @ {s['timestamp']} — "
                        f"up {s['volume_up_human']} / down {s['volume_down_human']}{upload_flag}",
                        style='List Bullet')
        if bulk.get("shared_heavy_platforms"):
            doc.add_heading("Shared Heavy-Use Platforms (cross-subject)", level=2)
            for s in bulk["shared_heavy_platforms"]:
                doc.add_paragraph(s["inference"], style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 13. Risk Scores
    doc.add_heading("13. Risk Assessment", level=1)
    for subject, score_data in analysis.get("risk_scores", {}).items():
        doc.add_heading(f"{subject}: {score_data['level']} ({score_data['score']}/100)", level=2)
        for factor in score_data.get("factors", []):
            doc.add_paragraph(factor, style='List Bullet')
    doc.add_paragraph("-" * 70)

    # 14. Priority Leads
    doc.add_heading("14. Priority Leads for Investigation", level=1)
    for lead in analysis.get("priority_leads", [])[:_REPORT_PRIORITY_LEADS]:
        doc.add_paragraph(f"[{lead['priority']}] {lead['type']}: {lead['value']}", style='List Bullet')
        doc.add_paragraph(f"  Action: {lead['action']}")
    doc.add_paragraph("-" * 70)

    # 15. Interrogation Questions
    doc.add_heading("15. Suggested Interrogation Questions", level=1)
    for subject, q_list in analysis.get("interrogation_questions", {}).items():
        doc.add_heading(f"Questions for {subject}", level=2)
        for i, q in enumerate(q_list[:_REPORT_INTERROGATION_QUESTIONS], 1):
            doc.add_paragraph(f"{i}. {q}")

    # Appendix A — Methodology / risk-scoring rubric
    append_rubric_to_docx(doc)

    doc.save(output_path)
    logger.info(f"DOCX report saved to {output_path}")


def generate_pdf_report(case, analysis, output_path):
    pdf = SimpleDocTemplate(output_path, pagesize=letter,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle('T', parent=styles['Title'], fontSize=16, textColor=HexColor('#1a1a1a'), spaceAfter=12)
    h1_s = ParagraphStyle('H1', parent=styles['Heading1'], fontSize=13, textColor=HexColor('#0047FF'), spaceBefore=14, spaceAfter=6)
    h2_s = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=11, textColor=HexColor('#333'), spaceBefore=10, spaceAfter=4)
    body_s = ParagraphStyle('B', parent=styles['Normal'], fontSize=9, leading=13, textColor=HexColor('#333'))
    bullet_s = ParagraphStyle('BL', parent=styles['Normal'], fontSize=9, leading=13, leftIndent=18, textColor=HexColor('#333'))

    story = []
    story.append(Paragraph("CDR & IPDR Intelligence Analysis Report", title_s))
    story.append(Paragraph(f"Case: {case['name']} | Subjects: {', '.join(analysis.get('subjects', []))}", body_s))
    story.append(Spacer(1, 12))

    # Summary
    story.append(Paragraph("Executive Summary", h1_s))
    for f in analysis.get("summary", {}).get("key_findings", []):
        story.append(Paragraph(f"&bull; {f}", bullet_s))
    story.append(Spacer(1, 8))

    # Sections
    section_renderers = [
        ("1. Funding Correlation", _render_funding_pdf),
        ("2. Communication Probability", _render_comm_pdf),
        ("3. Temporal Overlap", _render_temporal_pdf),
        ("4. File Transfer Indicators", _render_ft_pdf),
        ("5. Secure Messaging", _render_sm_pdf),
        ("6. Location Correlation", _render_loc_pdf),
        ("7. Communication Likelihood", _render_cl_pdf),
        ("8. Behavioral Profiling", _render_bp_pdf),
        ("9. Common Contacts", _render_cc_pdf),
        ("10. SIM / IMSI Analysis", _render_sim_pdf),
        ("11. Cell Tower Co-Location", _render_coloc_pdf),
        ("12. Bulk Data Transfer Alerts", _render_bulk_pdf),
        ("13. Risk Assessment", _render_risk_pdf),
        ("14. Priority Leads", _render_leads_pdf),
        ("15. Interrogation Questions", _render_questions_pdf),
    ]

    keys = ["funding_correlation", "communication_probability", "temporal_overlap",
            "file_transfer", "secure_messaging", "location_correlation",
            "communication_likelihood", "behavioral_profiling", "common_contacts",
            "sim_analysis", "cell_colocation", "bulk_transfer_analysis",
            "risk_scores", "priority_leads", "interrogation_questions"]

    for (title, renderer), key in zip(section_renderers, keys):
        story.append(Paragraph(title, h1_s))
        renderer(analysis.get(key, {}), story, h2_s, body_s, bullet_s)
        story.append(Spacer(1, 6))

    # Appendix A — Methodology / risk-scoring rubric
    append_rubric_to_pdf(story, h1_s, h2_s, body_s, bullet_s)

    pdf.build(story)
    logger.info(f"PDF report saved to {output_path}")


def _render_funding_pdf(data, story, h2, body, bullet):
    for subject, activity in data.get("subject_activity", {}).items():
        story.append(Paragraph(f"<b>{subject}:</b>", h2))
        for hit in activity[:5]:
            story.append(Paragraph(f"&bull; {hit.get('platform','N/A')} | IP: {hit.get('ip','N/A')} | {hit.get('timestamp','N/A')}", bullet))
    for corr in data.get("correlations", []):
        story.append(Paragraph(f"&bull; [{corr['strength']}] {corr['inference']}", bullet))


def _render_comm_pdf(data, story, h2, body, bullet):
    for subject, plats in data.get("subject_platforms", {}).items():
        story.append(Paragraph(f"&bull; {subject}: {', '.join(plats) if plats else 'None detected'}", bullet))


def _render_temporal_pdf(data, story, h2, body, bullet):
    # Explanation brief for investigators reading the PDF
    story.append(Paragraph(
        "<i>Temporal Overlap detects events from different subjects occurring close in time "
        "(within a 60-minute window). Lower the time gap, stronger the coordination signal. "
        "Bands: <b>CRITICAL</b> &lt;1 min, <b>HIGH</b> 1–5 min, <b>MEDIUM</b> 5–30 min, <b>LOW</b> 30–60 min.</i>",
        body))
    story.append(Paragraph(f"Total overlaps: {data.get('total_overlaps', 0)}", body))

    events_all = data.get("overlapping_events", [])
    bands = [("CRITICAL", 60), ("HIGH", 300), ("MEDIUM", 1800), ("LOW", 3600)]
    band_tally = {b[0]: 0 for b in bands}
    for ev in events_all:
        diff = ev.get("time_diff_seconds", 9999)
        for label, mx in bands:
            if diff <= mx:
                band_tally[label] += 1
                break
    story.append(Paragraph(
        "Distribution — " + " | ".join(f"<b>{lbl}:</b> {band_tally[lbl]}" for lbl, _ in bands),
        body))

    for ev in events_all[:_REPORT_TEMPORAL_CAP]:
        e1, e2 = ev["event1"], ev["event2"]
        diff = ev["time_diff_seconds"]
        band_label = next((lbl for lbl, mx in bands if diff <= mx), "LOW")
        story.append(Paragraph(
            f"&bull; [<b>{band_label}</b>] {e1['subject']} ({e1.get('platform','N/A')}) &lt;-&gt; "
            f"{e2['subject']} ({e2.get('platform','N/A')}) [{diff:.0f}s]",
            bullet))


def _render_ft_pdf(data, story, h2, body, bullet):
    for subject, activity in data.get("subject_activity", {}).items():
        plats = set(a["platform"] for a in activity)
        story.append(Paragraph(f"&bull; {subject}: {', '.join(plats)}", bullet))
    for s in data.get("shared_usage", []):
        story.append(Paragraph(f"&bull; {s['inference']}", bullet))


def _render_sm_pdf(data, story, h2, body, bullet):
    for subject, f in data.get("encryption_findings", {}).items():
        story.append(Paragraph(f"&bull; {subject}: {', '.join(f['platforms'])} - {f['risk_note']}", bullet))


def _render_loc_pdf(data, story, h2, body, bullet):
    for subject, loc in data.get("subject_locations", {}).items():
        story.append(Paragraph(f"&bull; {subject}: {loc}", bullet))


def _render_cl_pdf(data, story, h2, body, bullet):
    for pair in data.get("pairs", []):
        story.append(Paragraph(
            f"&bull; {pair['subject1']} &lt;-&gt; {pair['subject2']}: {pair['likelihood']} (Shared: {', '.join(pair['shared_platforms'])})",
            bullet))


def _render_bp_pdf(data, story, h2, body, bullet):
    for subject, profile in data.get("profiles", {}).items():
        story.append(Paragraph(f"<b>{subject}:</b> Role: {profile['role']}", h2))
        story.append(Paragraph(f"&bull; Platforms: {', '.join(profile['platforms_used'])}", bullet))
        story.append(Paragraph(f"&bull; Behavior: {', '.join(profile['behavior_type'])}", bullet))


def _render_cc_pdf(data, story, h2, body, bullet):
    story.append(Paragraph(f"Total shared contacts: {data.get('total_common_contacts', 0)}", body))
    for pair, d in data.get("pairwise_common", {}).items():
        story.append(Paragraph(f"&bull; {pair}: {d['count']} common", bullet))


def _render_risk_pdf(data, story, h2, body, bullet):
    for subject, score in data.items():
        if isinstance(score, dict) and "level" in score:
            story.append(Paragraph(f"<b>{subject}: {score['level']} ({score['score']}/100)</b>", h2))
            for f in score.get("factors", []):
                story.append(Paragraph(f"&bull; {f}", bullet))


def _render_leads_pdf(data, story, h2, body, bullet):
    if isinstance(data, list):
        for lead in data[:_REPORT_PRIORITY_LEADS]:
            story.append(Paragraph(f"&bull; [{lead['priority']}] {lead['type']}: {lead['value']}", bullet))
            story.append(Paragraph(f"  Action: {lead['action']}", bullet))


def _render_questions_pdf(data, story, h2, body, bullet):
    if isinstance(data, dict):
        for subject, qs in data.items():
            story.append(Paragraph(f"<b>Questions for {subject}:</b>", h2))
            for i, q in enumerate(qs[:_REPORT_INTERROGATION_QUESTIONS], 1):
                story.append(Paragraph(f"{i}. {q}", bullet))


def _render_sim_pdf(data, story, h2, body, bullet):
    if not data or not data.get("has_imsi_data"):
        story.append(Paragraph("<i>No IMSI metadata available in uploaded records.</i>", body))
        return
    story.append(Paragraph(
        "<i>IMSI tracking detects foreign-issued SIMs (MCC outside India 404/405/406), "
        "SIM-swap behaviour (one IMEI used with multiple IMSIs), and IMSIs shared across subjects.</i>",
        body))
    if data.get("foreign_sims"):
        story.append(Paragraph(f"<b>Foreign-SIM Detections ({len(data['foreign_sims'])})</b>", h2))
        for f in data["foreign_sims"][:20]:
            story.append(Paragraph(
                f"&bull; [<b>{f['country'].upper()}</b>] {f['subject']} — IMSI {f['imsi']} (MCC {f['mcc']}) — {f['count']} sessions",
                bullet))
    if data.get("sim_swaps"):
        story.append(Paragraph(f"<b>SIM-Swap Patterns ({len(data['sim_swaps'])})</b>", h2))
        for s in data["sim_swaps"][:20]:
            story.append(Paragraph(
                f"&bull; IMEI {s['imei']} used with {len(s['imsis'])} IMSIs: {', '.join(s['imsis'][:5])}",
                bullet))
    if data.get("multi_imsi_subjects"):
        story.append(Paragraph(f"<b>Multi-SIM Subjects ({len(data['multi_imsi_subjects'])})</b>", h2))
        for m in data["multi_imsi_subjects"][:20]:
            story.append(Paragraph(f"&bull; {m['inference']}", bullet))
    if data.get("shared_imsis"):
        story.append(Paragraph(f"<b>Shared IMSIs across subjects ({len(data['shared_imsis'])})</b>", h2))
        for s in data["shared_imsis"][:20]:
            story.append(Paragraph(f"&bull; {s['inference']}", bullet))
    story.append(Paragraph("<b>Per-Subject SIM Roster</b>", h2))
    for subject, info in data.get("per_subject", {}).items():
        story.append(Paragraph(
            f"&bull; <b>{subject}:</b> {info['imsi_count']} IMSI(s), {info['foreign_count']} foreign",
            bullet))
        for imsi in info.get("imsis", [])[:5]:
            flag = " [FOREIGN]" if imsi.get("is_foreign") else ""
            story.append(Paragraph(
                f"&nbsp;&nbsp;&nbsp;{imsi['imsi']} — {imsi['country']} (MCC {imsi['mcc']}) — {imsi['count']} sessions{flag}",
                bullet))


def _render_coloc_pdf(data, story, h2, body, bullet):
    if not data or not data.get("has_cell_data"):
        story.append(Paragraph("<i>No Cell-ID metadata available in uploaded records.</i>", body))
        return
    story.append(Paragraph(
        "<i>Detects when two subjects appear on the same cell tower within ±5 minutes — strong evidence "
        "of physical co-presence (sub-km radius). High-priority pairs are those appearing together at "
        "multiple distinct cells.</i>",
        body))
    story.append(Paragraph(f"Total co-location events: {data.get('total_events', 0)}", body))
    if data.get("pair_summary"):
        story.append(Paragraph("<b>Co-located Pairs</b>", h2))
        for p in data["pair_summary"][:10]:
            story.append(Paragraph(
                f"&bull; <b>{p['pair']}</b>: {p['count']} meetings across {p['unique_cells']} distinct cells, closest gap {p['min_diff_seconds']:.0f}s",
                bullet))
    if data.get("events"):
        story.append(Paragraph("<b>Closest Co-location Events (top 25)</b>", h2))
        for ev in data["events"][:25]:
            diff = ev["time_diff_seconds"]
            tier = "SIMULTANEOUS" if diff <= 60 else "VERY CLOSE" if diff <= 180 else "CLOSE"
            story.append(Paragraph(
                f"&bull; [<b>{tier}</b>] cell {ev['cell_id']}: {ev['subject1']} @ {ev['timestamp1']} &lt;-&gt; "
                f"{ev['subject2']} @ {ev['timestamp2']} [{diff:.0f}s apart]",
                bullet))


def _render_bulk_pdf(data, story, h2, body, bullet):
    if not data or not data.get("has_volume_data"):
        story.append(Paragraph("<i>No upload/download volume metadata available in IPDR records.</i>", body))
        return
    story.append(Paragraph(
        "<i>Severity bands: <b>ALERT</b> &gt;500 MB single session | <b>HIGH</b> 50–500 MB | "
        "<b>MEDIUM</b> 10–50 MB. Upload-heavy sessions (upload &gt;= 3x download) are a strong "
        "data-exfiltration signature.</i>",
        body))
    for subject, info in data.get("per_subject", {}).items():
        story.append(Paragraph(
            f"<b>{subject}</b> — Up: {info['total_up_human']} / Down: {info['total_down_human']} "
            f"[{info['alert_count']} ALERT, {info['high_count']} HIGH, {info['medium_count']} MED]",
            h2))
        if info.get("top_platforms"):
            story.append(Paragraph("<b>Top platforms by volume:</b>", body))
            for p in info["top_platforms"][:5]:
                story.append(Paragraph(
                    f"&bull; {p['platform']}: total {p['total_human']} (up {p['up_human']} / down {p['down_human']}) — {p['sessions']} sessions",
                    bullet))
        if info.get("top_sessions"):
            story.append(Paragraph("<b>Heaviest sessions:</b>", body))
            for s in info["top_sessions"][:8]:
                upload_flag = " <b>[UPLOAD-HEAVY: possible exfiltration]</b>" if s.get("is_upload_heavy") else ""
                story.append(Paragraph(
                    f"&bull; [<b>{s['severity']}</b>] {s['platform']} @ {s['timestamp']} — "
                    f"up {s['volume_up_human']} / down {s['volume_down_human']}{upload_flag}",
                    bullet))
    if data.get("shared_heavy_platforms"):
        story.append(Paragraph("<b>Shared Heavy-Use Platforms (cross-subject)</b>", h2))
        for s in data["shared_heavy_platforms"]:
            story.append(Paragraph(f"&bull; {s['inference']}", bullet))
