"""
frontend_ui.py
-----------------
Role: Frontend & UI/UX Developer (Amulya Agnihotri)

All Streamlit view code: the sidebar investigation controls, the three
investigator-facing tabs (Live Investigation, Case History Log,
Statutory Protocols), and the interactive Pyvis physics-graph renderer
with the red/grey/green risk-signal color scheme (color system design +
Pyvis physics parameters). The actual tracing, pricing, DB, and legal
logic all live in their own role modules and get called from here.
"""

import tempfile
import time
from datetime import datetime, timezone

import networkx as nx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from system_architecture import CHAINS, EXAMPLE_ADDRESSES, classify_address_family, short_addr
from database_admin import save_case_to_db, fetch_recent_cases
from graph_analytics import trace_fund_flow, calculate_confidence_score
from legal_forensics import generate_freeze_notice

NODE_COLORS = {"source": "#e74c3c", "intermediate": "#7f8c8d", "vasp": "#27ae60"}


# =====================================================================
# Interactive physics graph rendering
# =====================================================================

def render_graph(graph: nx.DiGraph) -> str:
    net = Network(height="460px", width="100%", bgcolor="#ffffff", font_color="#1a1a1a", directed=True)

    for node, attrs in graph.nodes(data=True):
        role = attrs.get("role", "intermediate")
        label = attrs.get("label", short_addr(node))
        size = 32 if role == "source" else (28 if role == "vasp" else 18)
        net.add_node(node, label=label, color=NODE_COLORS[role], shape="dot", size=size)

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
# Page chrome
# =====================================================================

def render_header():
    st.title("⚖️ CryptoFraud Trace")
    st.subheader("Real-Time Identification & Legal Attribution of Fraud-Linked VASP Endpoints")
    st.caption("SIH26183 | Ministry of Home Affairs (MHA)")


def render_sidebar(supabase_client, vasp_directory, api_key) -> dict:
    """Renders the investigator controls and returns the chosen settings."""
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
    st.sidebar.write(f"**VASP Clusters Indexed:** {sum(len(v) for v in vasp_directory.values())}")
    st.sidebar.write(f"**Etherscan V2 Feed:** {'Operational' if api_key else 'Missing API Key'}")

    return {
        "chain_name": chain_name,
        "max_hops": max_hops,
        "max_branches": max_branches,
        "simulation_fallback": simulation_fallback,
        "exhaustive_trace": exhaustive_trace,
        "save_case_toggle": save_case_toggle,
    }


# =====================================================================
# Tabs
# =====================================================================

def render_investigation_tab(settings, api_key, vasp_directory, supabase_client):
    chain_name = settings["chain_name"]
    max_hops = settings["max_hops"]
    max_branches = settings["max_branches"]
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

    if not trace_btn:
        return

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
        vasp_directory=vasp_directory, max_hops=max_hops, max_branches=max_branches,
        simulation_fallback=settings["simulation_fallback"], exhaustive_trace=settings["exhaustive_trace"],
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

    if settings["save_case_toggle"]:
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
        notice_text = generate_freeze_notice(
            suspect_wallet=cleaned, chain_name=chain_name, top_attribution=top_attribution,
            confidence=conf, investigator=st.session_state.get("auth_user"),
        )
        st.code(notice_text, language="text")
        st.download_button("📥 Download BNSS Freezing Order", data=notice_text,
                            file_name=f"BNSS_Section94_FreezeNotice_{short_addr(top_attribution['node'])}.txt",
                            mime="text/plain")
    else:
        st.info("Legal freezing orders generate automatically once an asset trail resolves to an identified exchange.")


def render_case_history_tab(supabase_client):
    st.subheader("Persistent Case Repository")
    records, error = fetch_recent_cases(supabase_client, limit=20)
    if error:
        (st.warning if supabase_client is None else st.error)(error)
        return
    if not records:
        st.info("No prior cases recorded in Supabase database.")
        return
    df = pd.DataFrame(records)
    cols = [c for c in ["id", "suspect_wallet", "chain", "hops_traversed",
                         "attributed_vasp", "investigator_email", "created_at"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True)


def render_protocols_tab():
    st.subheader("Standard Operating Procedures for Investigating Officers")
    st.markdown("""
    1. **Primary Drainer Validation:** Verify complainant transaction hash on the public ledger before triggering automated multi-hop traversal.
    2. **Cross-Asset Parity:** Launderers frequently swap between assets. Branch ranking here uses USD-normalized value across native coins, stablecoins, and ERC-20/BEP-20 tokens.
    3. **Legal Dispatch Protocol:** Once attribution is resolved, dispatch the Section 94 BNSS notice directly to the nodal compliance officer of the target exchange as mandated by FIU-IND and I4C guidelines.
    4. **Subpoena for KYC:** Follow up the provisional freezing notice with formal requisition of KYC documents under the Prevention of Money Laundering Act (PMLA).
    5. **Multi-chain scope:** Ethereum/BSC/Polygon (full token support), Bitcoin (native BTC only), Solana (native SOL only — SPL tokens not yet covered).
    """)
