#!/usr/bin/env python3
"""
V4 Layer 1: Build equivalence-class graph from V1/V2/V3 results.

Inputs:
  - v3/results/v3-deep-all.jsonl       (191 pairs with a_domain/b_domain/shared_equation/final_score/rating)
  - results/v2m-a-rated.jsonl          (19  A-rated V2 pairs)
  - results/a-final-all.jsonl          (47  V1 tier-1, no domain field)

Filter: final_score >= 7.0 OR rating in {"A", "B+"}

Output:
  - v4/results/graph.json
    {
      "nodes": [{"id": canonical_id, "name": display, "domain": ..., "aliases": [...], "sources": [...]}],
      "edges": [{"src": ..., "dst": ..., "score": ..., "shared_equation": ..., "pipelines": [...], "raw_names": [...]}],
      "stats": {...}
    }

Node canonicalization: simple normalized-string merging.
  canonical = strip whitespace + lowercase + remove punctuation
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_FILE = REPO_ROOT / "v4" / "results" / "graph.json"
ALIAS_FILE = REPO_ROOT / "v4" / "config" / "node_aliases.json"

SCORE_THRESHOLD = 7.0
RATING_WHITELIST = {"A", "B+", "A+", "B"}


def load_aliases():
    if not ALIAS_FILE.exists():
        return {}
    with ALIAS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("aliases", {})


_ALIASES = load_aliases()


def normalize_name(name: str) -> str:
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"[\s\-_/()（）·•,.，。:：;；'\"\[\]【】]", "", s)
    return s


def coerce_score(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_jsonl(path: Path):
    items = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def passes_filter(item) -> bool:
    score = coerce_score(item.get("final_score"))
    rating = (item.get("rating") or "").strip()
    if score is not None and score >= SCORE_THRESHOLD:
        return True
    if rating in RATING_WHITELIST:
        return True
    return False


def extract_pair(item, default_pipeline: str):
    """Normalize a record from any source to a common edge schema."""
    a = (item.get("a_name") or "").strip()
    b = (item.get("b_name") or "").strip()
    if not a or not b:
        return None
    a_dom = (item.get("a_domain") or "").strip()
    b_dom = (item.get("b_domain") or "").strip()
    score = coerce_score(item.get("final_score")) or 0.0
    shared_eq = (item.get("shared_equation") or "").strip()
    if not shared_eq:
        eqs = item.get("equations")
        if isinstance(eqs, list) and eqs:
            shared_eq = str(eqs[0])
        elif isinstance(eqs, str):
            shared_eq = eqs[:300]
    rating = (item.get("rating") or "").strip()
    return {
        "a_name": a,
        "b_name": b,
        "a_domain": a_dom,
        "b_domain": b_dom,
        "score": score,
        "shared_equation": shared_eq,
        "rating": rating,
        "pipeline": default_pipeline,
    }


def resolve_alias(name: str) -> str:
    return _ALIASES.get(name.strip(), name)


def canonical_node_id(name: str) -> str:
    resolved = resolve_alias(name)
    return normalize_name(resolved)[:48] or "UNKNOWN"


def build_graph():
    sources = [
        (REPO_ROOT / "v3" / "results" / "v3-deep-all.jsonl", "V3"),
        (REPO_ROOT / "results" / "v2m-a-rated.jsonl", "V2"),
        (REPO_ROOT / "results" / "a-final-all.jsonl", "V1"),
    ]

    all_pairs = []
    source_counts = {}
    filtered_counts = {}

    for path, tag in sources:
        items = load_jsonl(path)
        source_counts[tag] = len(items)
        n_kept = 0
        for item in items:
            if not passes_filter(item):
                continue
            pair = extract_pair(item, tag)
            if pair is None:
                continue
            all_pairs.append(pair)
            n_kept += 1
        filtered_counts[tag] = n_kept

    # Build nodes
    # Node key: canonical_id -> node record
    nodes: dict = {}

    def add_node(raw_name: str, domain: str):
        cid = canonical_node_id(raw_name)
        canonical_display = resolve_alias(raw_name)
        if cid not in nodes:
            nodes[cid] = {
                "id": cid,
                "name": canonical_display,  # prefer canonical name if aliased
                "domains": set(),
                "aliases": set(),
                "degree": 0,
            }
        if domain:
            nodes[cid]["domains"].add(domain)
        nodes[cid]["aliases"].add(raw_name)

    for p in all_pairs:
        add_node(p["a_name"], p["a_domain"])
        add_node(p["b_name"], p["b_domain"])

    # Build edges, dedup by canonical pair
    edge_map: dict = {}
    for p in all_pairs:
        u = canonical_node_id(p["a_name"])
        v = canonical_node_id(p["b_name"])
        if u == v:
            continue
        # undirected key
        key = tuple(sorted((u, v)))
        if key not in edge_map:
            edge_map[key] = {
                "src": key[0],
                "dst": key[1],
                "score": p["score"],
                "shared_equations": [],
                "pipelines": set(),
                "raw_names": set(),
            }
        e = edge_map[key]
        e["score"] = max(e["score"], p["score"])
        if p["shared_equation"] and p["shared_equation"] not in e["shared_equations"]:
            e["shared_equations"].append(p["shared_equation"])
        e["pipelines"].add(p["pipeline"])
        e["raw_names"].add(f"{p['a_name']} <-> {p['b_name']}")

    # Compute degree
    for e in edge_map.values():
        nodes[e["src"]]["degree"] += 1
        nodes[e["dst"]]["degree"] += 1

    # Finalize for JSON
    node_list = []
    for cid, n in sorted(nodes.items(), key=lambda kv: -kv[1]["degree"]):
        node_list.append({
            "id": cid,
            "name": n["name"],
            "domains": sorted(n["domains"]),
            "aliases": sorted(n["aliases"]),
            "degree": n["degree"],
        })

    edge_list = []
    for e in sorted(edge_map.values(), key=lambda x: -x["score"]):
        edge_list.append({
            "src": e["src"],
            "dst": e["dst"],
            "score": e["score"],
            "shared_equations": e["shared_equations"],
            "pipelines": sorted(e["pipelines"]),
            "raw_names": sorted(e["raw_names"]),
        })

    graph = {
        "nodes": node_list,
        "edges": edge_list,
        "stats": {
            "n_nodes": len(node_list),
            "n_edges": len(edge_list),
            "source_counts": source_counts,
            "filtered_counts": filtered_counts,
            "score_threshold": SCORE_THRESHOLD,
            "rating_whitelist": sorted(RATING_WHITELIST),
            "top10_degree": [(n["id"], n["name"], n["degree"]) for n in node_list[:10]],
        },
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"=== V4 Layer 1 Graph Build ===")
    print(f"Source counts: {source_counts}")
    print(f"Filtered counts (kept pairs): {filtered_counts}")
    print(f"Nodes: {len(node_list)}")
    print(f"Edges: {len(edge_list)}")
    print()
    print("Top 15 nodes by degree:")
    for n in node_list[:15]:
        doms = ",".join(n["domains"]) or "?"
        print(f"  deg={n['degree']:2d}  [{doms}]  {n['name']}")
    print()
    print(f"Output: {OUT_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    build_graph()
