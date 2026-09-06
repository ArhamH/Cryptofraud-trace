"""
CryptoFraud Trace — Law Enforcement Portal
SIH26183 | Ministry of Home Affairs (MHA)

Multi-chain (EVM / Bitcoin / Solana) tracing of a victim-reported wallet
to a regulated exchange (VASP), with USD-normalized branch ranking,
Supabase-backed case history + VASP directory, and investigator login.

Entry point. One file per team role does the actual work:

    system_architecture.py   Arham Hasan  — Full-Stack & System Architect
    blockchain_api.py        Pranjal Awasthi — Blockchain & API Engineer
    graph_analytics.py       Ruchir Gupta — Graph Analytics Analyst
    frontend_ui.py           Amulya Agnihotri — Frontend & UI/UX Developer
    database_admin.py        Yash Prajapati — Cloud Security & DB Admin
    legal_forensics.py       Ayushi Singh — Cyber Forensics & Legal Lead

This file just sequences the calls between them.
"""

import streamlit as st

from system_architecture import get_api_key
from database_admin import get_supabase_client, require_login, fetch_vasp_directory
from frontend_ui import (
    render_header,
    render_sidebar,
    render_investigation_tab,
    render_case_history_tab,
    render_protocols_tab,
)

st.set_page_config(page_title="CryptoFraud Trace | MHA LEA Portal",
                    page_icon="⚖️", layout="wide")

# --- Bootstrapping: DB client, auth gate, VASP directory, API key --------
supabase_client = get_supabase_client()
require_login(supabase_client)  # halts here until investigator signs in

vasp_directory = fetch_vasp_directory(supabase_client)
api_key = get_api_key()

# --- Page chrome -----------------------------------------------------------
render_header()
settings = render_sidebar(supabase_client, vasp_directory, api_key)

# --- Tabs --------------------------------------------------------------------
tabs = st.tabs(["🔎 Live Investigation", "📁 Case History Log", "📜 Statutory Protocols"])

with tabs[0]:
    render_investigation_tab(settings, api_key, vasp_directory, supabase_client)

with tabs[1]:
    render_case_history_tab(supabase_client)

with tabs[2]:
    render_protocols_tab()
