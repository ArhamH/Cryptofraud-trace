"""
system_architecture.py
------------------------
Core configuration, API endpoints, address classifiers, and seed VASP directories.
"""

import os
import re
import streamlit as st

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

def _cfg(key: str, default: str) -> str:
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

MEMPOOL_BASE = _cfg("MEMPOOL_BASE", "https://mempool.space/api")
SOLANA_RPC = _cfg("SOLANA_RPC", "https://api.mainnet-beta.solana.com")

def get_api_key() -> str:
    try:
        if "ETHERSCAN_API_KEY" in st.secrets:
            return st.secrets["ETHERSCAN_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ETHERSCAN_API_KEY", "")

CHAINS = {
    "Ethereum":        {"family": "evm", "chain_id": 1,   "native_symbol": "ETH"},
    "BNB Smart Chain": {"family": "evm", "chain_id": 56,  "native_symbol": "BNB"},
    "Polygon":         {"family": "evm", "chain_id": 137, "native_symbol": "MATIC"},
    "Bitcoin":         {"family": "btc"},
    "Solana":          {"family": "solana"},
}

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
BTC_RE = re.compile(r"^(1|3)[a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-zA-HJ-NP-Z0-9]{25,59}$")
SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

EXAMPLE_ADDRESSES = {
    "Ethereum": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "BNB Smart Chain": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "Polygon": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "Bitcoin": "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s",
    "Solana": "",
}

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

DEFAULT_VASP_BTC = {
    "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s": "Binance (BTC Hot Wallet, deprecated)",
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance (BTC Cold Wallet)",
}

DEFAULT_VASP_SOL = {}

IGNORED_CONTRACTS = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "0x4fabb145d64652a948d72533023f6e7a623c7c53",
}

SANCTIONED_EVM = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda0": "Tornado Cash Router",
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": "Tornado Cash: Router v2",
    "0x0836222f2b2b24a3f36f98668ed8f0b38d1a872f": "Lazarus Group (attributed)",
    "0x03893a7c7463ae47d46bad2531f938da4e63d9d6": "Lazarus Group (attributed)",
}
SANCTIONED_EVM = {k.lower(): v for k, v in SANCTIONED_EVM.items()}

PEEL_SKIM_MIN_SHARE = 0.01
PEEL_SKIM_MAX_SHARE = 0.15
SWEEP_WINDOW_SECONDS = 6 * 3600
SWEEP_MIN_FORWARD_RATIO = 0.90

STABLES = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "USDP", "FDUSD"}
STATIC_BASE_PRICES = {
    "ETH": 3400.0, "BNB": 580.0, "MATIC": 0.42, "POL": 0.42,
    "BTC": 64000.0, "SOL": 150.0, "USDT": 1.0, "USDC": 1.0, "DAI": 1.0
}

DEX_ROUTERS_EVM = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Router 2",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch Aggregation Router V5",
    "0x111111125421ca6dc452d289314280a0f8842a65": "1inch Aggregation Router V6",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap Router",
    "0x10ed43c718714eb63d5aa57b78b54704e256024e": "PancakeSwap V2 Router (BSC)",
}
DEX_ROUTERS_EVM = {k.lower(): v for k, v in DEX_ROUTERS_EVM.items()}

BRIDGE_CONTRACTS_EVM = {
    "0x8731d54e9d02c286767d56ac03e8037c07e01e8": "Stargate Finance Router",
    "0x150f94b44927f078737562f0fcf3c95c01cc2376": "Stargate Finance Router (v2)",
    "0x3ee18b2214aff97000d974cf647e7c347e8fa585": "Wormhole Token Bridge",
    "0x765277eebeca2e31912c9946eae1021199b39c61": "Wormhole Token Bridge (v2)",
}
BRIDGE_CONTRACTS_EVM = {k.lower(): v for k, v in BRIDGE_CONTRACTS_EVM.items()}

EVENT_TOPICS = {
    "ERC20_TRANSFER": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    "UNISWAP_V2_SWAP": "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822",
    "UNISWAP_V3_SWAP": "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
}

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
