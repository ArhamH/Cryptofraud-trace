import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components
import tempfile

st.set_page_config(
    page_title="CryptoFraud Trace", 
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ CryptoFraud Trace — Law Enforcement Portal")
st.caption("Ministry of Home Affairs | SIH Problem Statement SIH26183")

# Input Section
col1, col2 = st.columns([3, 1])
with col1:
    suspect_wallet = st.text_input(
        "Enter Suspect Wallet Address (Victim Reported):",
        value="0x71C39a824e...9f3D"
    )
with col2:
    st.write("")
    st.write("")
    trace_btn = st.button("🚀 Trace Fund Flow", use_container_width=True)

if trace_btn:
    st.markdown("---")
    st.subheader("🕸️ Multi-Hop Transaction Graph")
    st.caption("Physics-based flow reconstruction: Drag nodes or scroll to zoom.")

    # Initialize Pyvis Network
    net = Network(height="540px", width="100%", bgcolor="#12131C", font_color="white", directed=True)

    # Spread physics configuration to prevent node bunching
    net.force_atlas_2based(
        gravity=-120, 
        central_gravity=0.005, 
        spring_length=220, 
        spring_strength=0.04,
        damping=0.9
    )

    # 1. Flagged Suspect Wallet (Red)
    net.add_node(
        "A", 
        label="Suspect Wallet\n(Victim Lead)", 
        color="#E63946", 
        size=26, 
        shape="box",
        font={"face": "Helvetica", "size": 14, "color": "#FFFFFF"},
        title="Reported Origin Wallet"
    )

    # 2. Intermediate Wallets (Muted Slate)
    net.add_node(
        "B", 
        label="Wallet B\n(Hop 1 Hub)", 
        color="#4A5568", 
        size=20, 
        shape="dot",
        font={"face": "Helvetica", "size": 12, "color": "#E2E8F0"},
        title="Primary Splitting Node"
    )
    net.add_node(
        "C1", 
        label="Wallet C1\n(Mixer Splice)", 
        color="#4A5568", 
        size=18, 
        shape="dot",
        font={"face": "Helvetica", "size": 12, "color": "#E2E8F0"},
        title="Layer 2 Intermediate"
    )
    net.add_node(
        "C2", 
        label="Wallet C2\n(Layer 2)", 
        color="#4A5568", 
        size=18, 
        shape="dot",
        font={"face": "Helvetica", "size": 12, "color": "#E2E8F0"},
        title="Layer 2 Intermediate"
    )
    net.add_node(
        "C3", 
        label="Wallet C3\n(Mule Holding)", 
        color="#4A5568", 
        size=18, 
        shape="dot",
        font={"face": "Helvetica", "size": 12, "color": "#E2E8F0"},
        title="Stagnant Balance"
    )

    # 3. Final Identified Exchange (Green)
    net.add_node(
        "D", 
        label="Exchange Deposit\n[BINANCE HOT-WALLET]", 
        color="#06D6A0", 
        size=30, 
        shape="box",
        font={"face": "Helvetica", "size": 15, "color": "#0B132B"},
        title="Attributed Regulated VASP"
    )

    # Function to create clean non-overlapping edges with labels on top
    def add_edge_clean(src, dst, hop_text, stroke_color="#A0AEC0", width=2):
        net.add_edge(
            src, 
            dst, 
            label=hop_text, 
            color=stroke_color, 
            width=width,
            arrows="to",
            font={
                "align": "top",          # Text line ke theek upar baithega
                "size": 11, 
                "color": "#F7FAFC", 
                "strokeWidth": 2,        # Background halo taaki line text ko na kaate
                "strokeColor": "#12131C"
            }
        )

    # Add edges with clear above-line annotations
    add_edge_clean("A", "B", "Hop 1: 4.20 ETH", stroke_color="#CBD5E0", width=3)
    add_edge_clean("B", "C1", "Hop 2a: 2.10 ETH")
    add_edge_clean("B", "C2", "Hop 2b: 1.50 ETH")
    add_edge_clean("B", "C3", "Hop 2c: 0.60 ETH")
    add_edge_clean("C1", "D", "Hop 3: 2.10 ETH Deposit", stroke_color="#06D6A0", width=3)
    add_edge_clean("C2", "D", "Hop 3: 1.50 ETH Deposit", stroke_color="#06D6A0", width=3)

    # Render HTML through temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
        net.save_graph(tmp_file.name)
        with open(tmp_file.name, "r", encoding="utf-8") as f:
            html_content = f.read()

    components.html(html_content, height=560)

    # Intelligence & Summary Panel
    st.success("✅ **Attribution Match:** Identified Destination VASP: **Binance (KYC Enforced)**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric(label="Hops Traversed", value="3 Hops")
    c2.metric(label="Attribution Confidence", value="98.4%")
    c3.metric(label="Target Jurisdiction", value="Binance Global / FIU-IND")

    # Freeze Notice Export
    notice_text = (
        f"LEGAL FREEZE NOTICE (Section 91 CrPC / FIU-IND Compliance)\n"
        f"----------------------------------------------------------\n"
        f"Case Lead Wallet : {suspect_wallet}\n"
        f"Target VASP      : Binance Centralized Deposit Cluster\n"
        f"Identified Trace : 3 Hops via intermediate mixer clusters\n"
        f"Action Required  : Freeze corresponding account IDs and hold balances.\n"
    )
    st.download_button(
        label="📄 Download Freeze Notice (I4C Ready)",
        data=notice_text,
        file_name="Freeze_Notice_Binance.txt",
        mime="text/plain",
        use_container_width=True
    )
        color="#FF4B4B", 
        size=25, 
        shape="box",
        title="Flagged: Fraudulent Drainer Wallet"
    )

    # 2. Intermediate Wallets (GREY / BLUE ACCENT)
    net.add_node("B", label="Wallet B\n(Layer 1)", color="#6c757d", size=18, shape="dot")
    net.add_node("C1", label="Wallet C1\n(Mixer Splice)", color="#6c757d", size=18, shape="dot")
    net.add_node("C2", label="Wallet C2\n(Layer 2)", color="#6c757d", size=18, shape="dot")
    net.add_node("C3", label="Wallet C3\n(Mule)", color="#6c757d", size=18, shape="dot")

    # 3. Target Exchange / VASP (GREEN)
    net.add_node(
        "D", 
        label="Exchange Deposit\n[BINANCE HOT-WALLET]", 
        color="#00C853", 
        size=30, 
        shape="box",
        title="VASP Identified: Binance Centralized Deposit"
    )

    # Add Edges (Hops with transaction details)
    net.add_edge("A", "B", label="hop 1 (4.2 ETH)", color="#ffffff", width=2)
    net.add_edge("B", "C1", label="hop 2a (2.1 ETH)", color="#aaaaaa")
    net.add_edge("B", "C2", label="hop 2b (1.5 ETH)", color="#aaaaaa")
    net.add_edge("B", "C3", label="hop 2c (0.6 ETH)", color="#aaaaaa")
    net.add_edge("C1", "D", label="hop 3 (Final Deposit)", color="#00E676", width=2)
    net.add_edge("C2", "D", label="hop 3 (Final Deposit)", color="#00E676", width=2)

    # Render to HTML
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
        net.save_graph(tmp_file.name)
        with open(tmp_file.name, "r", encoding="utf-8") as f:
            html_content = f.read()

    # Display inside Streamlit
    components.html(html_content, height=520)

    # Action Summary Bar for LEA
    st.success("✅ **Attribution Match:** Identified Destination VASP: **Binance (KYC Enforced)**")
    
    colA, colB, colC = st.columns(3)
    colA.metric("Hops Traversed", "3 Hops")
    colB.metric("Confidence Score", "98.4%")
    colC.metric("Target Exchange", "Binance IN / Global")

    # Freeze Notice Download Mock Button
    st.download_button(
        label="📄 Download Ready-to-Serve Freeze Notice (I4C Standard)",
        data=f"LEGAL FREEZE NOTICE\nCase: Cyber Fraud\nSuspect: {suspect_wallet}\nTarget VASP: Binance\nAction: Immediate account freeze requested under Section 91 CrPC / PMLA.",
        file_name="Freeze_Notice_Binance.txt",
        mime="text/plain"
    )
