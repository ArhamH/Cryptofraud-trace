"""
CryptoFraud Trace - Law Enforcement Portal
SIH26183 | Ministry of Home Affairs (MHA) | HBTU, Kanpur

Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from
Victim-Reported Suspect Wallet Addresses.
"""

import os
import re
import time
import tempfile
from datetime import datetime, timezone

import requests
import streamlit as st
import pandas as pd
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components

# Optional Supabase client initialization
try:
    from supabase import create_client
except ImportError:
    create_client = None


# -------------------------------------------------------------------
# Configuration & Constants
# -------------------------------------------------------------------

st.set_page_config(
    page_title="CryptoFraud Trace | MHA LEA Portal",
    page_icon="⚖️",
    layout="wide",
)

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"

CHAINS = {
    "Ethereum": 1,
    "BNB Smart Chain": 56,
    "Polygon": 137,
}

WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

# Static fallback database of known VASP hot wallets and deposit clusters
DEFAULT_KNOWN_VASPS = {
    # Binance Global Hot Wallets
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance (Hot Wallet 14)",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance (Hot Wallet 16)",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance (Hot Wallet 20)",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance (Hot Wallet 8)",
    "0x564286362092d8e7936f0549571a803b203aaced": "Binance (Hot Wallet 7)",
    # Indian Regulated VASPs (FIU-IND Compliant)
    "0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c": "CoinDCX (Deposit Cluster)",
    "0x835678a611b28684005a5e2233695fb6cbbb0007": "WazirX (Deposit Cluster)",
    "0x742d35cc6634c0532925a3b844bc454e4438f44e": "Bitbns (Deposit Cluster)",
}
DEFAULT_KNOWN_VASPS = {k.lower(): v for k, v in DEFAULT_KNOWN_VASPS.items()}


# -------------------------------------------------------------------
# Helper Functions & Database Layer
# -------------------------------------------------------------------

def short_addr(addr: str) -> str:
    """Format wallet addresses for compact visualization."""
    if not addr or len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


def get_api_key() -> str:
    """Retrieve Etherscan API key from secrets or environment."""
    try:
        return st.secrets["ETHERSCAN_API_KEY"]
    except Exception:
        return os.environ.get("ETHERSCAN_API_KEY", "")


@st.cache_resource
def get_supabase_client():
    """Establish and cache connection to Supabase database."""
    if create_client is None:
        return None
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None


def fetch_vasp_directory(client) -> dict:
    """Load known VASP clusters from Supabase with fallback to local cache."""
    vasp_map = dict(DEFAULT_KNOWN_VASPS)
    if client:
        try:
            res = client.table("vasp_directory").select("address, vasp_name").execute()
            if res.data:
                for row in res.data:
                    vasp_map[row["address"].strip().lower()] = row["vasp_name"].strip()
        except Exception:
            pass  # Fail gracefully to static dictionary
    return vasp_map


def save_case_to_db(client, case_data: dict):
    """Persist completed trace findings to Supabase."""
    if client is None:
        return False, "Database client unconfigured. Findings logged locally."
    try:
        client.table("cases").insert(case_data).execute()
        return True, "Investigation record successfully logged in Supabase."
    except Exception as e:
        return False, f"Database write failed: {str(e)}"


# -------------------------------------------------------------------
# On-Chain Ledger Extraction (Native + ERC-20)
# -------------------------------------------------------------------

def fetch_outgoing_native_txs(address: str, chain_id: int, api_key: str, limit: int = 25) -> list:
    """Fetch normal on-chain transactions (ETH/BNB/MATIC)."""
    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": limit,
        "sort": "desc",
        "apikey": api_key,
    }
    try:
        resp = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            return [
                {
                    "to": tx.get("to", "").lower(),
                    "value": int(tx.get("value", "0") or "0") / 1e18,
                    "symbol": "ETH/GAS",
                    "hash": tx.get("hash", ""),
                }
                for tx in data["result"]
                if tx.get("from", "").lower() == address.lower()
                and tx.get("to")
                and tx.get("isError", "0") == "0"
            ]
    except Exception:
        pass
    return []


def fetch_outgoing_token_txs(address: str, chain_id: int, api_key: str, limit: int = 25) -> list:
    """Fetch ERC-20 token transfers (USDT/USDC/etc.)."""
    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "tokentx",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": limit,
        "sort": "desc",
        "apikey": api_key,
    }
    try:
        resp = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            txs = []
            for tx in data["result"]:
                if tx.get("from", "").lower() == address.lower() and tx.get("to"):
                    decimals = int(tx.get("tokenDecimal", "18") or "18")
                    val = int(tx.get("value", "0") or "0") / (10 ** decimals)
                    txs.append({
                        "to": tx.get("to", "").lower(),
                        "value": val,
                        "symbol": tx.get("tokenSymbol", "TOKEN").upper(),
                        "hash": tx.get("hash", ""),
                    })
            return txs
    except Exception:
        pass
    return []


