"""
legal_forensics.py
---------------------
Role: Cyber Forensics & Legal Lead (Ayushi Singh)

Generates the standardized BNSS Section 94 / PMLA freeze directive
text that gets dispatched to a target VASP's compliance officer once
an attribution has been resolved.
"""

from datetime import datetime, timezone


def generate_freeze_notice(suspect_wallet: str, chain_name: str, top_attribution: dict,
                            confidence: float, investigator: str) -> str:
    """Builds the full BNSS Section 94 / PMLA freeze notice text for a
    resolved attribution. Caller is responsible for checking that
    top_attribution is not None before calling this."""
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

STATUTORY MANDATE:
Under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 (formerly
Section 91 CrPC) read with the Prevention of Money Laundering Act (PMLA), the
compliance officer is hereby DIRECTED to:
  a) IMMEDIATELY RESTRICT and FREEZE all account balances tied to the designated
     terminal deposit address.
  b) PRESERVE KYC logs, IP logs, linked bank accounts, and fiat withdrawal endpoints.
  c) TRANSMIT an acknowledgement of restraint within 24 hours of notice delivery.

Authorized Signatory / Investigating Officer (IO):
State Cyber Crime Police Station / FIU Liaison
================================================================================"""
