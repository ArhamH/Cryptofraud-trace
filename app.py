"""
CryptoFraud Trace — Law Enforcement Portal
SIH26183 | Ministry of Home Affairs (MHA)

Multi-chain (EVM / Bitcoin / Solana) tracing of a victim-reported wallet
to a regulated exchange (VASP), with USD-normalized branch ranking,
Supabase-backed case history + VASP directory, and investigator login.
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

try:
    from supabase import create_client
except ImportError:
    create_client = None


# =====================================================================
# Configuration
# =====================================================================

st.set_page_config(page_title="CryptoFraud Trace | MHA LEA Portal",
                    page_icon="⚖️", layout="wide")

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def _cfg(key: str, default: str) -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.environ.get(key, default)


MEMPOOL_BASE = _cfg("MEMPOOL_BASE", "https://mempool.space/api")
SOLANA_RPC = _cfg("SOLANA_RPC", "https://api.mainnet-beta.solana.com")

# Chain registry — one entry per selectable chain, tagged with its family
# (family decides which fetch/pricing/validation logic path runs).
CHAINS = {
    "Ethereum":        {"family": "evm", "chain_id": 1,   "native_symbol": "ETH"},
    "BNB Smart Chain": {"family": "evm", "chain_id": 56,  "native_symbol": "BNB"},
    "Polygon":         {"family": "evm", "chain_id": 137, "native_symbol": "MATIC"},
    "Bitcoin":         {"family": "btc"},
    "Solana":          {"family": "solana"},
}

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
BTC_RE = re.compile(r"^(1|3)[a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-zA-HJ-NP-Z0-9]{25,59}$")
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")  # base58, no 0/O/I/l

EXAMPLE_ADDRESSES = {
    "Ethereum": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "BNB Smart Chain": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "Polygon": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "Bitcoin": "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",   # publicly-known Binance BTC wallet
    "Solana": "",  # no verified public sample on hand — leave blank, prompt user
}

# --- VASP directories, split by chain family (address formats differ) -----
# SAMPLE / illustrative only — verify and expand via a proper labeled-address
# feed before relying on this for real attribution.
DEFAULT_VASP_EVM = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance (Hot Wallet 14)",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance (Hot Wallet 16)",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance (Hot Wallet 20)",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance (Hot Wallet 8)",
    "0x564286362092d8e7936f0549571a803b203aaced": "Binance (Hot Wallet 7)",
    "0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c": "CoinDCX (Deposit Cluster)",
    "0x835678a611b28684005a5e2233695fb6cbbb0007": "WazirX (Deposit Cluster)",
    "0x742d35cc6634c0532925a3b844bc454e4438f44e": "Bitbns (Deposit Cluster)",
}
DEFAULT_VASP_EVM = {k.lower(): v for k, v in DEFAULT_VASP_EVM.items()}

# Publicly documented Binance BTC addresses (case-sensitive — do NOT lowercase).
DEFAULT_VASP_BTC = {
    "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s": "Binance (BTC Hot Wallet, deprecated)",
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance (BTC Cold Wallet)",
}

# No verified public Solana VASP address bundled — populate via the
# `vasp_directory` Supabase table instead of guessing addresses here.
DEFAULT_VASP_SOL = {}

IGNORED_CONTRACTS = {  # EVM only — don't let stablecoin/wrapped contracts become "mule nodes"
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",  # WETH
    "0x4fabb145d64652a948d72533023f6e7a623c7c53",  # BUSD
}

STABLES = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "USDP", "FDUSD"}
NATIVE_COINGECKO_ID = {"ETH": "ethereum", "BNB": "binancecoin",
                        "MATIC": "matic-network", "BTC": "bitcoin", "SOL": "solana"}
PLATFORM_ID = {1: "ethereum", 56: "binance-smart-chain", 137: "polygon-pos"}


def classify_address_family(addr: str):
    if not addr:
        return None
    if EVM_RE.match(addr):
        return "evm"
    if BTC_RE.match(addr):
        return "btc"
    if SOL_RE.match(addr):
        return "solana"
    return None


def short_addr(addr: str) -> str:
    if not addr or len(addr) < 10:
        return addr
    return f"{addr[:6]}...{addr[-4:]}"


# =====================================================================
# Secrets / clients
# =====================================================================

def get_api_key() -> str:
    try:
        return st.secrets["ETHERSCAN_API_KEY"]
    except Exception:
        return os.environ.get("ETHERSCAN_API_KEY", "")


@st.cache_resource
def get_supabase_client():
    if create_client is None:
        return None
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception:
        return None


def fetch_vasp_directory(client) -> dict:
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
# Chain-specific fetchers — each returns a common transfer dict shape:
# {"to": str, "amount": float, "symbol": str, "hash": str, "contract": str|None}
# =====================================================================

def fetch_outgoing_native_txs(address, chain_id, api_key, native_symbol, limit=25):
    params = {"chainid": chain_id, "module": "account", "action": "txlist",
              "address": address, "startblock": 0, "endblock": 99999999,
              "page": 1, "offset": limit, "sort": "desc", "apikey": api_key}
    try:
        resp = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            return [
                {"to": tx.get("to", "").lower(), "amount": int(tx.get("value", "0") or "0") / 1e18,
                 "symbol": native_symbol, "hash": tx.get("hash", ""), "contract": None}
                for tx in data["result"]
                if tx.get("from", "").lower() == address.lower()
                and tx.get("to") and tx.get("isError", "0") == "0"
            ]
    except Exception:
        pass
    return []


def fetch_outgoing_token_txs(address, chain_id, api_key, limit=25):
    params = {"chainid": chain_id, "module": "account", "action": "tokentx",
              "address": address, "startblock": 0, "endblock": 99999999,
              "page": 1, "offset": limit, "sort": "desc", "apikey": api_key}
    try:
        resp = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            out = []
            for tx in data["result"]:
                if tx.get("from", "").lower() == address.lower() and tx.get("to"):
                    decimals = int(tx.get("tokenDecimal", "18") or "18")
                    val = int(tx.get("value", "0") or "0") / (10 ** decimals)
                    out.append({"to": tx.get("to", "").lower(), "amount": val,
                                "symbol": tx.get("tokenSymbol", "TOKEN").upper(),
                                "hash": tx.get("hash", ""),
                                "contract": tx.get("contractAddress", "").lower()})
            return out
    except Exception:
        pass
    return []


def fetch_outgoing_btc_txs(address, limit=25):
    """Bitcoin is UTXO-based: 'outgoing' means this address appears as an
    input (it spent funds); each non-change output is a hop candidate."""
    try:
        resp = requests.get(f"{MEMPOOL_BASE}/address/{address}/txs", timeout=15)
        resp.raise_for_status()
        txs = resp.json()
    except Exception:
        return []

    transfers = []
    for tx in txs[:limit]:
        vin_addrs = {v.get("prevout", {}).get("scriptpubkey_address") for v in tx.get("vin", [])}
        if address not in vin_addrs:
            continue
        for vout in tx.get("vout", []):
            dest = vout.get("scriptpubkey_address")
            if not dest or dest == address:
                continue  # skip change back to self
            transfers.append({"to": dest, "amount": vout.get("value", 0) / 1e8,
                               "symbol": "BTC", "hash": tx.get("txid", ""), "contract": None})
    return transfers


def fetch_outgoing_sol_txs(address, sig_limit=8):
    """Solana native SOL transfers only (SPL token transfers are a known
    gap — see limitations note in the sidebar)."""
    try:
        sig_resp = requests.post(SOLANA_RPC, json={
            "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
            "params": [address, {"limit": sig_limit}],
        }, timeout=15)
        sig_resp.raise_for_status()
        sigs = [s["signature"] for s in sig_resp.json().get("result", []) or []]
    except Exception:
        return []

    transfers = []
    for sig in sigs:
        try:
            tx_resp = requests.post(SOLANA_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            }, timeout=15)
            tx_resp.raise_for_status()
            result = tx_resp.json().get("result")
            if not result:
                continue
            instructions = result.get("transaction", {}).get("message", {}).get("instructions", [])
            for instr in instructions:
                parsed = instr.get("parsed")
                if not parsed or parsed.get("type") != "transfer":
                    continue
                info = parsed.get("info", {})
                if info.get("source") != address:
                    continue
                transfers.append({"to": info.get("destination"),
                                   "amount": info.get("lamports", 0) / 1e9,
                                   "symbol": "SOL", "hash": sig, "contract": None})
        except Exception:
            continue
        time.sleep(0.15)
    return transfers


def fetch_transfers(wallet, chain_key, api_key):
    chain = CHAINS[chain_key]
    family = chain["family"]
    if family == "evm":
        native = fetch_outgoing_native_txs(wallet, chain["chain_id"], api_key, chain["native_symbol"])
        tokens = fetch_outgoing_token_txs(wallet, chain["chain_id"], api_key)
        return native + tokens
    if family == "btc":
        return fetch_outgoing_btc_txs(wallet)
    if family == "solana":
        return fetch_outgoing_sol_txs(wallet)
    return []


# =====================================================================
# USD normalization — fixes "raw token amount" ranking bug
# =====================================================================

def fetch_native_prices(symbols_needed: set) -> dict:
    ids = [NATIVE_COINGECKO_ID[s] for s in symbols_needed if s in NATIVE_COINGECKO_ID]
    if not ids:
        return {}
    try:
        resp = requests.get(f"{COINGECKO_BASE}/simple/price",
                             params={"ids": ",".join(ids), "vs_currencies": "usd"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {sym: data.get(cid, {}).get("usd", 0.0)
                for sym, cid in NATIVE_COINGECKO_ID.items() if cid in data}
    except Exception:
        return {}


def fetch_token_prices(chain_id: int, contracts: set) -> dict:
    platform = PLATFORM_ID.get(chain_id)
    if not platform or not contracts:
        return {}
    try:
        resp = requests.get(f"{COINGECKO_BASE}/simple/token_price/{platform}",
                             params={"contract_addresses": ",".join(contracts), "vs_currencies": "usd"},
                             timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {addr.lower(): info.get("usd", 0.0) for addr, info in data.items()}
    except Exception:
        return {}


def annotate_usd_values(transfers, chain_key):
    chain = CHAINS[chain_key]
    family = chain["family"]
    chain_id = chain.get("chain_id")

    native_needed, contracts_needed = set(), set()
    for t in transfers:
        if t["symbol"] in STABLES:
            continue
        if t.get("contract"):
            contracts_needed.add(t["contract"])
        else:
            native_needed.add(t["symbol"])

    native_prices = fetch_native_prices(native_needed) if native_needed else {}
    token_prices = fetch_token_prices(chain_id, contracts_needed) if (family == "evm" and contracts_needed) else {}

    for t in transfers:
        if t["symbol"] in STABLES:
            t["usd"], t["priced"] = t["amount"] * 1.0, True
        elif t.get("contract") and t["contract"] in token_prices:
            t["usd"], t["priced"] = t["amount"] * token_prices[t["contract"]], True
        elif t["symbol"] in native_prices:
            t["usd"], t["priced"] = t["amount"] * native_prices[t["symbol"]], True
        else:
            t["usd"], t["priced"] = 0.0, False
    return transfers


# =====================================================================
# Multi-hop BFS trace (chain-family agnostic)
# =====================================================================

def trace_fund_flow(start_address, chain_key, api_key, vasp_directory,
                     max_hops=8, max_branches=2, simulation_fallback=False,
                     exhaustive_trace=True, progress_cb=None):
    family = CHAINS[chain_key]["family"]
    vasp_map = vasp_directory[family]

    start = start_address.strip()
    start_key = start.lower() if family == "evm" else start

    graph = nx.DiGraph()
    graph.add_node(start_key, role="source", hop=0, label=f"Suspect Drainer\n{short_addr(start_key)}")

    attributions, frontier, visited = [], [start], {start_key}
    calls_made, hop = 0, 0

    while frontier and hop < max_hops:
        hop += 1
        next_frontier = []

        for wallet in frontier:
            wallet_key = wallet.lower() if family == "evm" else wallet
            if progress_cb:
                progress_cb(hop, wallet_key)

            transfers = fetch_transfers(wallet, chain_key, api_key)
            calls_made += 1
            time.sleep(0.3)
            if not transfers:
                continue

            transfers = annotate_usd_values(transfers, chain_key)

            by_dest = {}
            for t in transfers:
                dest = t.get("to")
                if not dest:
                    continue
                dest_key = dest.lower() if family == "evm" else dest
                if dest_key == wallet_key:
                    continue
                if family == "evm" and dest_key in IGNORED_CONTRACTS:
                    continue
                if dest_key not in by_dest or t["usd"] > by_dest[dest_key]["usd"]:
                    by_dest[dest_key] = t

            # Rank by USD value, not raw token amount — a stablecoin and a
            # low-price altcoin are not comparable as raw numbers.
            top_dests = sorted(by_dest.items(), key=lambda kv: kv[1]["usd"], reverse=True)[:max_branches]

            for dest_key, meta in top_dests:
                is_vasp = dest_key in vasp_map
                vasp_name = vasp_map.get(dest_key)

                graph.add_node(
                    dest_key, role="vasp" if is_vasp else "intermediate", hop=hop,
                    label=f"{vasp_name}\n{short_addr(dest_key)}" if is_vasp else f"Hop {hop}\n{short_addr(dest_key)}",
                )
                graph.add_edge(wallet_key, dest_key, amount=round(meta["amount"], 6),
                                symbol=meta["symbol"], usd=round(meta["usd"], 2),
                                priced=meta["priced"], hash=meta["hash"], hop=hop)

                if is_vasp:
                    attributions.append({"node": dest_key, "vasp": vasp_name, "hop": hop,
                                          "hash": meta["hash"], "amount": round(meta["amount"], 6),
                                          "symbol": meta["symbol"], "usd": round(meta["usd"], 2)})
                elif dest_key not in visited:
                    next_frontier.append(dest_key)

            visited.add(wallet_key)

        frontier = next_frontier
        if attributions and not exhaustive_trace:
            # Fast mode: stop as soon as ANY branch hits a VASP. Note this
            # can leave a larger, still-open fund trail unresolved just
            # because a smaller side-branch happened to reach an exchange
            # first — exhaustive_trace=True (default) avoids that.
            break

    # Report the highest-value VASP hit first, not merely the first one
    # discovered — discovery order depends on wallet iteration order, not
    # on which trail actually carries the most money.
    attributions.sort(key=lambda a: a["usd"], reverse=True)

    if not attributions and simulation_fallback and family == "evm" and graph.number_of_nodes() > 1:
        leaves = [n for n in graph.nodes if graph.out_degree(n) == 0 and n != start_key]
        if leaves:
            leaf = leaves[0]
            binance_hot = "0x28c6c06298d514db089934071355e5743bf21d60"
            graph.add_node(binance_hot, role="vasp", hop=hop, label="Binance (Hot Wallet 14) [SIMULATED]")
            graph.add_edge(leaf, binance_hot, amount=1.25, symbol="USDT", usd=1.25,
                            priced=True, hash="0xSIMULATED_HOP_DEMO", hop=hop)
            attributions.append({"node": binance_hot, "vasp": "Binance (Hot Wallet 14) [Simulation]",
                                  "hop": hop, "hash": "0xSIMULATED_HOP_DEMO", "amount": 1.25,
                                  "symbol": "USDT", "usd": 1.25})

    return graph, attributions, calls_made


def calculate_confidence_score(attributions, hop_reached, max_hops):
    if not attributions:
        return 0.0
    if "[Simulation]" in attributions[0]["vasp"]:
        return 45.0
    score = 80.0 + max(0.0, (max_hops - hop_reached) * 2.5)
    return float(max(50.0, min(99.0, score)))


# =====================================================================
# Graph rendering
# =====================================================================

def render_graph(graph: nx.DiGraph) -> str:
    net = Network(height="460px", width="100%", bgcolor="#ffffff", font_color="#1a1a1a", directed=True)
    colors = {"source": "#e74c3c", "intermediate": "#7f8c8d", "vasp": "#27ae60"}

    for node, attrs in graph.nodes(data=True):
        role = attrs.get("role", "intermediate")
        label = attrs.get("label", short_addr(node))
        size = 32 if role == "source" else (28 if role == "vasp" else 18)
        net.add_node(node, label=label, color=colors[role], shape="dot", size=size)

    for src, dst, attrs in graph.edges(data=True):
        if attrs.get("priced"):
            edge_label = f"${attrs.get('usd', 0):,.0f}"
        else:
            edge_label = f"{attrs.get('amount', '')} {attrs.get('symbol', '')} ⚠️unpriced"
        net.add_edge(src, dst, label=edge_label, arrows="to",
                     title=f"tx {attrs.get('hash', '')[:16]}… (hop {attrs.get('hop')})")

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


# =====================================================================
# App
# =====================================================================

supabase_client = get_supabase_client()
require_login(supabase_client)  # halts here until investigator signs in

VASP_DIRECTORY = fetch_vasp_directory(supabase_client)
api_key = get_api_key()

st.title("⚖️ CryptoFraud Trace")
st.subheader("Real-Time Identification & Legal Attribution of Fraud-Linked VASP Endpoints")
st.caption("SIH26183 | Ministry of Home Affairs (MHA)")

st.sidebar.write(f"**Signed in as:** {st.session_state.get('auth_user')}")
if st.sidebar.button("Log out"):
    st.session_state.auth_user = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("Investigation Controls")
chain_name = st.sidebar.selectbox("Blockchain Ledger", list(CHAINS.keys()))
max_hops = st.sidebar.slider("Traversal Max Hops", 2, 15, 6)
max_branches = st.sidebar.slider("Branches per Mule Hop", 1, 4, 2)
simulation_fallback = st.sidebar.checkbox("Allow Demo Simulation Link (EVM only)", value=False)
exhaustive_trace = st.sidebar.checkbox(
    "Trace all branches to conclusion (recommended)", value=True,
    help="If off, the trace stops the instant ANY branch hits a VASP — "
         "which can under-report a larger fund trail that was still open. "
         "Uses more API calls; turn off only if you hit rate limits.")
save_case_toggle = st.sidebar.checkbox("Persist Findings to Case Database", value=True)

with st.sidebar.expander("Chain notes / known limitations"):
    st.caption(
        "- **Bitcoin**: UTXO model via mempool.space, first ~25 txs only "
        "(no deep pagination yet).\n"
        "- **Solana**: native SOL transfers only — SPL token transfers "
        "(USDC-SPL etc.) are not traced yet.\n"
        "- Public Solana RPC and mempool.space are rate-limited — for "
        "heavy use, point `SOLANA_RPC` / `MEMPOOL_BASE` in secrets at a "
        "dedicated provider.\n"
        "- Branch ranking uses **USD-normalized value** (CoinGecko), not "
        "raw token amount — a transfer CoinGecko can't price is flagged "
        "⚠️unpriced and ranked last, not excluded."
    )

st.sidebar.markdown("---")
st.sidebar.write(f"**Database:** {'Supabase Connected' if supabase_client else 'Local Mode'}")
st.sidebar.write(f"**VASP Clusters Indexed:** {sum(len(v) for v in VASP_DIRECTORY.values())}")
st.sidebar.write(f"**Etherscan V2 Feed:** {'Operational' if api_key else 'Missing API Key'}")

tabs = st.tabs(["🔎 Live Investigation", "📁 Case History Log", "📜 Statutory Protocols"])

# ---------------- TAB 1: Live Investigation ----------------
with tabs[0]:
    chain_family = CHAINS[chain_name]["family"]
    if chain_family == "evm" and not api_key:
        st.warning("⚠️ Etherscan API key missing. Configure `ETHERSCAN_API_KEY` in "
                   "`.streamlit/secrets.toml` or environment.")

    example = EXAMPLE_ADDRESSES.get(chain_name, "")
    suspect_wallet = st.text_input(
        f"Victim-Reported Suspect Wallet ({chain_name} address)",
        value=example,
        help="Input the initial scam/drainer wallet address reported in the FIR/14C portal.",
    )
    if example:
        st.caption(f"Example {chain_name} address format: `{example}`")
    elif chain_family == "solana":
        st.caption("Paste any real Solana address (base58, 32-44 chars) to test.")

    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        can_trace = api_key if chain_family == "evm" else True
        trace_btn = st.button("Initiate Traversal", type="primary", disabled=not can_trace)
    with col_info:
        st.caption("🔴 Suspect Drainer   ⚪ Intermediate Mule   🟢 Regulated VASP Endpoint")

    if trace_btn:
        cleaned = suspect_wallet.strip()
        detected_family = classify_address_family(cleaned)
        if detected_family != chain_family:
            st.error(f"That doesn't look like a valid {chain_name} address.")
            st.caption(f"Debug info — you entered: `{cleaned}` ({len(cleaned)} characters). "
                       f"Detected format: {detected_family or 'unrecognized'}, expected: {chain_family}.")
            st.stop()

        status = st.empty()
        progress_bar = st.progress(0)

        def on_progress(hop, wallet):
            progress_bar.progress(min(int(hop / max_hops * 100), 98))
            status.info(f"Traversing Hop {hop}/{max_hops}: Inspecting mule node `{short_addr(wallet)}`...")

        start_time = time.time()
        graph, attributions, calls_made = trace_fund_flow(
            start_address=cleaned, chain_key=chain_name, api_key=api_key,
            vasp_directory=VASP_DIRECTORY, max_hops=max_hops, max_branches=max_branches,
            simulation_fallback=simulation_fallback, exhaustive_trace=exhaustive_trace,
            progress_cb=on_progress,
        )
        elapsed = time.time() - start_time
        status.empty()
        progress_bar.empty()

        if graph.number_of_edges() == 0:
            st.warning(f"No outgoing transactions discovered on {chain_name}. "
                       "Verify the address or try another ledger.")
            st.stop()

        components.html(render_graph(graph), height=480)

        hops_reached = max(attrs.get("hop", 0) for _, attrs in graph.nodes(data=True))

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
                f"**Terminal Custody Located:** Funds channeled to **{top_attribution['vasp']}** "
                f"at hop {top_attribution['hop']} (~${top_attribution['usd']:,.2f}).\n\n"
                f"**Deposit Address:** `{top_attribution['node']}` | "
                f"**Terminal TX:** `{top_attribution.get('hash', 'N/A')}`"
            )
            if len(attributions) > 1:
                st.caption(f"⚠️ {len(attributions)} separate VASP endpoints were reached "
                           "(funds split across multiple branches). Largest shown above — "
                           "review all before issuing a freeze notice:")
                st.dataframe(
                    pd.DataFrame(attributions)[["vasp", "hop", "amount", "symbol", "usd", "node"]]
                    .rename(columns={"usd": "usd_value", "node": "deposit_address"}),
                    use_container_width=True,
                )
        else:
            st.info(f"No registered VASP boundary reached within {max_hops} hops.")

        if save_case_toggle:
            case_record = {
                "suspect_wallet": cleaned,
                "chain": chain_name,
                "hops_traversed": hops_reached,
                "attributed_vasp": top_attribution["vasp"] if top_attribution else None,
                "confidence_score": conf if top_attribution else 0.0,
                "investigator_email": st.session_state.get("auth_user"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            saved, db_msg = save_case_to_db(supabase_client, case_record)
            st.caption(f"Audit Status: {db_msg}")

        st.subheader("Statutory Legal Notice")
        if top_attribution:
            notice_text = f"""================================================================================