def fetch_all_outgoing_txs(address: str, chain_id: int, api_key: str, track_tokens: bool = True) -> list:
    """Aggregate native and token transfers for comprehensive mule tracking."""
    transfers = fetch_outgoing_native_txs(address, chain_id, api_key)
    if track_tokens:
        transfers.extend(fetch_outgoing_token_txs(address, chain_id, api_key))
    return transfers


# -------------------------------------------------------------------
# Multi-Hop Breadth-First Graph Traversal
# -------------------------------------------------------------------

def trace_fund_flow(
    start_address: str,
    chain_id: int,
    api_key: str,
    vasp_directory: dict,
    max_hops: int = 8,
    max_branches: int = 2,
    track_tokens: bool = True,
    simulation_fallback: bool = False,
    progress_cb=None
):
    """Walk outgoing transfers hop by hop until a terminal VASP is identified."""
    graph = nx.DiGraph()
    start = start_address.strip().lower()
    graph.add_node(start, role="source", hop=0, label=f"Suspect Drainer\n{short_addr(start)}")

    attributions = []
    frontier = [start]
    visited = {start}
    calls_made = 0
    hop = 0

    while frontier and hop < max_hops:
        hop += 1
        next_frontier = []

        for wallet in frontier:
            if progress_cb:
                progress_cb(hop, wallet)

            txs = fetch_all_outgoing_txs(wallet, chain_id, api_key, track_tokens=track_tokens)
            calls_made += (2 if track_tokens else 1)
            time.sleep(0.3)  # Rate-limit safety margin

            if not txs:
                continue

            # Keep dominant transfer per destination
            by_dest = {}
            for tx in txs:
                dest = tx["to"]
                if not dest or dest == wallet:
                    continue
                if dest not in by_dest or tx["value"] > by_dest[dest]["value"]:
                    by_dest[dest] = tx

            top_dests = sorted(by_dest.items(), key=lambda kv: kv[1]["value"], reverse=True)[:max_branches]

            for dest, meta in top_dests:
                is_vasp = dest in vasp_directory
                vasp_name = vasp_directory.get(dest)

                graph.add_node(
                    dest,
                    role="vasp" if is_vasp else "intermediate",
                    hop=hop,
                    label=f"{vasp_name}\n{short_addr(dest)}" if is_vasp else f"Hop {hop}\n{short_addr(dest)}"
                )

                graph.add_edge(
                    wallet,
                    dest,
                    value=round(meta["value"], 4),
                    symbol=meta["symbol"],
                    hash=meta["hash"],
                    hop=hop
                )

                if is_vasp:
                    attributions.append({
                        "node": dest,
                        "vasp": vasp_name,
                        "hop": hop,
                        "hash": meta["hash"],
                        "value": round(meta["value"], 4),
                        "symbol": meta["symbol"]
                    })
                elif dest not in visited:
                    next_frontier.append(dest)

            visited.add(wallet)

        frontier = next_frontier
        if attributions:
            break

    # Transparent Evaluation Fallback
    if not attributions and graph.number_of_nodes() > 1 and simulation_fallback:
        leaves = [n for n in graph.nodes if graph.out_degree(n) == 0 and n != start]
        if leaves:
            leaf = leaves[0]
            binance_hot = "0x28c6c06298d514db089934071355e5743bf21d60"
            graph.add_node(binance_hot, role="vasp", hop=hop, label="Binance (Hot Wallet 14) [SIMULATED]")
            graph.add_edge(leaf, binance_hot, value=1.25, symbol="USDT", hash="0xSIMULATED_HOP_DEMO", hop=hop)
            attributions.append({
                "node": binance_hot,
                "vasp": "Binance (Hot Wallet 14) [Simulation]",
                "hop": hop,
                "hash": "0xSIMULATED_HOP_DEMO",
                "value": 1.25,
                "symbol": "USDT"
            })

    return graph, attributions, calls_made


def calculate_confidence_score(attributions: list, hop_reached: int, max_hops: int) -> float:
    """Calculate forensic confidence score based on trace proximity."""
    if not attributions:
        return 0.0
    if "[Simulation]" in attributions[0]["vasp"]:
        return 45.0
    score = 80.0 + max(0.0, (max_hops - hop_reached) * 2.5)
    return float(max(50.0, min(99.0, score)))


# -------------------------------------------------------------------
# Interactive Graph Engine
# -------------------------------------------------------------------

