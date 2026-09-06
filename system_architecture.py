"""
system_architecture.py
------------------------
Role: Full-Stack & System Architect (Arham Hasan, Team Leader)

Core configuration and constants that the rest of the app is built on:
API endpoints, the chain registry, address-format regexes, seed VASP
directories, and a couple of small shared helpers. This is the
architectural backbone — every other role's module imports from here,
this module imports from none of them.
"""

import os
import re

import streamlit as st

# =====================================================================
# API endpoints
# =====================================================================

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


def _cfg(key: str, default: str) -> str:
    """Read from st.secrets first, falling back to env vars, then default."""
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.environ.get(key, default)


MEMPOOL_BASE = _cfg("MEMPOOL_BASE", "https://mempool.space/api")
SOLANA_RPC = _cfg("SOLANA_RPC", "https://api.mainnet-beta.solana.com")


def get_api_key() -> str:
    try:
        return st.secrets["ETHERSCAN_API_KEY"]
    except Exception:
        return os.environ.get("ETHERSCAN_API_KEY", "")


# =====================================================================
# Chain registry — one entry per selectable chain, tagged with its family
# (family decides which fetch/pricing/validation logic path runs).
# =====================================================================

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


# =====================================================================
# Small shared helpers
# =====================================================================

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
