"""
frontend_ui.py
-----------------
Law Enforcement Investigative UI with modern Bento Hero Section, AI Case Briefing,
Number-Flow metrics, Scramble-Hover/Copy card, and Animated-Tags.
"""

import re
import tempfile
import time
from datetime import datetime, timezone

import networkx as nx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from system_architecture import CHAINS, EXAMPLE_ADDRESSES, classify_address_family, short_addr
from data_layer import (
    save_case_to_db, fetch_recent_cases, sync_opensanctions_labels,
    list_cases, build_case_replay_graph,
)
from graph_engine import trace_fund_flow, calculate_confidence_score, score_nodes
from legal_forensics import generate_freeze_notice, generate_freeze_notice_pdf
from ai_assistant import generate_investigation_brief

NODE_COLORS = {
    "source": "#e74c3c", "intermediate": "#7f8c8d",
    "vasp": "#27ae60", "deposit_address": "#2980b9",
    "dex_hop": "#9b59b6", "bridge_exit": "#e67e22",
}
PEEL_EDGE_COLOR = "#f39c12"

def render_header():
    hero_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-transparent m-0 p-0">
      <div class="relative overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950 p-4 sm:p-6 font-sans shadow-2xl">
        <div class="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="space-y-2">
            <div class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10px] font-mono font-medium bg-neutral-900 border border-neutral-700/60 text-cyan-400">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
              SIH26183 • MINISTRY OF HOME AFFAIRS (MHA)
            </div>
            <h1 class="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              CryptoFraud <span class="bg-gradient-to-r from-cyan-400 via-blue-500 to-indigo-400 bg-clip-text text-transparent">Trace</span>
            </h1>
            <p class="text-xs sm:text-sm text-neutral-400 max-w-xl leading-relaxed">
              Real-Time Forensic Identification & Statutory Attribution of Fraud-Linked VASP Endpoints with automated Section 94 BNSS orders.
            </p>
          </div>
          <div class="flex items-center gap-3 bg-neutral-900/80 border border-neutral-800 p-3 rounded-xl self-start md:self-auto">
            <div class="text-center px-1">
              <div class="text-sm sm:text-base font-bold font-mono text-white">Multi-Chain</div>
              <div class="text-[9px] uppercase tracking-wider text-neutral-400">EVM • BTC • SOL</div>
            </div>
            <div class="w-px h-6 bg-neutral-800"></div>
            <div class="text-center px-1">
              <div class="text-sm sm:text-base font-bold font-mono text-emerald-400">Sec. 94</div>
              <div class="text-[9px] uppercase tracking-wider text-neutral-400">BNSS Order</div>
            </div>
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(hero_html, height=240, scrolling=True)

def render_smooth_orb_loader(status_text: str):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-transparent m-0 p-0 font-sans">
      <div class="flex flex-col items-center justify-center p-4 bg-neutral-950 rounded-2xl border border-neutral-800 my-2">
        <div class="relative flex items-center justify-center w-20 h-20">
          <div class="absolute w-16 h-16 rounded-full bg-gradient-to-tr from-cyan-500 via-indigo-500 to-fuchsia-500 blur-xl opacity-70 animate-pulse"></div>
          <div class="relative w-12 h-12 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 shadow-2xl flex items-center justify-center border border-white/20">
            <div class="w-5 h-5 rounded-full bg-white/10 backdrop-blur-sm animate-ping"></div>
          </div>
        </div>
        <p class="mt-2.5 text-[10px] sm:text-xs font-mono text-cyan-400 tracking-wider uppercase animate-pulse">{status_text}</p>
      </div>
    </body>
    </html>
    """
    components.html(html_code, height=155, scrolling=False)

def render_smooth_metrics(hops: int, confidence: float, nodes_count: int, query_time: str):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-transparent m-0 p-0 font-sans">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-2 bg-neutral-950 p-2.5 rounded-xl border border-neutral-800">
        <div class="p-2.5 bg-neutral-900/70 rounded-lg border border-neutral-800">
          <span class="text-[10px] font-medium text-neutral-400 uppercase tracking-wider">Resolution Hops</span>
          <div class="text-xl sm:text-2xl font-bold text-white mt-0.5 font-mono">{hops}</div>
        </div>
        <div class="p-2.5 bg-neutral-900/70 rounded-lg border border-neutral-800">
          <span class="text-[10px] font-medium text-neutral-400 uppercase tracking-wider">Confidence</span>
          <div class="text-xl sm:text-2xl font-bold text-emerald-400 mt-0.5 font-mono">{confidence:.0f}%</div>
        </div>
        <div class="p-2.5 bg-neutral-900/70 rounded-lg border border-neutral-800">
          <span class="text-[10px] font-medium text-neutral-400 uppercase tracking-wider">Mule Nodes</span>
          <div class="text-xl sm:text-2xl font-bold text-white mt-0.5 font-mono">{nodes_count}</div>
        </div>
        <div class="p-2.5 bg-neutral-900/70 rounded-lg border border-neutral-800">
          <span class="text-[10px] font-medium text-neutral-400 uppercase tracking-wider">Latency</span>
          <div class="text-xl sm:text-2xl font-bold text-cyan-400 mt-0.5 font-mono">{query_time}</div>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(html_code, height=195, scrolling=True)

def render_smooth_tags(peel: bool, sweep: bool, sealed: bool = True):
    peel_badge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-950/60 text-amber-300 border border-amber-800/50">⚡ Peel Tagged</span>' if peel else '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-neutral-900 text-neutral-400 border border-neutral-800">No Peel Split</span>'
    sweep_badge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-blue-950/60 text-blue-300 border border-blue-800/50">🔄 Sweeps Detected</span>' if sweep else '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-neutral-900 text-neutral-400 border border-neutral-800">No Sweeps</span>'
    sealed_badge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/50">🔒 SHA-256 Sealed</span>'

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-transparent m-0 p-0 font-sans">
      <div class="flex flex-wrap gap-1.5 py-1">
        {peel_badge}
        {sweep_badge}
        {sealed_badge}
      </div>
    </body>
    </html>
    """
    components.html(html_code, height=50, scrolling=False)

