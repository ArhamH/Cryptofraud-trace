"""
database_admin.py
--------------------
Role: Cloud Security & DB Admin (Yash Prajapati)

Everything that touches Supabase: getting a client, the investigator
login gate (Supabase Auth), pulling the admin-curated VASP directory on
top of the static seed lists, and persisting/reading case records.
"""

import streamlit as st

try:
    from supabase import create_client
except ImportError:
    create_client = None

from system_architecture import (
    DEFAULT_VASP_EVM,
    DEFAULT_VASP_BTC,
    DEFAULT_VASP_SOL,
    classify_address_family,
)


# =====================================================================
# Supabase client
# =====================================================================

@st.cache_resource
def get_supabase_client():
    if create_client is None:
        return None
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception:
        return None


# =====================================================================
# Investigator authentication (Supabase Auth — app-level login)
# =====================================================================

def require_login(client):
    """Blocks the app behind a login form until an investigator signs in.
    Accounts must be provisioned by an admin in the Supabase project
    (Auth > Users) — there is intentionally no public self-signup for a
    law-enforcement tool."""
    if st.session_state.get("auth_user"):
        return

    st.title("🔐 Investigator Login")
    st.caption("CryptoFraud Trace — access restricted to authorized investigators.")

    if client is None:
        st.error("Authentication backend not configured (Supabase URL/Key missing "
                  "from secrets). Contact your administrator.")
        st.stop()

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In")

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

    st.caption("Forgot your password? Ask your Supabase project admin to reset it "
               "from the Auth dashboard.")
    st.stop()


# =====================================================================
# VASP directory sync + case persistence
# =====================================================================

def fetch_vasp_directory(client) -> dict:
    """Static seed directory, overlaid with any admin-curated rows from
    the `vasp_directory` Supabase table (falls back to seed-only if the
    table read fails or no client is configured)."""
    directory = {
        "evm": dict(DEFAULT_VASP_EVM),
        "btc": dict(DEFAULT_VASP_BTC),
        "solana": dict(DEFAULT_VASP_SOL),
    }
    if client:
        try:
            res = client.table("vasp_directory").select("address, vasp_name").execute()
            for row in (res.data or []):
                addr = row["address"].strip()
                fam = classify_address_family(addr)
                if fam is None:
                    continue
                key = addr.lower() if fam == "evm" else addr
                directory[fam][key] = row["vasp_name"].strip()
        except Exception:
            pass  # fall back to static directory
    return directory


def save_case_to_db(client, case_data: dict):
    if client is None:
        return False, "Database client unconfigured. Findings not persisted."
    try:
        client.table("cases").insert(case_data).execute()
        return True, "Investigation record logged in Supabase."
    except Exception as e:
        return False, f"Database write failed: {e}"


def fetch_recent_cases(client, limit: int = 20):
    """Returns (records, error_message). records is None on failure."""
    if client is None:
        return None, "Case repository requires active Supabase connection."
    try:
        res = client.table("cases").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data or [], None
    except Exception as e:
        return None, f"Could not load case repository: {e}"
