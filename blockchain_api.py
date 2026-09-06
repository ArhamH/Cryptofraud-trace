"""
blockchain_api.py
--------------------
Role: Blockchain & API Engineer (Pranjal Awasthi)

Chain-specific transaction fetchers (EVM via Etherscan V2, Bitcoin via
mempool.space, Solana via public RPC) that all normalize into a common
transfer shape:

    {"to": str, "amount": float, "symbol": str, "hash": str, "contract": str|None}

Plus CoinGecko-backed USD normalization so branch ranking isn't fooled
by comparing raw token amounts across different assets.
"""

import time

import requests

from system_architecture import (
    ETHERSCAN_BASE_URL,
    COINGECKO_BASE,
    MEMPOOL_BASE,
    SOLANA_RPC,
    CHAINS,
    STABLES,
    NATIVE_COINGECKO_ID,
    PLATFORM_ID,
)


# =====================================================================
# Chain-specific fetchers
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
