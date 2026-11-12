#!/usr/bin/env python3
"""
V4 Layer 2: Hub detection + community discovery on the graph produced by build_graph.py.

Strategy (MVP):
  1) Load v4/results/graph.json
  2) Build a NetworkX undirected graph
  3) Connected components -> count those with >= 3 nodes and >= 2 distinct domains
  4) Louvain community detection (fallback: greedy modularity if python-louvain missing)
  5) For each candidate class:
       - members
       - domain coverage
       - aggregated shared_equations
       - avg/max edge score
       - hub node (highest internal degree)
  6) Emit v4/results/candidate_classes.jsonl

We do NOT need heavy dependencies; falls back gracefully.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH_FILE = REPO_ROOT / "v4" / "results" / "graph.json"
OUT_FILE = REPO_ROOT / "v4" / "results" / "candidate_classes.jsonl"

MIN_MEMBERS = 3
MIN_DOMAINS = 2


def main():
    try:
        import networkx as nx
    except ImportError:
        print("ERROR: networkx not installed. pip install networkx", file=sys.stderr)
        sys.exit(1)

    with GRAPH_FILE.open("r", encoding="utf-8") as f:
        graph = json.load(f)

    G = nx.Graph()
    node_info = {}
    for n in graph["nodes"]:
        G.add_node(n["id"])
        node_info[n["id"]] = n
    for e in graph["edges"]:
        G.add_edge(
            e["src"], e["dst"],
            score=e["score"],
            shared_equations=e["shared_equations"],
            pipelines=e["pipelines"],
        )

    print(f"=== V4 Layer 2 Hub Detection ===")
    print(f"Loaded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print()

    # -------- Connected components --------
    components = sorted(nx.connected_components(G), key=lambda c: -len(c))
    print(f"Connected components (≥2 nodes):")
    filtered_components = []
    for i, comp in enumerate(components):
        if len(comp) < 2:
            continue
        domains = set()
        for nid in comp:
            domains.update(node_info[nid]["domains"])
        filtered_components.append((comp, domains))
        if len(comp) >= MIN_MEMBERS:
            print(f"  C{i:02d}: size={len(comp):3d}, domains={len(domains):2d}")
    print()

    # -------- Louvain / greedy modularity on the giant component --------
    largest = max(components, key=len) if components else set()
    if len(largest) >= 4:
        print(f"Running community detection on giant component ({len(largest)} nodes)...")
        sub = G.subgraph(largest).copy()
        communities = None
        try:
            # NetworkX 3.x native Louvain
            communities = list(nx.community.louvain_communities(sub, weight="score", seed=42))
            algo = "louvain"
        except Exception as e:
            print(f"  louvain failed ({e}); falling back to greedy modularity")
            communities = list(nx.community.greedy_modularity_communities(sub, weight="score"))
            algo = "greedy_modularity"
        communities = [set(c) for c in communities]
        communities.sort(key=lambda c: -len(c))
        print(f"  Found {len(communities)} communities via {algo}:")
        for i, c in enumerate(communities):
            doms = set()
            for nid in c:
                doms.update(node_info[nid]["domains"])
            print(f"    L{i:02d}: size={len(c):3d}, domains={len(doms):2d}")
    else:
        communities = []
        algo = None
    print()

    # -------- Emit candidate classes --------
    #
    # We emit two flavours:
    #   (a) connected-component-based (coarse, naturally forms isolated classes)
    #   (b) louvain-based (fine-grained, splits the giant component)
    #
    # A "candidate class" needs: >=MIN_MEMBERS nodes, >=MIN_DOMAINS distinct domains.

    candidates = []

    def summarize_class(member_ids: set, provenance: str, index: int):
        doms = set()
        all_eqs = []
        total_score = 0.0
        max_score = 0.0
        edge_count = 0
        for nid in member_ids:
            doms.update(node_info[nid]["domains"])
        for e in graph["edges"]:
            if e["src"] in member_ids and e["dst"] in member_ids:
                all_eqs.extend(e["shared_equations"])
                total_score += e["score"]
                max_score = max(max_score, e["score"])
                edge_count += 1
        if len(member_ids) < MIN_MEMBERS or len(doms) < MIN_DOMAINS:
            return None
        # Hub node = member with highest degree inside this class
        internal_degree = Counter()
        for e in graph["edges"]:
            if e["src"] in member_ids and e["dst"] in member_ids:
                internal_degree[e["src"]] += 1
                internal_degree[e["dst"]] += 1
        hub_id, hub_deg = (internal_degree.most_common(1)[0] if internal_degree else (None, 0))
        return {
            "provenance": provenance,
            "index": index,
            "size": len(member_ids),
            "n_domains": len(doms),
            "domains": sorted(doms),
            "hub": {
                "id": hub_id,
                "name": node_info[hub_id]["name"] if hub_id else None,
                "degree_inside_class": hub_deg,
            },
            "members": sorted(
                [
                    {
                        "id": nid,
                        "name": node_info[nid]["name"],
                        "domains": node_info[nid]["domains"],
                    }
                    for nid in member_ids
                ],
                key=lambda x: x["name"],
            ),
            "edges_internal": edge_count,
            "avg_edge_score": round(total_score / edge_count, 3) if edge_count else 0,
            "max_edge_score": round(max_score, 3),
            "shared_equations_sample": all_eqs[:15],
        }

    # (a) Components
    for i, (comp, doms) in enumerate(filtered_components):
        cls = summarize_class(comp, "connected_component", i)
        if cls:
            candidates.append(cls)

    # (b) Louvain communities (only if we have them)
    for i, c in enumerate(communities):
        cls = summarize_class(c, "louvain_community", i)
        if cls:
            candidates.append(cls)

    # Sort by (size × n_domains) * avg_edge_score — proxy for "meaningful & broad"
    def rank_key(c):
        return -(c["size"] * c["n_domains"] * (c["avg_edge_score"] or 1))

    candidates.sort(key=rank_key)

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Print top candidates
    print(f"=== Top candidate equivalence classes (size × domains × score) ===")
    print()
    for i, c in enumerate(candidates[:8]):
        print(f"--- #{i + 1}  provenance={c['provenance']}  size={c['size']}  domains={c['n_domains']}  "
              f"avg_edge_score={c['avg_edge_score']}  max={c['max_edge_score']}")
        print(f"    Hub: {c['hub']['name']}  (internal degree {c['hub']['degree_inside_class']})")
        print(f"    Domains: {', '.join(c['domains'])}")
        print(f"    Members:")
        for m in c["members"]:
            doms = ",".join(m["domains"]) or "?"
            print(f"      - [{doms}] {m['name']}")
        if c["shared_equations_sample"]:
            print(f"    Sample shared equation: {c['shared_equations_sample'][0][:110]}")
        print()

    print(f"Output: {OUT_FILE.relative_to(REPO_ROOT)}  ({len(candidates)} candidates)")


if __name__ == "__main__":
    main()
