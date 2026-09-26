"""
graph_engine.py
-------------------
Graph analytics, multithreaded BFS, and inductive risk scoring.
"""

from concurrent.futures import ThreadPoolExecutor
import networkx as nx

from system_architecture import (
    CHAINS, IGNORED_CONTRACTS, short_addr,
    PEEL_SKIM_MIN_SHARE, PEEL_SKIM_MAX_SHARE,
    SWEEP_WINDOW_SECONDS, SWEEP_MIN_FORWARD_RATIO,
)
from blockchain_api import (
    fetch_transfers, annotate_usd_values,
    classify_evm_contract_hop, resolve_dex_swap_output, resolve_bridge_exit,
)

class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

def _detect_sweep_forward(dest_key, chain_key, api_key, vasp_map, family, inbound_ts, inbound_usd):
    if family not in ("evm", "btc"):
        return None
    try:
        outgoing = fetch_transfers(dest_key, chain_key, api_key)
        if not outgoing:
            return None
        outgoing = annotate_usd_values(outgoing, chain_key)
        for t in outgoing[:3]:
            to_raw = t.get("to")
            if not to_raw:
                continue
            to_key = to_raw.lower() if family == "evm" else to_raw
            if to_key in vasp_map:
                ts = t.get("timestamp", 0) or 0
                if inbound_ts and ts and not (0 <= ts - inbound_ts <= SWEEP_WINDOW_SECONDS):
                    continue
                if inbound_usd and t.get("usd", 0.0) < SWEEP_MIN_FORWARD_RATIO * inbound_usd:
                    continue
                return vasp_map[to_key]
    except Exception:
        pass
    return None

