"""
ai_assistant.py
----------------
Generates plain-language forensic and statutory case summaries for 
investigating officers and non-technical stakeholders.
Uses google-genai (Gemini 2.5 Flash) with an instant deterministic fallback.
"""

import os
import streamlit as st

def _get_gemini_key() -> str:
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "")

def generate_fallback_summary(suspect_wallet: str, chain_name: str, top_attribution: dict,
                              hops: int, peel_detected: bool, sweep_detected: bool) -> str:
    vasp = top_attribution.get("vasp", "Centralized Exchange / Sanctioned Entity")
    usd = top_attribution.get("usd", 0.0)
    dest_node = top_attribution.get("node", "N/A")
    taint = top_attribution.get("taint_score", 1.0) * 100

    peel_text = (
        "• **Laundering Technique (Peel Chain):** The suspect split the stolen assets across multiple "
        "temporary 'mule' wallets, peeling off small amounts while forwarding the bulk balance to evade tracking."
        if peel_detected else
        "• **Direct Pathing:** The funds were moved through direct consolidated transfers across intermediary nodes."
    )

    sweep_text = (
        "\n• **Automated Sweeping:** The terminal deposit was swept directly into an omnibus exchange hot wallet cluster."
        if sweep_detected else ""
    )

    return f"""### 🛡️ AI Case Brief (Plain-Language Forensic Summary)

**What Happened:**
Stolen digital assets originating from suspect wallet `{suspect_wallet[:10]}...{suspect_wallet[-6:]}` were systematically layered across **{hops} blockchain hop(s)** on the {chain_name} network.

**Forensic Findings:**
{peel_text}{sweep_text}
• **Terminal Destination:** Approximately **${usd:,.2f} USD** ({taint:.1f}% proportional taint) successfully reached **{vasp}** at deposit address `{dest_node}`.

**Statutory Recommendation for Investigating Officers (IO):**
Issue an immediate asset-freezing requisition under **Section 94 BNSS, 2023** and **Section 17 PMLA, 2002** to the compliance nodal officer of **{vasp}** to prevent off-ramping into fiat bank accounts."""

def generate_investigation_brief(suspect_wallet: str, chain_name: str, top_attribution: dict,
                                 hops: int, peel_detected: bool, sweep_detected: bool) -> str:
    """Invokes Gemini 2.5 Flash for contextual plain-language summaries; falls back cleanly on timeout/error."""
    api_key = _get_gemini_key()
    if not api_key:
        return generate_fallback_summary(suspect_wallet, chain_name, top_attribution, hops, peel_detected, sweep_detected)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = f"""
You are an expert digital forensics assistant for Indian Law Enforcement Agencies (State Cyber Police, I4C, FIU-IND).
Write a brief, authoritative 3-bullet plain-English case summary of this blockchain crime trail for a non-technical Police Officer or Court Judge:

Suspect Address: {suspect_wallet}
Ledger Network: {chain_name}
Terminal VASP / Entity: {top_attribution.get('vasp', 'N/A')}
Terminal Deposit Address: {top_attribution.get('node', 'N/A')}
Intermediary Hops Traversed: {hops}
Terminal Amount Traced: ~${top_attribution.get('usd', 0.0):,.2f} USD
Peel Chain Technique Identified: {peel_detected}
Deposit Sweeps Identified: {sweep_detected}

Formatting requirements:
1. Heading: '### 🛡️ AI Case Brief (Plain-Language Forensic Summary)'
2. Bullet 1: 'What Happened' (Explain the movement and layering simply).
3. Bullet 2: 'Forensic Evidence' (Mention the peel chains, sweeps, terminal exchange, and exact USD value).
4. Bullet 3: 'Immediate Action Mandated' (Cite Section 94 BNSS and Section 17 PMLA to freeze the account at the target VASP).
Keep it under 150 words, completely clear of technical jargon like UTXO or hash pointers.
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
    except Exception:
        pass

    return generate_fallback_summary(suspect_wallet, chain_name, top_attribution, hops, peel_detected, sweep_detected)
