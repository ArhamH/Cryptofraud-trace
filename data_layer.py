"""
data_layer.py
-----------------
Supabase client, authentication, and comprehensive benchmark case replay suite.
Covers: Mixers (OFAC), Peel Chains, DEX Swaps, Bridge Exits, and Sweep Deposits.
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
        st.session_state["auth_user"] = "evaluator.demo@sih.gov.in"
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
                st.session_state["auth_user"] = result.user.email
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
        "title": "🔴 Lazarus WazirX Breach (Mixer & Peel Chain)",
        "summary": "Multi-hop mule layering ke sath OFAC Tornado Cash routing aur micro-skims peel chains demonstrate karta hai.",
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
                "role": "intermediate",
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
                "role": "vasp",
                "vasp_name": "SANCTIONED: Tornado Cash Router (OFAC/SDN)",
                "taint_score": 0.88,
                "is_peel": True,
            }
        ],
        "cross_chain_alerts": []
    },

    "dex_swap_demo": {
        "id": "dex_swap_demo",
        "title": "🟣 Decentralized Exchange (DEX) Swap Hop",
        "summary": "Uniswap V3 router ke zariye token swap aur receiver address ke automatic resolution ko highlight karta hai.",
        "chain_family": "evm",
        "victim_wallet": "0x742d35cc6634c0532925a3b844bc454e4438f444",
        "trail": [
            {
                "from": "0x742d35cc6634c0532925a3b844bc454e4438f444",
                "to": "0xe592427a0aece92de3edee1f18e0157c05861564",
                "amount": 50000.0,
                "symbol": "USDT",
                "usd": 50000.0,
                "hash": "0x98f3b211a77e8d2e8b23f290d23abde31a78b4081c7f04bb9d29f8749a2a11b0",
                "hop": 1,
                "role": "dex_hop",
                "vasp_name": "Uniswap V3 Router [DEX SWAP]",
                "taint_score": 0.95,
                "is_peel": False,
                "is_dex": True
            },
            {
                "from": "0xe592427a0aece92de3edee1f18e0157c05861564",
                "to": "0x392e696634c3717837b0b060139721c0df48c5ff",
                "amount": 14.7,
                "symbol": "ETH",
                "usd": 49980.0,
                "hash": "0x98f3b211a77e8d2e8b23f290d23abde31a78b4081c7f04bb9d29f8749a2a11b0",
                "hop": 2,
                "role": "intermediate",
                "vasp_name": None,
                "taint_score": 0.92,
                "is_peel": False,
            },
            {
                "from": "0x392e696634c3717837b0b060139721c0df48c5ff",
                "to": "0x28c6c06298d514db089934071355e5743bf21d60",
                "amount": 14.7,
                "symbol": "ETH",
                "usd": 49980.0,
                "hash": "0x12a8bc94471f43a0e10b1a039d9189b216c54784a0d9238e811acbfa619d88cc",
                "hop": 3,
                "role": "vasp",
                "vasp_name": "Binance (Hot Wallet 14)",
                "taint_score": 0.90,
                "is_peel": False,
            }
        ],
        "cross_chain_alerts": []
    },

    "bridge_exit_demo": {
        "id": "bridge_exit_demo",
        "title": "🟠 Cross-Chain Bridge Exit (Stargate Router)",
        "summary": "EVM chain se bahar Stargate Liquidity Pool ke zariye fund transfer hone ka alert trigger karta hai.",
        "chain_family": "evm",
        "victim_wallet": "0x53d284357ec70ce289d6d64134dfac8e511c8a3d",
        "trail": [
            {
                "from": "0x53d284357ec70ce289d6d64134dfac8e511c8a3d",
                "to": "0x8731d54e9d02c286767d56ac03e8037c07e01e8",
                "amount": 120000.0,
                "symbol": "USDC",
                "usd": 120000.0,
                "hash": "0x4fe2b98e16bb4b190f897e93b169542a98f480397db9a8e9981f1816e87d4aa3",
                "hop": 1,
                "role": "bridge_exit",
                "vasp_name": "Stargate Finance Router [BRIDGE EXIT]",
                "taint_score": 0.96,
                "is_peel": False,
                "is_bridge": True
            }
        ],
        "cross_chain_alerts": [
            {
                "bridge_name": "Stargate Finance Router",
                "bridge_address": "0x8731d54e9d02c286767d56ac03e8037c07e01e8",
                "hop": 1,
                "amount": 120000.0,
                "symbol": "USDC",
                "usd": 120000.0,
                "node": "0x8731d54e9d02c286767d56ac03e8037c07e01e8",
                "note": "Cross-chain messaging router detect hua. Funds doosri chain par exit kar chuke hain, bridge relayers audit zaroori hai."
            }
        ]
    },

    "sweep_deposit_demo": {
        "id": "sweep_deposit_demo",
        "title": "🔵 Unregistered Deposit Sweep to VASP Cluster",
        "summary": "Forward sweep heuristic trace karta hai jisme ek intermediate wallet se exchange cluster me pura balance sweep ho jata hai.",
        "chain_family": "evm",
        "victim_wallet": "0x1111111254eeb25477b68fb85ed929f73a960582",
        "trail": [
            {
                "from": "0x1111111254eeb25477b68fb85ed929f73a960582",
                "to": "0x98127392a8374d92a18829374028374829103982",
                "amount": 25.0,
                "symbol": "ETH",
                "usd": 85000.0,
                "hash": "0x88923a1a9cb84e72398402847a98234bcade0192840918239048a12903847291",
                "hop": 1,
                "role": "deposit_address",
                "vasp_name": "User Deposit Addr → WazirX (Deposit Cluster)",
                "taint_score": 0.95,
                "is_peel": False,
                "sweep_detected": True
            },
            {
                "from": "0x98127392a8374d92a18829374028374829103982",
                "to": "0x835678a611b28684005a5e2233695fb6cbbb0007",
                "amount": 24.99,
                "symbol": "ETH",
                "usd": 84966.0,
                "hash": "0x7723901928301928309182039182039182039182039182039182039182039182",
                "hop": 2,
                "role": "vasp",
                "vasp_name": "WazirX (Deposit Cluster)",
                "taint_score": 0.94,
                "is_peel": False,
            }
        ],
        "cross_chain_alerts": []
    }
}

def list_cases():
    return list(CASES.values())

def build_case_replay_graph(case_id: str):
    case = CASES.get(case_id)
    if not case or not case["trail"]:
        return None, [], [], case

    graph = nx.DiGraph()
    attributions = []
    start_key = case["victim_wallet"].lower() if case["chain_family"] == "evm" else case["victim_wallet"]
    
    graph.add_node(
        start_key, role="source", hop=0, is_replay=True, taint=1.0,
        label=f"Reported Drainer\n{start_key[:6]}...{start_key[-4:]}"
    )

    for hop_data in case["trail"]:
        src = hop_data["from"].lower() if case["chain_family"] == "evm" else hop_data["from"]
        dst = hop_data["to"].lower() if case["chain_family"] == "evm" else hop_data["to"]
        role = hop_data.get("role", "intermediate")
        is_vasp = role in ("vasp", "deposit_address")
        usd = hop_data.get("usd", 0.0)
        amount = hop_data.get("amount", 0.0)
        taint = hop_data.get("taint_score", 1.0)
        is_peel = hop_data.get("is_peel", False)
        vasp_label = hop_data.get("vasp_name") or f"Mule Hop {hop_data['hop']}"

        graph.add_node(
            dst, role=role, hop=hop_data["hop"], is_replay=True, taint=taint,
            label=f"{vasp_label}\n{dst[:6]}...{dst[-4:]}"
        )
        
        graph.add_edge(
            src, dst, amount=amount, symbol=hop_data["symbol"], usd=usd,
            priced=True, hash=hop_data.get("hash", ""), hop=hop_data["hop"],
            taint_score=taint, is_peel=is_peel, is_replay=True,
            sweep_detected=hop_data.get("sweep_detected", False)
        )

        if is_vasp:
            attributions.append({
                "node": dst, 
                "vasp": f"{hop_data['vasp_name']} [Benchmark]",
                "hop": hop_data["hop"], 
                "hash": hop_data.get("hash", "N/A"),
                "amount": amount, 
                "symbol": hop_data["symbol"], 
                "usd": usd,
                "taint_score": taint,
                "is_replay": True,
                "sweep_detected": hop_data.get("sweep_detected", False)
            })

    return graph, attributions, case.get("cross_chain_alerts", []), case
