"""
frontend_ui.py
-----------------
Streamlit interface: sidebar controls, Pyvis physics graph renderer, 
benchmark replay runner, and BNSS PDF export.
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
from database_admin import save_case_to_db, fetch_recent_cases, sync_opensanctions_labels
from graph_analytics import trace_fund_flow, calculate_confidence_score
from legal_forensics import generate_freeze_notice, generate_freeze_notice_pdf
from case_replay import list_cases, build_case_replay_graph

NODE_COLORS = {
    "source": "#e74c3c", "intermediate": "#7f8c8d",
    "vasp": "#27ae60", "deposit_address": "#2980b9"
}
PEEL_EDGE_COLOR = "#f39c12"

def render_graph(graph: nx.DiGraph) -> str:
    net = Network(height="460px", width="100%", bgcolor="#ffffff", font_color="#1a1a1a", directed=True)

    for node, attrs in graph.nodes(data=True):
        role = attrs.get("role", "intermediate")
        label = attrs.get("label", short_addr(node))
        size = 32 if role == "source" else (28 if role in ("vasp", "deposit_address") else 18)
        taint = attrs.get("taint")
        title = f"Taint Decay: {taint * 100:.1f}%" if taint is not None else None
        net.add_node(node, label=label, color=NODE_COLORS.get(role, "#7f8c8d"), shape="dot", size=size, title=title)

    for src, dst, attrs in graph.edges(data=True):
        if attrs.get("priced"):
            edge_label = f"${attrs.get('usd', 0):,.0f}"
        else:
            edge_label = f"{attrs.get('amount', '')} {attrs.get('symbol', '')} ⚠️unpriced"
        if attrs.get("is_peel"):
            edge_label += " [peel]"
        
        taint_score = attrs.get("taint_score")
        color = PEEL_EDGE_COLOR if attrs.get("is_peel") else ("#e74c3c" if attrs.get("is_replay") else None)
        edge_kwargs = {
            "label": edge_label, "arrows": "to",
            "title": f"tx {attrs.get('hash', '')[:16]}... (hop {attrs.get('hop')})"
                     + (f" | taint {taint_score * 100:.0f}%" if taint_score is not None else "")
        }
        if color:
            edge_kwargs["color"] = color
        net.add_edge(src, dst, **edge_kwargs)

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

def render_graph_png(graph: nx.DiGraph) -> bytes | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from io import BytesIO

        pos = nx.spring_layout(graph, seed=42, k=0.9)
        fig, ax = plt.subplots(figsize=(9, 5))
        colors = [NODE_COLORS.get(attrs.get("role", "intermediate"), "#7f8c8d") for _, attrs in graph.nodes(data=True)]
        sizes = [700 if attrs.get("role") == "source" else (600 if attrs.get("role") in ("vasp", "deposit_address") else 250) for _, attrs in graph.nodes(data=True)]
        
        nx.draw_networkx_nodes(graph, pos, node_color=colors, node_size=sizes, ax=ax)
        nx.draw_networkx_edges(graph, pos, arrows=True, arrowsize=12, ax=ax, edge_color="#999999")
        labels = {n: attrs.get("label", short_addr(n)).split("\n")[0] for n, attrs in graph.nodes(data=True)}
        nx.draw_networkx_labels(graph, pos, labels=labels, font_size=7, ax=ax)
        ax.axis("off")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=160)
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None

def render_header():
    st.title("⚖️ CryptoFraud Trace")
    st.subheader("Real-Time Identification & Legal Attribution of Fraud-Linked VASP Endpoints")
    st.caption("SIH26183 | Ministry of Home Affairs (MHA)")

def render_sidebar(supabase_client, vasp_directory, api_key) -> dict:
    st.sidebar.write(f"**Investigator:** {st.session_state.get('auth_user')}")
    if st.sidebar.button("Log out"):
        st.session_state.auth_user = None
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("Investigation Controls")
    chain_name = st.sidebar.selectbox("Blockchain Ledger", list(CHAINS.keys()))
    max_hops = st.sidebar.slider("Traversal Max Hops", 2, 15, 6)
    max_branches = st.sidebar.slider("Branches per Mule Hop", 1, 4, 2)
    detect_sweeps = st.sidebar.checkbox("Detect Deposit Sweeps", value=True)
    exhaustive_trace = st.sidebar.checkbox("Trace all branches", value=True)
    save_case_toggle = st.sidebar.checkbox("Persist Findings to Supabase", value=True)

    with st.sidebar.expander("Admin: Sanctions Sync"):
        if st.button("Refresh Sanctions Watchlist"):
            count, err = sync_opensanctions_labels(supabase_client)
            if err:
                st.error(err)
            else:
                st.success(f"Synced {count} sanctioned addresses.")

    return {
        "chain_name": chain_name,
        "max_hops": max_hops,
        "max_branches": max_branches,
        "detect_sweeps": detect_sweeps,
        "exhaustive_trace": exhaustive_trace,
        "save_case_toggle": save_case_toggle,
    }

def _render_findings(graph, attributions, hops_reached, elapsed, api_calls,
                      suspect_wallet, chain_name, supabase_client, save_case_toggle, is_replay=False):
    components.html(render_graph(graph), height=480)

    st.subheader("Attribution & Velocity Analysis")
    top_attribution = attributions[0] if attributions else None
    conf = calculate_confidence_score(attributions, top_attribution["hop"] if top_attribution else hops_reached, hops_reached or 1)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Resolution Hops", hops_reached)
    m2.metric("Forensic Confidence", f"{conf:.0f}%" if top_attribution else "N/A")
    m3.metric("Mule Nodes Monitored", graph.number_of_nodes())
    m4.metric("Ledger Query Time", "Cached (Replay)" if is_replay else f"{elapsed:.1f}s")

    if top_attribution:
        taint_str = f" | **Taint Score:** {top_attribution.get('taint_score', 1.0) * 100:.1f}%"
        st.success(
            f"**Terminal Custody Located:** Funds channeled to **{top_attribution['vasp']}** "
            f"at hop {top_attribution['hop']} (~${top_attribution['usd']:,.2f}).\n\n"
            f"**Deposit Address:** `{top_attribution['node']}` | "
            f"**Terminal TX:** `{top_attribution.get('hash', 'N/A')}`{taint_str}"
        )
        if len(attributions) > 1:
            st.caption("Multiple terminal endpoints resolved:")
            cols = ["vasp", "hop", "amount", "symbol", "usd", "node", "taint_score"]
            st.dataframe(pd.DataFrame(attributions)[[c for c in cols if c in attributions[0]]], use_container_width=True)
    else:
        st.info("No registered VASP boundary reached within search depth.")

    if save_case_toggle and not is_replay:
        case_record = {
            "suspect_wallet": suspect_wallet, "chain": chain_name,
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
        investigator = st.session_state.get("auth_user")
        notice_text = generate_freeze_notice(suspect_wallet, chain_name, top_attribution, conf, investigator)
        st.code(notice_text, language="text")

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "📥 Download Plain Notice (.txt)", data=notice_text,
                file_name=f"FreezeNotice_{short_addr(top_attribution['node'])}.txt", mime="text/plain"
            )
        with c2:
            try:
                png = render_graph_png(graph)
                pdf_bytes = generate_freeze_notice_pdf(
                    suspect_wallet, chain_name, top_attribution, conf, investigator, png
                )
                st.download_button(
                    "📄 Download BNSS Court PDF", data=pdf_bytes,
                    file_name=f"BNSS_Section94_Order_{short_addr(top_attribution['node'])}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.caption(f"PDF engine notice: {e}")

def render_investigation_tab(settings, api_key, vasp_directory, supabase_client):
    chain_name = settings["chain_name"]
    max_hops = settings["max_hops"]
    max_branches = settings["max_branches"]
    chain_family = CHAINS[chain_name]["family"]

    example = EXAMPLE_ADDRESSES.get(chain_name, "")
    suspect_wallet = st.text_input(
        f"Victim-Reported Suspect Wallet ({chain_name})",
        value=example,
        help="Input the scam address reported on the 1930 / I4C cyber portal."
    )

    col1, col2, col3 = st.columns([1, 1.4, 3])
    with col1:
        can_trace = api_key if chain_family == "evm" else True
        trace_btn = st.button("Initiate Traversal", type="primary", disabled=not can_trace)
    with col2:
        replay_cases = list_cases()
        replay_btn = st.button("📁 Replay Benchmark Case", disabled=not replay_cases)
    with col3:
        st.caption("🔴 Drainer  ⚪ Mule  🔵 Sweep Deposit  🟢 VASP / Mixer")

    if replay_btn:
        case = replay_cases[0]
        st.warning(f"📁 **BENCHMARK REPLAY MODE** — Displaying verified record: **{case['title']}**")
        graph, attributions, _ = build_case_replay_graph(case["id"])
        hops_reached = max(attrs.get("hop", 0) for _, attrs in graph.nodes(data=True))
        _render_findings(graph, attributions, hops_reached, 0.0, 0, case["victim_wallet"], chain_name, supabase_client, False, True)
        return

    if not trace_btn:
        return

    cleaned = suspect_wallet.strip()
    detected_family = classify_address_family(cleaned)
    if detected_family != chain_family:
        st.error(f"Address format does not match selected chain {chain_name}.")
        st.stop()

    status = st.empty()
    progress_bar = st.progress(0)

    def on_progress(hop, wallet):
        progress_bar.progress(min(int(hop / max_hops * 100), 98))
        status.info(f"Traversing Hop {hop}/{max_hops}: Analyzing node `{short_addr(wallet)}`...")

    start_time = time.time()
    graph, attributions, calls_made = trace_fund_flow(
        cleaned, chain_name, api_key, vasp_directory,
        max_hops=max_hops, max_branches=max_branches,
        exhaustive_trace=settings["exhaustive_trace"],
        detect_sweeps=settings["detect_sweeps"],
        progress_cb=on_progress,
    )
    elapsed = time.time() - start_time
    status.empty()
    progress_bar.empty()

    if graph.number_of_edges() == 0:
        st.warning("No outgoing transactions discovered on this ledger.")
        st.stop()

    hops_reached = max(attrs.get("hop", 0) for _, attrs in graph.nodes(data=True))
    _render_findings(graph, attributions, hops_reached, elapsed, calls_made, cleaned, chain_name, supabase_client, settings["save_case_toggle"])

def render_case_history_tab(supabase_client):
    st.subheader("Persistent Case Repository")
    records, error = fetch_recent_cases(supabase_client)
    if error:
        st.warning(error)
        return
    if not records:
        st.info("No prior cases logged.")
        return
    st.dataframe(pd.DataFrame(records), use_container_width=True)

def render_protocols_tab():
    st.subheader("Standard Operating Procedures for Investigating Officers")
    st.markdown("""
    1. **Primary Validation:** Cross-reference victim transaction hashes on public explorers before initiating graph traversal.
    2. **Taint Scoring:** Haircut model calculates fund decay across commingled pools; cite decay factor as supporting evidence.
    3. **Legal Compliance:** Dispatch generated Section 94 BNSS orders directly to registered Nodal Compliance Officers via FIU-IND communication rails.
    4. **Subpoena for KYC:** Requisition KYC identification records under PMLA Section 17 following account restraint.
    """)
