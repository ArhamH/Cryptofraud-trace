"""
database_admin.py
--------------------
Supabase connection, authentication, VASP directory indexing, and sanctions sync.
Supports credential resolution across both st.secrets and system environment variables (Render),
and includes one-click demo evaluator access.
"""

import os
import requests
import streamlit as st

try:
    from supabase import create_client
except ImportError:
    create_client = None

from system_architecture import (
    DEFAULT_VASP_EVM,
    DEFAULT_VASP_BTC,
    DEFAULT_VASP_SOL,
    SANCTIONED_EVM,
    classify_address_family,
)

def _get_credential(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

@st.cache_resource
def get_supabase_client():
    if create_client is None:
        return None
    try:
        url = _get_credential("SUPABASE_URL")
        key = _get_credential("SUPABASE_KEY")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None

def require_login(client):
    if st.session_state.get("auth_user"):
        return

    st.title("🔐 Investigator Login")
    st.caption("CryptoFraud Trace — restricted to authorized cyber crime investigators.")

    # High-prominence One-Click Demo Access button
    st.info("💡 **SIH Evaluation Access:** Click below to bypass authentication.")
    if st.button("🧪 One-Click Evaluator Demo Access", type="primary", use_container_width=True):
        st.session_state.auth_user = "evaluator.demo@sih.gov.in"
        st.rerun()

    if client is None:
        st.warning("⚠️ Running in Local/Offline Mode (Database client unconfigured).")
        st.stop()

    st.markdown("---")
    st.caption("Or sign in with registered LEA credentials:")

    with st.form("login_form"):
        email = st.text_input("Investigator Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", use_container_width=True)

    if submitted:
        try:
            result = client.auth.sign_in_with_password({"email": email, "password": password})
            if result and result.user:
                st.session_state.auth_user = result.user.email
                st.rerun()
            else:
                st.error("Invalid credentials.")
        except Exception as e:
            st.error(f"Login failed: {e}")

    st.stop()

def fetch_vasp_directory(client) -> dict:
    directory = {
        "evm": {**DEFAULT_VASP_EVM, **SANCTIONED_EVM},
        "btc": dict(DEFAULT_VASP_BTC),
        "solana": dict(DEFAULT_VASP_SOL),
    }
    if client:
        try:
            res = client.table("vasp_directory").select("address, vasp_name").execute()
            for row in (res.data or []):
                addr = row.get("address", "").strip()
                fam = classify_address_family(addr)
                if fam is None:
                    continue
                key = addr.lower() if fam == "evm" else addr
                directory[fam][key] = row.get("vasp_name", "").strip()
        except Exception:
            pass
    return directory

def save_case_to_db(client, case_data: dict):
    if client is None:
        return False, "Database client unconfigured. Findings not persisted."
    try:
        client.table("cases").insert(case_data).execute()
        return True, "Investigation record logged in Supabase."
    except Exception as e:
        return False, f"Database write failed: {e}"

def sync_opensanctions_labels(client, api_key: str = "", chain_filter: str = None, limit: int = 200):
    if client is None:
        return 0, "Database client unconfigured."

    key = api_key or _get_credential("OPENSANCTIONS_API_KEY")
    headers = {"Authorization": f"ApiKey {key}"} if key else {}
    params = {"schema": "CryptoWallet", "dataset": "sanctions", "limit": limit}

    try:
        resp = requests.get("https://api.opensanctions.org/search/default", params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        return 0, f"OpenSanctions fetch failed: {e}"

    rows = []
    for entity in results:
        props = entity.get("properties", {})
        addresses = props.get("publicKey") or props.get("address") or []
        caption = entity.get("caption", "Sanctioned Entity")
        for addr in addresses:
            addr = addr.strip()
            fam = classify_address_family(addr)
            if fam is None or (chain_filter and fam != chain_filter):
                continue
            rows.append({
                "address": addr,
                "vasp_name": f"SANCTIONED: {caption} (OFAC/OpenSanctions)"
            })

    if not rows:
        return 0, "No sanctioned records returned."
    try:
        client.table("vasp_directory").upsert(rows, on_conflict="address").execute()
        return len(rows), None
    except Exception as e:
        return 0, f"Database write failed: {e}"

def fetch_recent_cases(client, limit: int = 20):
    if client is None:
        return None, "Case repository requires active Supabase connection."
    try:
        res = client.table("cases").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data or [], None
    except Exception as e:
        return None, f"Could not load cases: {e}"