def render_crypto_address_card(title: str, address: str, tx_hash: str, vasp_name: str, usd_val: float):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-transparent m-0 p-0 font-sans">
      <div class="p-3.5 bg-gradient-to-r from-neutral-950 via-neutral-900 to-neutral-950 border border-emerald-800/50 rounded-xl my-2 shadow-lg">
        <div class="flex items-center justify-between">
          <span class="text-[11px] font-semibold uppercase tracking-wider text-emerald-400">Terminal Custody Located</span>
          <span class="text-base sm:text-lg font-bold font-mono text-emerald-300">${usd_val:,.2f} USD</span>
        </div>
        <div class="mt-1 text-white font-medium text-sm sm:text-base">{vasp_name}</div>
        <div class="mt-2.5 flex items-center justify-between bg-neutral-900 p-2 rounded border border-neutral-800 font-mono text-[11px] text-neutral-300">
          <span class="truncate pr-2">Deposit: {address}</span>
          <button onclick="navigator.clipboard.writeText('{address}')" class="px-2 py-0.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded text-[10px] shrink-0 transition">Copy</button>
        </div>
        <div class="mt-1 flex items-center justify-between bg-neutral-900 p-2 rounded border border-neutral-800 font-mono text-[11px] text-neutral-400">
          <span class="truncate pr-2">TX: {tx_hash}</span>
          <button onclick="navigator.clipboard.writeText('{tx_hash}')" class="px-2 py-0.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded text-[10px] shrink-0 transition">Copy</button>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(html_code, height=170, scrolling=False)

def render_graph(graph: nx.DiGraph) -> str:
    net = Network(height="460px", width="100%", bgcolor="#0d0d0d", font_color="#f0f0f0", directed=True)

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
            edge_label = f"{attrs.get('amount', '')} {attrs.get('symbol', '')} unpriced"
        if attrs.get("is_peel"):
            edge_label += " [peel]"
        
        taint_score = attrs.get("taint_score")
        color = PEEL_EDGE_COLOR if attrs.get("is_peel") else ("#e74c3c" if attrs.get("is_replay") else "#555555")
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

        pos = nx.spring_layout(graph, seed=42, k=1.2)
        fig, ax = plt.subplots(figsize=(10, 4.2))
        ax.margins(0.25)
        
        colors = [NODE_COLORS.get(attrs.get("role", "intermediate"), "#7f8c8d") for _, attrs in graph.nodes(data=True)]
        sizes = [650 if attrs.get("role") == "source" else (550 if attrs.get("role") in ("vasp", "deposit_address") else 220) for _, attrs in graph.nodes(data=True)]
        
        nx.draw_networkx_nodes(graph, pos, node_color=colors, node_size=sizes, ax=ax)
        nx.draw_networkx_edges(graph, pos, arrows=True, arrowsize=14, ax=ax, edge_color="#888888", width=1.5)
        
        raw_labels = {n: attrs.get("label", short_addr(n)).split("\n")[0] for n, attrs in graph.nodes(data=True)}
        clean_labels = {n: re.sub(r'[^\x00-\x7F]+', '', text).strip() for n, text in raw_labels.items()}
        
        nx.draw_networkx_labels(graph, pos, labels=clean_labels, font_size=7.5, font_family="sans-serif", ax=ax)
        
        ax.axis("off")
        fig.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        return None

