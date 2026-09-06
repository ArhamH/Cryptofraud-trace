"""
graph_analytics.py
---------------------
Role: Graph Analytics Analyst (Ruchir Gupta)

Chain-family-agnostic multi-hop BFS traversal that reconstructs fund
flow from a suspect wallet out to a regulated VASP endpoint, plus the
forensic confidence scoring used to rate that attribution.
"""

import time

import networkx as nx

from system_architecture import CHAINS, IGNORED_CONTRACTS, short_addr
from blockchain_api import fetch_transfers, annotate_usd_values


def trace_fund_flow(start_address, chain_key, api_key, vasp_directory,
                     max_hops=8, max_branches=2, simulation_fallback=False,
                     exhaustive_trace=True, progress_cb=None):
    family = CHAINS[chain_key]["family"]
    vasp_map = vasp_directory[family]

    start = start_address.strip()
    start_key = start.lower() if family == "evm" else start

    graph = nx.DiGraph()
    graph.add_node(start_key, role="source", hop=0, label=f"Suspect Drainer\n{short_addr(start_key)}")

    attributions, frontier, visited = [], [start], {start_key}
    calls_made, hop = 0, 0

    while frontier and hop < max_hops:
        hop += 1
        next_frontier = []

        for wallet in frontier:
            wallet_key = wallet.lower() if family == "evm" else wallet
            if progress_cb:
                progress_cb(hop, wallet_key)

            transfers = fetch_transfers(wallet, chain_key, api_key)
            calls_made += 1
            time.sleep(0.3)
            if not transfers:
                continue

            transfers = annotate_usd_values(transfers, chain_key)

            by_dest = {}
            for t in transfers:
                dest = t.get("to")
                if not dest:
                    continue
                dest_key = dest.lower() if family == "evm" else dest
                if dest_key == wallet_key:
                    continue
                if family == "evm" and dest_key in IGNORED_CONTRACTS:
                    continue
                if dest_key not in by_dest or t["usd"] > by_dest[dest_key]["usd"]:
                    by_dest[dest_key] = t

            # Rank by USD value, not raw token amount — a stablecoin and a
            # low-price altcoin are not comparable as raw numbers.
            top_dests = sorted(by_dest.items(), key=lambda kv: kv[1]["usd"], reverse=True)[:max_branches]

            for dest_key, meta in top_dests:
                is_vasp = dest_key in vasp_map
                vasp_name = vasp_map.get(dest_key)

                graph.add_node(
                    dest_key, role="vasp" if is_vasp else "intermediate", hop=hop,
                    label=f"{vasp_name}\n{short_addr(dest_key)}" if is_vasp else f"Hop {hop}\n{short_addr(dest_key)}",
                )
                graph.add_edge(wallet_key, dest_key, amount=round(meta["amount"], 6),
                                symbol=meta["symbol"], usd=round(meta["usd"], 2),
                                priced=meta["priced"], hash=meta["hash"], hop=hop)

                if is_vasp:
                    attributions.append({"node": dest_key, "vasp": vasp_name, "hop": hop,
                                          "hash": meta["hash"], "amount": round(meta["amount"], 6),
                                          "symbol": meta["symbol"], "usd": round(meta["usd"], 2)})
                elif dest_key not in visited:
                    next_frontier.append(dest_key)

            visited.add(wallet_key)

        frontier = next_frontier
        if attributions and not exhaustive_trace:
            # Fast mode: stop as soon as ANY branch hits a VASP. Note this
            # can leave a larger, still-open fund trail unresolved just
            # because a smaller side-branch happened to reach an exchange
            # first — exhaustive_trace=True (default) avoids that.
            break

    # Report the highest-value VASP hit first, not merely the first one
    # discovered — discovery order depends on wallet iteration order, not
    # on which trail actually carries the most money.
    attributions.sort(key=lambda a: a["usd"], reverse=True)

    if not attributions and simulation_fallback and family == "evm" and graph.number_of_nodes() > 1:
        leaves = [n for n in graph.nodes if graph.out_degree(n) == 0 and n != start_key]
        if leaves:
            leaf = leaves[0]
            binance_hot = "0x28c6c06298d514db089934071355e5743bf21d60"
            graph.add_node(binance_hot, role="vasp", hop=hop, label="Binance (Hot Wallet 14) [SIMULATED]")
            graph.add_edge(leaf, binance_hot, amount=1.25, symbol="USDT", usd=1.25,
                            priced=True, hash="0xSIMULATED_HOP_DEMO", hop=hop)
            attributions.append({"node": binance_hot, "vasp": "Binance (Hot Wallet 14) [Simulation]",
                                  "hop": hop, "hash": "0xSIMULATED_HOP_DEMO", "amount": 1.25,
                                  "symbol": "USDT", "usd": 1.25})

    return graph, attributions, calls_made


def calculate_confidence_score(attributions, hop_reached, max_hops):
    if not attributions:
        return 0.0
    if "[Simulation]" in attributions[0]["vasp"]:
        return 45.0
    score = 80.0 + max(0.0, (max_hops - hop_reached) * 2.5)
    return float(max(50.0, min(99.0, score)))
