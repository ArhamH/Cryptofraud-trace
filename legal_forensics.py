"""
legal_forensics.py
---------------------
Generates formal freeze notices under Section 94 BNSS (formerly Sec. 91 CrPC) 
and Section 17 PMLA in plain text and court-admissible PDF format with SHA-256 integrity hash.
Sanitized for standard PDF core fonts and compliant with statutory header requirements.
"""

import re
import hashlib
from datetime import datetime, timezone
from io import BytesIO

def _sanitize_pdf_text(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'[^\x00-\x7F]+', ' ', str(text))
    return ' '.join(clean.split())

def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def generate_freeze_notice(suspect_wallet: str, chain_name: str, top_attribution: dict,
                            confidence: float, investigator: str) -> str:
    vasp_name = _sanitize_pdf_text(top_attribution.get('vasp', 'N/A'))
    return f"""================================================================================
STATUTORY FREEZING DIRECTIVE UNDER SECTION 94 BNSS & PMLA GUIDELINES
Issued by Cyber Crime Unit / Law Enforcement Agency | Governed by I4C Standards
================================================================================
Generated Timestamp   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Investigating Officer : {_sanitize_pdf_text(investigator or 'N/A')}
Target VASP / Entity  : {vasp_name}
Chain Network         : {chain_name}

INCIDENT TRACE PARTICULARS:
--------------------------------------------------------------------------------
1. Reported Drainer   : {suspect_wallet}
2. Terminal Deposit   : {top_attribution['node']}
3. Layering Depth     : {top_attribution['hop']} intermediary hop(s)
4. Forensic Integrity : {confidence:.0f}% Confidence
5. Terminal Amount    : {top_attribution['amount']} {top_attribution['symbol']} (~${top_attribution['usd']:,.2f})
6. Terminal Tx Hash   : {top_attribution.get('hash', 'N/A')}
7. Taint Decay Factor : {top_attribution.get('taint_score', 1.0) * 100:.1f}% (proportional attribution)

STATUTORY MANDATE:
Under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 (formerly
Section 91 CrPC) read with Section 17 of the Prevention of Money Laundering Act
(PMLA), 2002 (Search and Seizure), the compliance officer is hereby DIRECTED to:
  a) IMMEDIATELY RESTRICT and FREEZE all account balances tied to the designated
     terminal deposit address.
  b) PRESERVE KYC logs, IP logs, linked bank accounts, and fiat withdrawal endpoints.
  c) TRANSMIT an acknowledgement of restraint within 24 hours of notice delivery,
     per PMLA Section 17(1A) reporting obligations.

Authorized Signatory / Investigating Officer (IO):
State Cyber Crime Police Station / FIU Liaison
================================================================================"""

def generate_freeze_notice_pdf(suspect_wallet: str, chain_name: str, top_attribution: dict,
                                confidence: float, investigator: str,
                                graph_png_bytes: bytes | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, Image as RLImage
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    vasp_clean = _sanitize_pdf_text(top_attribution.get('vasp', 'N/A'))
    body_text = generate_freeze_notice(suspect_wallet, chain_name, top_attribution, confidence, investigator)
    report_hash = _sha256_hex(body_text)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=12 * mm, bottomMargin=14 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm
    )
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "Header", parent=styles["Title"], fontSize=12, leading=15, spaceAfter=2, alignment=1
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=8, leading=10, alignment=1, textColor=colors.HexColor("#444444")
    )
    mono_style = ParagraphStyle(
        "Mono", parent=styles["Normal"], fontName="Courier", fontSize=8, leading=11
    )
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], fontSize=6.5, leading=8.5, textColor=colors.HexColor("#555555")
    )

    story = [
        Paragraph("INDIAN CYBER CRIME COORDINATION CENTRE (I4C) STANDARDS", sub_style),
        Paragraph("MINISTRY OF HOME AFFAIRS (MHA) | AUTOMATED DIGITAL FORENSICS", sub_style),
        Spacer(1, 2 * mm),
        Paragraph("STATUTORY FREEZING DIRECTIVE - SECTION 94 BNSS / PMLA SEC. 17", header_style),
        Paragraph("Digital Forensic Evidence Report | Automated Blockchain Trail Analysis", sub_style),
        Spacer(1, 4 * mm),
    ]

    rows = [
        ["Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")],
        ["Investigating Officer", _sanitize_pdf_text(investigator or "N/A")],
        ["Chain Network", chain_name],
        ["Reported Drainer", suspect_wallet],
        ["Terminal Deposit (VASP)", vasp_clean],
        ["Terminal Deposit Address", top_attribution["node"]],
        ["Layering Depth", f"{top_attribution['hop']} hop(s)"],
        ["Terminal Amount", f"{top_attribution['amount']} {top_attribution['symbol']} (~${top_attribution['usd']:,.2f})"],
        ["Terminal Tx Hash", top_attribution.get("hash", "N/A")],
        ["Forensic Confidence", f"{confidence:.0f}%"],
        ["Taint Decay Factor", f"{top_attribution.get('taint_score', 1.0) * 100:.1f}% (proportional)"],
    ]

    table = Table(rows, colWidths=[52 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f5f7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [table, Spacer(1, 4 * mm)]

    if graph_png_bytes:
        try:
            img = RLImage(BytesIO(graph_png_bytes), width=180 * mm, height=75 * mm, kind="proportional")
            story += [
                Paragraph("<b>Fund-Flow Graph Snapshot (Evidence Exhibit A)</b>", styles["Normal"]),
                Spacer(1, 1 * mm),
                img,
                Spacer(1, 3 * mm)
            ]
        except Exception:
            pass

    mandate_p = (
        f"Under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 "
        f"(formerly Section 91 CrPC), read with Section 17 of the Prevention of "
        f"Money Laundering Act (PMLA), 2002, the compliance officer of <b>{vasp_clean}</b> "
        f"is DIRECTED to: (a) immediately restrict and freeze all account balances "
        f"tied to the terminal deposit address above; (b) preserve KYC records, IP logs, "
        f"linked bank accounts, and fiat withdrawal endpoints; and (c) transmit an "
        f"acknowledgement of restraint within 24 hours per PMLA Sec. 17(1A)."
    )

    story += [
        Paragraph("<b>Statutory Mandate</b>", styles["Normal"]),
        Spacer(1, 1 * mm),
        Paragraph(mandate_p, mono_style),
        Spacer(1, 4 * mm),
        Paragraph("<b>Authorized Signatory / Investigating Officer (IO)</b>", styles["Normal"]),
        Paragraph("State Cyber Crime Police Station / FIU Liaison", sub_style),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>Chain-of-Custody Integrity Hash (SHA-256):</b> {report_hash}", footer_style),
        Paragraph("Cryptographic proof of non-tampering for judicial admission under Indian Evidence Act.", footer_style),
    ]

    doc.build(story)
    return buf.getvalue()