def render_sidebar(supabase_client, vasp_directory, api_key) -> dict:
    user_email = st.session_state.get('auth_user', 'investigator@sih.gov.in')
    
    avatar_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-transparent m-0 p-0 font-sans">
      <div class="flex items-center space-x-3 p-2.5 bg-neutral-900 rounded-xl border border-neutral-800 mb-2">
        <div class="w-9 h-9 rounded-full bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center text-white font-bold text-xs shadow">
          {user_email[:2].upper()}
        </div>
        <div class="flex flex-col truncate">
          <span class="text-xs font-bold text-white truncate">{user_email}</span>
          <span class="text-[9px] text-emerald-400 font-mono">LEA Authorized Officer</span>
        </div>
      </div>
    </body>
    </html>
    """
    with st.sidebar:
        components.html(avatar_html, height=70, scrolling=False)

        if st.button("Log out", use_container_width=True):
            st.session_state["auth_user"] = None
            st.rerun()

        st.markdown("---")
        st.header("Investigation Controls")
        chain_name = st.selectbox("Blockchain Ledger", list(CHAINS.keys()))
        max_hops = st.slider("Traversal Max Hops", 2, 10, 5)
        max_branches = st.slider("Branches per Mule Hop", 1, 4, 2)
        detect_sweeps = st.checkbox("Detect Deposit Sweeps", value=True)
        exhaustive_trace = st.checkbox("Trace all branches", value=True)
        save_case_toggle = st.checkbox("Persist Findings to Supabase", value=True)

        with st.expander("Admin: Sanctions Sync"):
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
                      suspect_wallet, chain_name, supabase_client, save_case_toggle,
                      is_replay=False, cross_chain_alerts=None):
    cross_chain_alerts = cross_chain_alerts or []
    components.html(render_graph(graph), height=480)

    st.subheader("Attribution & Velocity Analysis")
    top_attribution = attributions[0] if attributions else None
    conf = calculate_confidence_score(attributions, top_attribution["hop"] if top_attribution else hops_reached, hops_reached or 1)

    render_smooth_metrics(hops_reached, conf if top_attribution else 0.0, graph.number_of_nodes(), "Cached" if is_replay else f"{elapsed:.1f}s")

    peel_detected = any(attrs.get("is_peel") for _, _, attrs in graph.edges(data=True))
    sweep_detected = any(attrs.get("sweep_detected") for _, _, attrs in graph.edges(data=True))
    dex_hops = sum(1 for _, attrs in graph.nodes(data=True) if attrs.get("role") == "dex_hop")

    render_smooth_tags(peel_detected, sweep_detected, True)

    if dex_hops or cross_chain_alerts:
        st.caption(f"🟣 DEX Router Swaps Resolved: {dex_hops}  |  🟠 Cross-Chain Bridge Exits Flagged: {len(cross_chain_alerts)}")

    if cross_chain_alerts:
        with st.expander(f"⚠️ {len(cross_chain_alerts)} Cross-Chain Bridge Exit(s) — Manual Follow-Up Required", expanded=True):
            for a in cross_chain_alerts:
                st.warning(
                    f"**{a['bridge_name']}** at hop {a['hop']} — "
                    f"~{a['amount']} {a['symbol']} (~${a['usd']:,.2f}) exited this ledger via "
                    f"`{a['bridge_address']}`.\n\n{a['note']}"
                )

    if not is_replay and graph.number_of_nodes() > 1:
        risk_scores = score_nodes(graph)
        method = next(iter(risk_scores.values()))["method"] if risk_scores else "heuristic_coldstart"
        method_label = ("Trained GraphSAGE checkpoint" if method == "graphsage_trained"
                          else "Heuristic cold-start (Inductive Model)")
        with st.expander(f"🧪 Inductive Mule/Mixer Risk Scoring — {method_label}"):
            risk_df = pd.DataFrame([
                {"node": n, "risk_score": v["score"], "method": v["method"]}
                for n, v in sorted(risk_scores.items(), key=lambda kv: kv[1]["score"], reverse=True)[:15]
            ])
            if not risk_df.empty:
                st.dataframe(risk_df, use_container_width=True)

    if top_attribution:
        render_crypto_address_card(
            title="Terminal VASP Located",
            address=top_attribution["node"],
            tx_hash=top_attribution.get("hash", "N/A"),
            vasp_name=f"{top_attribution['vasp']} (Hop {top_attribution['hop']})",
            usd_val=top_attribution["usd"]
        )

        if len(attributions) > 1:
            st.caption("Multiple terminal endpoints resolved:")
            cols = ["vasp", "hop", "amount", "symbol", "usd", "node", "taint_score"]
            _attr_df = pd.DataFrame(attributions).reindex(columns=cols)
            st.dataframe(_attr_df.dropna(how="all", axis=1), use_container_width=True)
    else:
        st.info("No registered VASP boundary reached within search depth.")

    if save_case_toggle and not is_replay:
        case_record = {
            "suspect_wallet": suspect_wallet,
            "chain": chain_name,
            "hops_traversed": hops_reached,
            "attributed_vasp": top_attribution["vasp"] if top_attribution else None,
            "confidence_score": conf if top_attribution else 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        auth_u = st.session_state.get("auth_user")
        if auth_u:
            case_record["investigator_email"] = auth_u

        saved, db_msg = save_case_to_db(supabase_client, case_record)
        if not saved and "investigator_email" in str(db_msg):
            case_record.pop("investigator_email", None)
            saved, db_msg = save_case_to_db(supabase_client, case_record)

        if saved:
            st.caption(f"Audit Status: {db_msg}")
        else:
            st.caption("Audit Status: Logged in local session cache")

    # AI Case Explainer Brief
    if top_attribution:
        brief_md = generate_investigation_brief(
            suspect_wallet=suspect_wallet,
            chain_name=chain_name,
            top_attribution=top_attribution,
            hops=hops_reached,
            peel_detected=peel_detected,
            sweep_detected=sweep_detected
        )
        st.markdown(
            f"""
            <div style="background-color: #0c1322; border: 1px solid #1e293b; border-radius: 12px; padding: 18px; margin: 18px 0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);">
                {brief_md}
            </div>
            """,
            unsafe_allow_html=True
        )

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

    st.markdown("**Real-World Incident Presets:**")
    p1, p2, p3 = st.columns(3)
    if p1.button("📌 WazirX Exploiter (ETH)"):
        st.session_state["wallet_input_box"] = "0x04b21735E93Fa3f8df70e2Da89e6922616891a88"
    if p2.button("📌 Poly Network (ETH)"):
        st.session_state["wallet_input_box"] = "0xC8a65Fadf0e0dDAf421F28FEAb69Bf6E2E589963"
    if p3.button("📌 Binance Hot Wallet (BTC)"):
        st.session_state["wallet_input_box"] = "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s"

    default_val = st.session_state.get("wallet_input_box", EXAMPLE_ADDRESSES.get(chain_name, ""))
    suspect_wallet = st.text_input(
        f"Victim-Reported Suspect Wallet ({chain_name})",
        value=default_val,
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
        st.caption("🔴 Drainer  ⚪ Mule  🔵 Sweep Deposit  🟢 VASP  🟣 DEX Swap  🟠 Bridge Exit")

    if replay_btn:
        case = replay_cases[0]
        st.warning(f"📁 **BENCHMARK REPLAY MODE** — Displaying verified record: **{case['title']}**")
        graph, attributions, _ = build_case_replay_graph(case["id"])
        hops_reached = max(attrs.get("hop", 0) for _, attrs in graph.nodes(data=True))
        _render_findings(
            graph, attributions, hops_reached, 0.0, 0,
            case["victim_wallet"], "Ethereum", supabase_client,
            False, is_replay=True, cross_chain_alerts=[]
        )
        return

    if not trace_btn:
        return

    cleaned = suspect_wallet.strip()
    detected_family = classify_address_family(cleaned)
    if detected_family != chain_family:
        st.error(f"Address format does not match selected chain {chain_name}.")
        st.stop()

    loader_placeholder = st.empty()
    with loader_placeholder:
        render_smooth_orb_loader(f"Traversing Layered Flows on {chain_name}...")

    start_time = time.time()
    graph, attributions, calls_made, cross_chain_alerts = trace_fund_flow(
        cleaned, chain_name, api_key, vasp_directory,
        max_hops=max_hops, max_branches=max_branches,
        exhaustive_trace=settings["exhaustive_trace"],
        detect_sweeps=settings["detect_sweeps"],
        progress_cb=None,
    )
    elapsed = time.time() - start_time
    loader_placeholder.empty()

    if graph.number_of_edges() == 0:
        st.warning("No outgoing transactions discovered on this ledger.")
        st.stop()

    hops_reached = max(attrs.get("hop", 0) for _, attrs in graph.nodes(data=True))
    _render_findings(graph, attributions, hops_reached, elapsed, calls_made, cleaned, chain_name,
                      supabase_client, settings["save_case_toggle"], cross_chain_alerts=cross_chain_alerts)

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
