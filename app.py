"""
CryptoFraud Trace — Law Enforcement Portal
SIH26183 | Ministry of Home Affairs (MHA)
"""

import streamlit as st

if st.query_params.get("health") == "check":
    st.write("OK")
    st.stop()

from system_architecture import get_api_key
from database_admin import get_supabase_client, require_login, fetch_vasp_directory
from frontend_ui import (
    render_header,
    render_sidebar,
    render_investigation_tab,
    render_case_history_tab,
    render_protocols_tab,
)

st.set_page_config(page_title="CryptoFraud Trace | MHA LEA Portal", page_icon="⚖️", layout="wide")

supabase_client = get_supabase_client()
require_login(supabase_client)

vasp_directory = fetch_vasp_directory(supabase_client)
api_key = get_api_key()

render_header()
settings = render_sidebar(supabase_client, vasp_directory, api_key)

tabs = st.tabs(["🔎 Live Investigation", "📁 Case History Log", "📜 Statutory Protocols"])

with tabs[0]:
    render_investigation_tab(settings, api_key, vasp_directory, supabase_client)

with tabs[1]:
    render_case_history_tab(supabase_client)

with tabs[2]:
    render_protocols_tab()
