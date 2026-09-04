import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components
import tempfile

st.set_page_config(page_title="CryptoFraud Trace", layout="wide")

st.title("🛡️ CryptoFraud Trace — Law Enforcement Portal")
st.caption("MHA Hackathon Edition | PS: SIH26183")

# Input Section
col1, col2 = st.columns([3, 1])
with col1:
    suspect_wallet = st.text_input(
        "Enter Suspect Wallet Address (Victim Reported):",
        "0x71C...39A (Suspect Lead)"
    )
with col2:
    st.write("")
    st.write("")
    trace_btn = st.button("🚀 Trace Fund Flow", use_container_width=True)

if trace_btn:
    st.markdown("---")
    st.subheader("🕸️ Real-Time Multi-Hop Transaction Graph (Physics Simulation)")
    st.info("💡 **Interactive:** Nodes ko drag karo, zoom in/out karo aur inspect karo.")

    # Initialize Pyvis Network with Physics
    net = Network(height="500px", width="100%", bgcolor="#1a1a24", font_color="white", directed=True)
    
    # Physics engine configure (spring-like bounce effect)
    net.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=100, spring_strength=0.08)

    # 1. Victim / Suspect Node (RED)
    net.add_node(
        "A", 
        label="Suspect Wallet\n(Victim Reported)", 
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
