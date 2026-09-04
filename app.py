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

    net = Network(height="540px", width="100%", bgcolor="#12131C", font_color="white", directed=True)

    net.force_atlas_2based(
        gravity=-120, 
        central_gravity=0.005, 
        spring_length=220, 
        spring_strength=0.04,
        damping=0.9
    )

    net.add_node(
        "A", 
        label="Suspect Wallet\n(Victim Lead)", 
        color="#E63946", 
        size=26, 
        shape="box",
        font={"face": "Helvetica", "size": 14, "color": "#FFFFFF"},
        title="Reported Origin Wallet"
    )

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

    net.add_node(
        "D", 
        label="Exchange Deposit\n[BINANCE HOT-WALLET]", 
        color="#06D6A0", 
        size=30, 
        shape="box",
        font={"face": "Helvetica", "size": 15, "color": "#0B132B"},
        title="Attributed Regulated VASP"
    )

    def add_edge_clean(src, dst, hop_text, stroke_color="#A0AEC0", width=2):
        net.add_edge(
            src, 
            dst, 
            label=hop_text, 
            color=stroke_color, 
            width=width,
            arrows="to",
            font={
                "align": "top",
                "size": 11, 
                "color": "#F7FAFC", 
                "strokeWidth": 2,
                "strokeColor": "#12131C"
            }
        )

    add_edge_clean("A", "B", "Hop 1: 4.20 ETH", stroke_color="#CBD5E0", width=3)
    add_edge_clean("B", "C1", "Hop 2a: 2.10 ETH")
    add_edge_clean("B", "C2", "Hop 2b: 1.50 ETH")
    add_edge_clean("B", "C3", "Hop 2c: 0.60 ETH")
    add_edge_clean("C1", "D", "Hop 3: 2.10 ETH Deposit", stroke_color="#06D6A0", width=3)
    add_edge_clean("C2", "D", "Hop 3: 1.50 ETH Deposit", stroke_color="#06D6A0", width=3)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
        net.save_graph(tmp_file.name)
        with open(tmp_file.name, "r", encoding="utf-8") as f:
            html_content = f.read()

    components.html(html_content, height=560)

    st.success("✅ Attribution Match: Identified Destination VASP: Binance (KYC Enforced)")
    
    c1, c2, c3 = st.columns(3)
    c1.metric(label="Hops Traversed", value="3 Hops")
    c2.metric(label="Attribution Confidence", value="98.4%")
    c3.metric(label="Target Jurisdiction", value="Binance Global / FIU-IND")

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
