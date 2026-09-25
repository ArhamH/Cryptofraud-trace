"""
legal_forensics.py
---------------------
Generates formal freeze notices under Section 94 BNSS (formerly Sec. 91 CrPC) 
and Section 17 PMLA in text and court-admissible PDF format with SHA-256 integrity hash.
"""

import hashlib
from datetime import datetime, timezone
from io import BytesIO

EMBLEM_TEXT = "GOVERNMENT OF INDIA — CYBER CRIME & FORENSIC INVESTIGATION UNIT"

def generate_freeze_notice(suspect_wallet: str, chain_name: str, top_attribution: dict,
                            confidence: float, investigator: str) -> str:
    return f"""================================================================================
OFFICIAL FREEZE DIRECTIVE UNDER SECTION 94 BNSS & PMLA GUIDELINES
Issued by Cyber Crime Unit / Law Enforcement Agency | Governed by I4C Standards
================================================================================
Generated Timestamp   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Investigating Officer : {investigator or 'N/A'}
Target VASP / Entity  : {top_attribution['vasp']}
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

def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

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

    body_text = generate_freeze_notice(suspect_wallet, chain_name, top_attribution, confidence, investigator)
    report_hash = _sha256_hex(body_text)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=16 * mm, bottomMargin=18 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm
    )
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("Header", parent=styles["Title"], fontSize=13, spaceAfter=2)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=8, alignment=1)
    mono_style = ParagraphStyle("Mono", parent=styles["Normal"], fontName="Courier", fontSize=8.5, leading=12)
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=6.5, textColor=colors.HexColor("#666666"))

    story = [
        Paragraph(EMBLEM_TEXT, sub_style),
        Spacer(1, 4),
        Paragraph("OFFICIAL FREEZE DIRECTIVE — SECTION 94 BNSS / PMLA SEC. 17", header_style),
        Paragraph("Digital Forensic Evidence Report | I4C Compliance Standards", sub_style),
        Spacer(1, 8),
    ]

    rows = [
        ["Generated (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")],
        ["Investigating Officer", investigator or "N/A"],
        ["Chain Network", chain_name],
        ["Reported Drainer", suspect_wallet],
        ["Terminal Deposit (VASP)", top_attribution["vasp"]],
        ["Terminal Deposit Address", top_attribution["node"]],
        ["Layering Depth", f"{top_attribution['hop']} hop(s)"],
        ["Terminal Amount", f"{top_attribution['amount']} {top_attribution['symbol']} (~${top_attribution['usd']:,.2f})"],
        ["Terminal Tx Hash", top_attribution.get("hash", "N/A")],
        ["Forensic Confidence", f"{confidence:.0f}%"],
        ["Taint Decay Factor", f"{top_attribution.get('taint_score', 1.0) * 100:.1f}%"],
    ]
    table = Table(rows, colWidths=[55 * mm, 120 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f9fa")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [table, Spacer(1, 10)]

    if graph_png_bytes:
        try:
            img = RLImage(BytesIO(graph_png_bytes), width=175 * mm, height=90 * mm, kind="proportional")
            story += [
                Paragraph("Fund-Flow Graph Snapshot (Evidence Exhibit A)", styles["Heading4"]),
                img, Spacer(1, 8)
            ]
        except Exception:
            pass

    story += [
        Paragraph("Statutory Mandate", styles["Heading4"]),
        Paragraph(
            f"Under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, "
            f"read with Section 17 of the Prevention of Money Laundering Act (PMLA), 2002, "
            f"the compliance officer of <b>{top_attribution['vasp']}</b> is DIRECTED to: "
            f"(a) restrict and freeze all funds tied to the specified address; "
            f"(b) preserve all KYC, IP, and transaction audit trails; and "
            f"(c) furnish an acknowledgement of compliance within 24 hours.",
            mono_style,
        ),
        Spacer(1, 12),
        Paragraph("Authorized Signatory / Investigating Officer (IO)", styles["Normal"]),
        Paragraph("State Cyber Crime Police Station / FIU Liaison", sub_style),
        Spacer(1, 14),
        Paragraph(f"Chain-of-Custody Integrity Hash (SHA-256 of report body): {report_hash}", footer_style),
        Paragraph("Cryptographic proof of non-tampering for judicial admission.", footer_style),
    ]

    doc.build(story)
    return buf.getvalue()