def render_graph(graph: nx.DiGraph) -> str:
    """Build dynamic WebGL spring-physics graph."""
    net = Network(height="460px", width="100%", bgcolor="#ffffff", font_color="#1a1a1a", directed=True)

    colors = {
        "source": "#e74c3c",        # Red
        "intermediate": "#7f8c8d",  # Grey
        "vasp": "#27ae60",          # Emerald Green
    }

    for node, attrs in graph.nodes(data=True):
        role = attrs.get("role", "intermediate")
        label = attrs.get("label", short_addr(node))
        size = 32 if role == "source" else (28 if role == "vasp" else 18)
        net.add_node(node, label=label, color=colors[role], shape="dot", size=size)

    for src, dst, attrs in graph.edges(data=True):
        edge_label = f"{attrs.get('value', '')} {attrs.get('symbol', '')}"
        net.add_edge(src, dst, label=edge_label, arrows="to")

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -65,
          "centralGravity": 0.012,
          "springLength": 140,
          "springConstant": 0.08
        },
        "stabilization": { "iterations": 150 }
      }
    }
    """)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        net.save_graph(tmp.name)
        with open(tmp.name, "r", encoding="utf-8") as f:
            return f.read()


# -------------------------------------------------------------------
# Primary Investigator Portal
# -------------------------------------------------------------------

supabase_client = get_supabase_client()
VASP_DIRECTORY = fetch_vasp_directory(supabase_client)
api_key = get_api_key()

st.title("⚖️ CryptoFraud Trace")
st.subheader("Real-Time Identification & Legal Attribution of Fraud-Linked VASP Endpoints")
st.caption("SIH26183 | Ministry of Home Affairs (MHA) | HBTU, Kanpur")

# Sidebar Configuration
st.sidebar.header("Investigation Controls")
chain_name = st.sidebar.selectbox("Blockchain Ledger", list(CHAINS.keys()))
max_hops = st.sidebar.slider("Traversal Max Hops", 2, 15, 8)
max_branches = st.sidebar.slider("Branches per Mule Hop", 1, 4, 2)
track_tokens = st.sidebar.checkbox("Trace ERC-20 Tokens (USDT/USDC)", value=True)
simulation_fallback = st.sidebar.checkbox("Allow Demo Simulation Link", value=False)
save_case_toggle = st.sidebar.checkbox("Persist Findings to Case Database", value=True)

st.sidebar.markdown("---")
st.sidebar.write(f"**Database:** {'Supabase Connected' if supabase_client else 'Local Mode'}")
st.sidebar.write(f"**VASP Clusters Indexed:** {len(VASP_DIRECTORY)}")
st.sidebar.write(f"**Etherscan V2 Feed:** {'Operational' if api_key else 'Missing API Key'}")

tabs = st.tabs(["🔎 Live Investigation", "📁 Case History Log", "📜 Statutory Protocols"])

# TAB 1: Live Investigation
with tabs[0]:
    if not api_key:
        st.warning("⚠️ Etherscan API key missing. Configure `ETHERSCAN_API_KEY` in `.streamlit/secrets.toml` or environment.")

    suspect_wallet = st.text_input(
        "Victim-Reported Suspect Wallet (0x Address)",
        value="0x28c6c06298d514db089934071355e5743bf21d60",
        help="Input the initial scam/drainer wallet address reported in the FIR/14C portal.",
    )

    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        trace_btn = st.button("Initiate Traversal", type="primary", disabled=not api_key)
    with col_info:
        st.caption("🔴 Suspect Drainer   ⚪ Intermediate Mule   🟢 Regulated VASP Endpoint")

    if trace_btn:
        if not WALLET_RE.match(suspect_wallet.strip()):
            st.error("Invalid address format. Address must be '0x' followed by 40 hex characters.")
            st.stop()

        status = st.empty()
        progress_bar = st.progress(0)

        def on_progress(hop, wallet):
            progress_bar.progress(min(int(hop / max_hops * 100), 98))
            status.info(f"Traversing Hop {hop}/{max_hops}: Inspecting mule node `{short_addr(wallet)}`...")

        start_time = time.time()
        graph, attributions, calls_made = trace_fund_flow(
            start_address=suspect_wallet.strip(),
            chain_id=CHAINS[chain_name],
            api_key=api_key,
            vasp_directory=VASP_DIRECTORY,
            max_hops=max_hops,
            max_branches=max_branches,
            track_tokens=track_tokens,
            simulation_fallback=simulation_fallback,
            progress_cb=on_progress,
        )
        elapsed = time.time() - start_time
        status.empty()
        progress_bar.empty()

        if graph.number_of_edges() == 0:
            st.warning(f"No outgoing transactions discovered on {chain_name}. Verify network selection or explore alternative ledgers.")
            st.stop()

        # Render Flow Visualization
        components.html(render_graph(graph), height=480)

        hops_reached = max(attrs.get("hop", 0) for _, attrs in graph.nodes(data=True))

        # Metrics Dashboard
        st.subheader("Attribution & Velocity Analysis")
        top_attribution = attributions[0] if attributions else None
        conf = calculate_confidence_score(attributions, top_attribution["hop"] if top_attribution else hops_reached, max_hops)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Resolution Hops", hops_reached)
        m2.metric("Forensic Confidence", f"{conf:.0f}%" if top_attribution else "N/A")
        m3.metric("Mule Nodes Monitored", graph.number_of_nodes())
        m4.metric("Ledger Query Time", f"{elapsed:.1f}s")

        if top_attribution:
            st.success(
                f"**Terminal Custody Located:** Funds channeled to **{top_attribution['vasp']}** at hop {top_attribution['hop']}.\n\n"
                f"**Deposit Address:** `{top_attribution['node']}` | **Terminal TX:** `{top_attribution.get('hash', 'N/A')}`"
            )
        else:
            st.info(f"No registered VASP boundary reached within {max_hops} hops. Layering continues into cold/unindexed accounts.")

        # Persist to Database
        if save_case_toggle:
            case_record = {
                "suspect_wallet": suspect_wallet.strip(),
                "chain": chain_name,
                "hops_traversed": hops_reached,
                "attributed_vasp": top_attribution["vasp"] if top_attribution else None,
                "confidence_score": conf if top_attribution else 0.0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            saved, db_msg = save_case_to_db(supabase_client, case_record)
            st.caption(f"Audit Status: {db_msg}")

        # Legal Freeze Notice Generator
        st.subheader("Statutory Legal Notice")
        if top_attribution:
            notice_text = f"""================================================================================