OFFICIAL FREEZE DIRECTIVE UNDER SECTION 94 BNSS & PMLA GUIDELINES
Issued by Cyber Crime Unit / Law Enforcement Agency | Governed by I4C Standards
================================================================================
Generated Timestamp   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
Investigating Officer : {st.session_state.get('auth_user', 'N/A')}
Target VASP / Entity  : {top_attribution['vasp']}
Chain Network         : {chain_name}

INCIDENT TRACE PARTICULARS:
--------------------------------------------------------------------------------
1. Reported Drainer   : {cleaned}
2. Terminal Deposit   : {top_attribution['node']}
3. Layering Depth     : {top_attribution['hop']} intermediary hop(s)
4. Forensic Integrity : {conf:.0f}% Confidence
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
            st.code(notice_text, language="text")
            st.download_button("📥 Download BNSS Freezing Order", data=notice_text,
                                file_name=f"BNSS_Section94_FreezeNotice_{short_addr(top_attribution['node'])}.txt",
                                mime="text/plain")
        else:
            st.info("Legal freezing orders generate automatically once an asset trail resolves to an identified exchange.")

# ---------------- TAB 2: Case History Log ----------------
with tabs[1]:
    st.subheader("Persistent Case Repository")
    if supabase_client:
        try:
            records = supabase_client.table("cases").select("*").order("created_at", desc=True).limit(20).execute()
            if records.data:
                df = pd.DataFrame(records.data)
                cols = [c for c in ["id", "suspect_wallet", "chain", "hops_traversed",
                                     "attributed_vasp", "investigator_email", "created_at"] if c in df.columns]
                st.dataframe(df[cols], use_container_width=True)
            else:
                st.info("No prior cases recorded in Supabase database.")
        except Exception as e:
            st.error(f"Could not load case repository: {e}")
    else:
        st.warning("Case repository requires active Supabase connection.")

# ---------------- TAB 3: Statutory Protocols ----------------
with tabs[2]:
    st.subheader("Standard Operating Procedures for Investigating Officers")
    st.markdown("""
    1. **Primary Drainer Validation:** Verify complainant transaction hash on the public ledger before triggering automated multi-hop traversal.
    2. **Cross-Asset Parity:** Launderers frequently swap between assets. Branch ranking here uses USD-normalized value across native coins, stablecoins, and ERC-20/BEP-20 tokens.
    3. **Legal Dispatch Protocol:** Once attribution is resolved, dispatch the Section 94 BNSS notice directly to the nodal compliance officer of the target exchange as mandated by FIU-IND and I4C guidelines.
    4. **Subpoena for KYC:** Follow up the provisional freezing notice with formal requisition of KYC documents under the Prevention of Money Laundering Act (PMLA).
    5. **Multi-chain scope:** Ethereum/BSC/Polygon (full token support), Bitcoin (native BTC only), Solana (native SOL only — SPL tokens not yet covered).
    """)
