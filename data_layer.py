"""
data_layer.py
-----------------
Supabase client, authentication, and offline benchmark case replay.
"""

import os
import requests
import streamlit as st
import networkx as nx

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
    except Exception:
        try:
            client.table("vasp_directory").insert(rows).execute()
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

CASES = {
    "wazirx_2024": {
        "id": "wazirx_2024",
        "title": "WazirX Multi-Sig Breach & Lazarus Laundering (July 2024)",
        "summary": (
            "~$235M drained from WazirX multisig storage proxy into exploiter consolidator "
            "wallets, followed by systematic peeling and deposit routing into the "
            "Tornado Cash Router contract (OFAC Sanctioned Entity)."
        ),
        "chain_family": "evm",
        "victim_wallet": "0x27fD43BABfbe83a81d14665b1a6fB8030A60C9b4",
        "trail": [
            {
                "from": "0x27fD43BABfbe83a81d14665b1a6fB8030A60C9b4",
                "to": "0x04b21735E93Fa3f8df70e2Da89e6922616891a88",
                "amount": 5433.0,
                "symbol": "ETH",
                "usd": 18472200.0,
                "hash": "0x58e4861433eba2184ffa39bfdc604cee872305970d4da6f38cdbf62a311957a6",
                "hop": 1,
                "vasp_name": None,
                "taint_score": 1.0,
                "is_peel": False,
            },
            {
                "from": "0x04b21735E93Fa3f8df70e2Da89e6922616891a88",
                "to": "0x8589427373d6d84e98730d7795d8f6f8731fda0",
                "amount": 100.0,
                "symbol": "ETH",
                "usd": 340000.0,
                "hash": "0x3a9cb7127e77747e452601ab03932fa5a73e6559bc8bb2798e4f16bc46a6fcf7",
                "hop": 2,
                "vasp_name": "SANCTIONED: Tornado Cash Router (OFAC/SDN)",
                "taint_score": 0.88,
                "is_peel": True,
            }
        ],
    },
}

def list_cases():
    return [c for c in CASES.values() if c["trail"]]

def build_case_replay_graph(case_id: str):
    case = CASES.get(case_id)
    if not case or not case["trail"]:
        return None, [], case

    graph = nx.DiGraph()
    attributions = []
    start_key = case["victim_wallet"].lower() if case["chain_family"] == "evm" else case["victim_wallet"]
    
    graph.add_node(
        start_key, role="source", hop=0, is_replay=True, taint=1.0,
        label=f"Compromised Proxy [REPLAY]\n{start_key[:10]}..."
    )

    for hop_data in case["trail"]:
        src = hop_data["from"].lower() if case["chain_family"] == "evm" else hop_data["from"]
        dst = hop_data["to"].lower() if case["chain_family"] == "evm" else hop_data["to"]
        is_vasp = hop_data.get("vasp_name") is not None
        usd = hop_data.get("usd", 0.0)
        amount = hop_data.get("amount", 0.0)
        taint = hop_data.get("taint_score", 1.0)
        is_peel = hop_data.get("is_peel", False)

        graph.add_node(
            dst, role="vasp" if is_vasp else "intermediate",
            hop=hop_data["hop"], is_replay=True, taint=taint,
            label=f"{hop_data['vasp_name']}\n{dst[:10]}..." if is_vasp else f"Mule Hop {hop_data['hop']}\n{dst[:10]}..."
        )
        
        graph.add_edge(
            src, dst, amount=amount, symbol=hop_data["symbol"], usd=usd,
            priced=True, hash=hop_data.get("hash", ""), hop=hop_data["hop"],
            taint_score=taint, is_peel=is_peel, is_replay=True
        )

        if is_vasp:
            attributions.append({
                "node": dst, 
                "vasp": f"{hop_data['vasp_name']} [Replay/Benchmark]",
                "hop": hop_data["hop"], 
                "hash": hop_data.get("hash", "N/A"),
                "amount": amount, 
                "symbol": hop_data["symbol"], 
                "usd": usd,
                "taint_score": taint,
                "is_replay": True
            })

    return graph, attributions, case
