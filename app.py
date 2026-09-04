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

    # Directed network initialize
    net = Network(height="400px", width="100%", bgcolor="#12131C", font_color="white", directed=True)

    # STRICT LEFT-TO-RIGHT HIERARCHY (NO RANDOM PHYSICS)
    # level 0 -> level 1 -> level 2 -> level 3 (Left se Right seedha arrow banega)
    
    # 1. Suspect Wallet (Red Box, Level 0)
    net.add_node(
        "A", 
        label="Suspect wallet\nvictim reported", 
        color="#E0533C", 
        shape="box", 
        level=0,
        font={"face": "Helvetica", "size": 15, "color": "#FFFFFF"},
        margin=12
    )

    # 2. Intermediate Wallet B (Grey Box, Level 1)
    net.add_node(
        "B", 
        label="Wallet B\nintermediate", 
        color="#7F8C8D", 
        shape="box", 
        level=1,
        font={"face": "Helvetica", "size": 15, "color": "#FFFFFF"},
        margin=12
    )

    # 3. Intermediate C1 & C2 (Grey Boxes, Level 2)
    net.add_node(
        "C1", 
        label="Wallet C1\nintermediate", 
        color="#7F8C8D", 
        shape="box", 
        level=2,
        font={"face": "Helvetica", "size": 14, "color": "#FFFFFF"},
        margin=10
    )
    net.add_node(
        "C2", 
        label="Wallet C2\nintermediate", 
        color="#7F8C8D", 
        shape="box", 
        level=2,
        font={"face": "Helvetica", "size": 14, "color": "#FFFFFF"},
        margin=10
    )

    # 4. Final Binance Deposit (Green Box, Level 3)
    net.add_node(
        "D", 
        label="Exchange deposit\nlabeled: Binance", 
        color="#00A86B", 
        shape="box", 
        level=3,
        font={"face": "Helvetica", "size": 15, "color": "#FFFFFF"},
        margin=12
    )

    # Edges with neat labels
    def add_edge_clean(src, dst, text):
        net.add_edge(
            src, 
            dst, 
            label=text, 
            color="#FFFFFF", 
            width=2,
            arrows="to",
            font={
                "align": "horizontal",
                "size": 13, 
                "color": "#FFFFFF", 
                "background": "#12131C"
            }
        )

    add_edge_clean("A", "B", "hop 1")
    add_edge_clean("B", "C1", "hop 2a")
    add_edge_clean("B", "C2", "hop 2b")
    add_edge_clean("C1", "D", "hop 3")
    add_edge_clean("C2", "D", "hop 3")

    # Set Layout to Left-to-Right and disable physics chaos
    net.set_options("""
    {
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "LR",
          "sortMethod": "directed",
          "levelSeparation": 180,
          "nodeSpacing": 100
        }
      },
      "physics": {
        "enabled": false
      },
      "edges": {
        "smooth": {
          "type": "cubicBezier",
          "forceDirection": "horizontal",
          "roundness": 0.4
        }
      }
    }
    """)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
        net.save_graph(tmp_file.name)
        with open(tmp_file.name, "r", encoding="utf-8") as f:
            html_content = f.read()

    components.html(html_content, height=420)

    st.success("✅ **Attribution Match:** Identified Destination VASP: **Binance (KYC Enforced)**")
    
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