def trace_fund_flow(start_address, chain_key, api_key, vasp_directory,
                     max_hops=6, max_branches=2, exhaustive_trace=True,
                     detect_sweeps=True, progress_cb=None):
    family = CHAINS[chain_key]["family"]
    vasp_map = vasp_directory[family]

    start = start_address.strip()
    start_key = start.lower() if family == "evm" else start

    uf = _UnionFind() if family == "btc" else None

    def canon(addr_key):
        return uf.find(addr_key) if uf else addr_key

    graph = nx.DiGraph()
    graph.add_node(
        canon(start_key), role="source", hop=0, taint=1.0,
        label=f"Suspect Drainer\n{short_addr(start_key)}"
    )

    attributions = []
    cross_chain_alerts = []
    frontier = [(start_key, 1.0, 0)]
    visited = {canon(start_key)}
    calls_made, hop = 0, 0

    while frontier and hop < max_hops:
        hop += 1
        current_layer = frontier[:]
        frontier = []

        if progress_cb:
            progress_cb(hop, f"{len(current_layer)} node(s) concurrently")

        def _fetch_worker(item):
            w_addr, w_taint, in_ts = item
            raw = fetch_transfers(w_addr, chain_key, api_key)
            annotated = annotate_usd_values(raw, chain_key) if raw else []
            return (w_addr, w_taint, in_ts, annotated)

        with ThreadPoolExecutor(max_workers=5) as executor:
            fetched_data = list(executor.map(_fetch_worker, current_layer))
        calls_made += len(current_layer)

        for wallet, wallet_taint, inbound_ts, transfers in fetched_data:
            wallet_key = canon(wallet.lower() if family == "evm" else wallet)
            if not transfers:
                continue

            if uf:
                for t in transfers:
                    for other in t.get("co_spend_cluster", set()):
                        uf.union(wallet_key, other)
                wallet_key = canon(wallet_key)

            by_dest = {}
            for t in transfers:
                dest = t.get("to")
                if not dest:
                    continue
                dest_key = canon(dest.lower() if family == "evm" else dest)
                if dest_key == wallet_key or (family == "evm" and dest_key in IGNORED_CONTRACTS):
                    continue
                if dest_key not in by_dest or t["usd"] > by_dest[dest_key]["usd"]:
                    by_dest[dest_key] = t

            hop_total_usd = sum(m["usd"] for m in by_dest.values()) or 0.0
            ranked = sorted(by_dest.items(), key=lambda kv: kv[1]["usd"], reverse=True)
            top_dests = ranked[:max_branches]

            peel_dests = []
            if hop_total_usd > 0:
                for dest_key, meta in ranked[max_branches:]:
                    share = meta["usd"] / hop_total_usd
                    if PEEL_SKIM_MIN_SHARE <= share <= PEEL_SKIM_MAX_SHARE:
                        peel_dests.append((dest_key, meta))
                peel_dests = peel_dests[:2]

            local_taint = wallet_taint
            if wallet_key in graph.nodes:
                graph.nodes[wallet_key]["taint"] = round(local_taint, 4)

            # Avoid pruning valid peel splits by using a 2% floor
            if local_taint < 0.02:
                continue

            peel_keys = {k for k, _ in peel_dests}
            for dest_key, meta in top_dests + peel_dests:
                is_peel = dest_key in peel_keys
                edge_from = wallet_key

                if family == "evm":
                    contract_kind, contract_name = classify_evm_contract_hop(dest_key)
                    if contract_kind == "bridge":
                        alert = resolve_bridge_exit(meta["hash"], CHAINS[chain_key]["chain_id"],
                                                     api_key, dest_key, contract_name)
                        calls_made += 1
                        graph.add_node(dest_key, role="bridge_exit", hop=hop,
                                        label=f"{contract_name}\n[BRIDGE EXIT]\n{short_addr(dest_key)}",
                                        taint=round(local_taint, 4))
                        graph.add_edge(edge_from, dest_key, amount=round(meta["amount"], 6),
                                        symbol=meta["symbol"], usd=round(meta["usd"], 2),
                                        priced=meta["priced"], hash=meta["hash"], hop=hop,
                                        is_peel=is_peel, taint_score=round(local_taint, 4), is_bridge=True)
                        cross_chain_alerts.append({**alert, "node": dest_key, "hop": hop,
                                                    "usd": round(meta["usd"], 2),
                                                    "amount": round(meta["amount"], 6),
                                                    "symbol": meta["symbol"]})
                        continue

                    if contract_kind == "dex":
                        resolved = resolve_dex_swap_output(meta["hash"], CHAINS[chain_key]["chain_id"],
                                                             api_key, dest_key)
                        calls_made += 1
                        if resolved and resolved.get("resolved_to") and resolved["resolved_to"] != wallet_key:
                            graph.add_node(dest_key, role="dex_hop", hop=hop,
                                            label=f"{contract_name}\n[DEX SWAP]\n{short_addr(dest_key)}",
                                            taint=round(local_taint, 4))
                            graph.add_edge(edge_from, dest_key, amount=round(meta["amount"], 6),
                                            symbol=meta["symbol"], usd=round(meta["usd"], 2),
                                            priced=meta["priced"], hash=meta["hash"], hop=hop,
                                            is_peel=is_peel, taint_score=round(local_taint, 4), is_dex=True)
                            edge_from, dest_key = dest_key, resolved["resolved_to"]

                is_vasp = dest_key in vasp_map
                vasp_name = vasp_map.get(dest_key)
                attributed_deposit_vasp = None

                if not is_vasp and detect_sweeps and dest_key not in visited:
                    attributed_deposit_vasp = _detect_sweep_forward(
                        dest_key, chain_key, api_key, vasp_map, family,
                        inbound_ts=meta.get("timestamp", 0), inbound_usd=meta["usd"]
                    )
                    calls_made += 1

                role = "vasp" if is_vasp else ("deposit_address" if attributed_deposit_vasp else "intermediate")
                if is_vasp:
                    node_label = f"{vasp_name}\n{short_addr(dest_key)}"
                elif attributed_deposit_vasp:
                    node_label = f"User Deposit Addr\n→ {attributed_deposit_vasp}\n{short_addr(dest_key)}"
                else:
                    node_label = f"Hop {hop}\n{short_addr(dest_key)}" + (" [peel]" if is_peel else "")

                graph.add_node(
                    dest_key, role=role, hop=hop, label=node_label,
                    taint=round(local_taint, 4)
                )
                graph.add_edge(
                    edge_from, dest_key, amount=round(meta["amount"], 6),
                    symbol=meta["symbol"], usd=round(meta["usd"], 2),
                    priced=meta["priced"], hash=meta["hash"], hop=hop,
                    is_peel=is_peel, taint_score=round(local_taint, 4)
                )

                if is_vasp:
                    attributions.append({
                        "node": dest_key, "vasp": vasp_name, "hop": hop,
                        "hash": meta["hash"], "amount": round(meta["amount"], 6),
                        "symbol": meta["symbol"], "usd": round(meta["usd"], 2),
                        "taint_score": round(local_taint, 4)
                    })
                elif attributed_deposit_vasp:
                    attributions.append({
                        "node": dest_key,
                        "vasp": f"{attributed_deposit_vasp} (User Deposit Addr, sweep-detected)",
                        "hop": hop, "hash": meta["hash"], "amount": round(meta["amount"], 6),
                        "symbol": meta["symbol"], "usd": round(meta["usd"], 2),
                        "taint_score": round(local_taint, 4), "sweep_detected": True
                    })
                elif dest_key not in visited:
                    prop_taint = local_taint * ((meta["usd"] / hop_total_usd) if hop_total_usd > 0 else 0.95)
                    frontier.append((dest_key, max(0.01, prop_taint), meta.get("timestamp", 0)))

            visited.add(wallet_key)

        if attributions and not exhaustive_trace:
            break

    attributions.sort(key=lambda a: a["usd"], reverse=True)
    return graph, attributions, calls_made, cross_chain_alerts

def calculate_confidence_score(attributions, hop_reached, max_hops):
    if not attributions:
        return 0.0
    top = attributions[0]
    if top.get("is_replay"):
        return 100.0
    score = 80.0 + max(0.0, (max_hops - hop_reached) * 2.5)
    if top.get("sweep_detected"):
        score -= 15.0
    taint = top.get("taint_score")
    if taint is not None and taint < 1.0:
        score -= (1.0 - taint) * 20.0
    return float(max(50.0, min(99.0, score)))

def score_nodes(graph):
    results = {}
    for node in graph.nodes():
        if graph.nodes[node].get("role") in ("source", "vasp"):
            continue
        in_edges = list(graph.in_edges(node, data=True))
        out_edges = list(graph.out_edges(node, data=True))
        peel_in = sum(1 for e in in_edges if e[2].get("is_peel"))
        taint = graph.nodes[node].get("taint") or 0.0
        
        fanout = min(1.0, len(out_edges) / 3.0) if in_edges else 0.0
        peel_ratio = (peel_in / len(in_edges)) if in_edges else 0.0
        
        score = min(0.95, 0.4 * fanout + 0.35 * peel_ratio + 0.25 * taint)
        results[node] = {"score": round(score, 3), "method": "heuristic_coldstart"}
    return results