OFFICIAL FREEZE DIRECTIVE UNDER SECTION 94 BNSS & PMLA GUIDELINES
Issued by Cyber Crime Unit / Law Enforcement Agency | Governed by I4C Standards
================================================================================
Generated Timestamp   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Subject Reference     : Emergency Freeze Notice - Stolen Cryptocurrency Assets
Target VASP / Entity  : {top_attribution['vasp']}
Chain Network         : {chain_name} (Chain ID: {CHAINS[chain_name]})

INCIDENT TRACE PARTICULARS:
--------------------------------------------------------------------------------
1. Reported Drainer   : {suspect_wallet.strip()}
2. Terminal Deposit   : {top_attribution['node']}
3. Layering Depth     : {top_attribution['hop']} intermediary hop(s)
4. Forensic Integrity : {conf:.0f}% Confidence
5. Terminal Tx Hash   : {top_attribution.get('hash', 'N/A')}

STATUTORY MANDATE:
Under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023 (formerly 
Section 91 CrPC) read with the Prevention of Money Laundering Act (PMLA), the 
compliance officer is hereby DIRECTED to:
  a) IMMEDIATELY RESTRICT and FREEZE all account balances tied to the designated
     terminal deposit address.
  b) PRESERVE Know Your Customer (KYC) logs, IP logs, linked bank accounts, and 
     associated fiat withdrawal endpoints.
  c) TRANSMIT an acknowledgement of restraint within 24 hours of notice delivery.

Authorized Signatory / Investigating Officer (IO):
State Cyber Crime Police Station / FIU Liason
================================================================================"""

            st.code(notice_text, language="text")
            st.download_button(
                "📥 Download BNSS Freezing Order",
                data=notice_text,
                file_name=f"BNSS_Section94_FreezeNotice_{short_addr(top_attribution['node'])}.txt",
                mime="text/plain",
            )
        else:
            st.info("Legal freezing orders generate automatically once an asset trail resolves to an identified exchange.")

# TAB 2: Case History Log
with tabs[1]:
    st.subheader("Persistent Case Repository")
    if supabase_client:
        try:
            records = supabase_client.table("cases").select("*").order("created_at", desc=True).limit(20).execute()
            if records.data:
                df = pd.DataFrame(records.data)
                df = df[["id", "suspect_wallet", "chain", "hops_traversed", "attributed_vasp", "created_at"]]
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No prior cases recorded in Supabase database.")
        except Exception as e:
            st.error(f"Could not load case repository: {e}")
    else:
        st.warning("Case repository requires active Supabase connection. Connect your credentials to review previous traces.")

# TAB 3: Statutory Protocols
with tabs[2]:
    st.subheader("Standard Operating Procedures for Investigating Officers")
    st.markdown("""
    1. **Primary Drainer Validation:** Verify complainant transaction hash on the public ledger before triggering automated multi-hop traversal.
    2. **ERC-20 & Native Parity:** Launderers frequently swap native assets for Tether (USDT). Maintain ERC-20 token tracking enabled on all EVM traces.
    3. **Legal Dispatch Protocol:** Once attribution is resolved, dispatch the Section 94 BNSS notice directly to the nodal compliance officer of the target exchange as mandated by FIU-IND and I4C guidelines.
    4. **Subpoena for KYC:** Follow up the provisional freezing notice with formal requisition of KYC documents under the Prevention of Money Laundering Act (PMLA).
    """)
