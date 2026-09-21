"""
Computes network statistics for the UN member-state Wikipedia network and
writes them to data/network_stats.json, which stats.html fetches and
renders. Re-run this any time data/un_nodes.tsv or data/un_edges.tsv change
(e.g. after a manual edge correction like the Kenya patch) to keep the
stats page in sync.

Methodology mirrors the course's own week 3 approach (centrality measures,
undirected-giant-component treatment for path/betweenness/eigenvector,
harmonic centrality in place of plain closeness for a directed/imperfectly-
connected graph) -- see https://sunelehmann.com/socialgraphs2026-web/weeks/week3.html
Deliberately out of scope, per that same methodology: PageRank and degree
assortativity.

Usage:
    python3 analyze_network.py
"""

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pandas as pd

HERE = Path(__file__).resolve().parent
NODES_PATH = HERE / "data" / "un_nodes.tsv"
EDGES_PATH = HERE / "data" / "un_edges.tsv"
OUTPUT_PATH = HERE / "data" / "network_stats.json"

TOP_N = 15
MAX_CLIQUE_EXAMPLES = 5


def load_graph():
    nodes = pd.read_csv(NODES_PATH, sep="\t", comment="#", quoting=3)
    edges = pd.read_csv(EDGES_PATH, sep="\t", comment="#", names=["source", "target"])

    G = nx.DiGraph()
    # All 193 nodes added before any edge, exactly as build_un_network.ipynb
    # does -- so an isolate (if any) is preserved rather than silently
    # dropped for never appearing in an edge tuple.
    G.add_nodes_from(nodes.node_id)
    G.add_edges_from(edges.itertuples(index=False))

    name_by_id = dict(zip(nodes.node_id, nodes.name))
    return G, name_by_id


def named(node_id, name_by_id):
    return {"node_id": node_id, "name": name_by_id[node_id]}


def top_n_from_dict(d, name_by_id, n=TOP_N, decimals=None):
    ranked = sorted(d.items(), key=lambda kv: (-kv[1], name_by_id[kv[0]]))[:n]
    out = []
    for node_id, value in ranked:
        entry = named(node_id, name_by_id)
        entry["value"] = round(value, decimals) if decimals is not None else value
        out.append(entry)
    return out


def validate_clique(H, clique):
    """Sanity-check a reported clique is genuinely complete in H -- don't
    trust nx.find_cliques's output blindly before writing it out."""
    for a, b in itertools.combinations(clique, 2):
        if not H.has_edge(a, b):
            raise AssertionError(f"Reported clique is NOT complete: {a} -- {b} missing")
    return True


def analyze_cliques(H, name_by_id, label):
    cliques = list(nx.find_cliques(H))
    clique_number = max(len(c) for c in cliques) if cliques else 0
    max_cliques = [c for c in cliques if len(c) == clique_number]

    for c in max_cliques:
        validate_clique(H, c)

    print(f"  [{label}] clique number = {clique_number}, "
          f"{len(max_cliques)} maximum clique(s) found")

    examples = []
    for c in max_cliques[:MAX_CLIQUE_EXAMPLES]:
        members = sorted(name_by_id[node_id] for node_id in c)
        examples.append(members)

    return {
        "clique_number": clique_number,
        "n_max_cliques": len(max_cliques),
        "examples": examples,
        "n_examples_shown": len(examples),
    }


def main():
    G, name_by_id = load_graph()
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    print(f"Loaded {n_nodes} nodes, {n_edges} edges.")

    # ---------------------------------------------------------- overview --
    density = nx.density(G)

    reciprocated_pairs = set()
    for u, v in G.edges():
        if G.has_edge(v, u):
            pair = tuple(sorted((u, v)))
            reciprocated_pairs.add(pair)
    reciprocated_edge_count = 2 * len(reciprocated_pairs)
    reciprocity_fraction = reciprocated_edge_count / n_edges if n_edges else 0.0

    # cross-check against networkx's own definition
    nx_reciprocity = nx.overall_reciprocity(G)
    assert abs(nx_reciprocity - reciprocity_fraction) < 1e-9, (
        f"Manual reciprocity {reciprocity_fraction} disagrees with "
        f"nx.overall_reciprocity {nx_reciprocity}"
    )

    weak_components = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    weak_giant = weak_components[0]
    outside_weak_giant = sorted(
        (name_by_id[n] for n in set(G.nodes()) - weak_giant),
        key=str,
    )

    strong_components = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    strong_giant = strong_components[0]

    print(f"Density: {density:.4f}")
    print(f"Reciprocated edges: {reciprocated_edge_count} of {n_edges} "
          f"({reciprocity_fraction:.1%})")
    print(f"Weakly connected giant component: {len(weak_giant)} / {n_nodes} "
          f"({len(weak_components)} components total)")
    print(f"Strongly connected giant component: {len(strong_giant)} / {n_nodes} "
          f"({len(strong_components)} components total)")

    overview = {
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "density": round(density, 4),
        "reciprocity": {
            "reciprocated_edges": reciprocated_edge_count,
            "total_edges": n_edges,
            "fraction": round(reciprocity_fraction, 4),
        },
        "weakly_connected": {
            "giant_size": len(weak_giant),
            "n_components": len(weak_components),
            "outside_giant": outside_weak_giant,
        },
        "strongly_connected": {
            "giant_size": len(strong_giant),
            "n_components": len(strong_components),
        },
    }

    # ------------------------------------------------------- paths/dist. --
    Gu = G.to_undirected()  # union: edge exists if EITHER direction present
    undirected_components = sorted(nx.connected_components(Gu), key=len, reverse=True)
    Gu_giant = Gu.subgraph(undirected_components[0]).copy()

    avg_path_length = nx.average_shortest_path_length(Gu_giant)
    diameter = nx.diameter(Gu_giant)
    radius = nx.radius(Gu_giant)
    center_ids = nx.center(Gu_giant)

    print(f"Undirected giant component: {Gu_giant.number_of_nodes()} nodes")
    print(f"Average path length: {avg_path_length:.3f}")
    print(f"Diameter: {diameter}, radius: {radius}")
    print(f"Center: {[name_by_id[n] for n in center_ids]}")

    paths = {
        "n_nodes_in_component": Gu_giant.number_of_nodes(),
        "avg_path_length": round(avg_path_length, 3),
        "diameter": diameter,
        "radius": radius,
        "center": sorted(name_by_id[n] for n in center_ids),
    }

    # ------------------------------------------------------- centrality --
    in_degree = dict(G.in_degree())
    out_degree = dict(G.out_degree())
    total_degree = {n: in_degree[n] + out_degree[n] for n in G.nodes()}

    print("Computing harmonic centrality (directed, on the full graph)...")
    harmonic = nx.harmonic_centrality(G)

    print("Computing betweenness centrality (undirected giant component)...")
    betweenness = nx.betweenness_centrality(Gu_giant)

    print("Computing eigenvector centrality (undirected giant component)...")
    try:
        eigenvector = nx.eigenvector_centrality(Gu_giant, max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        print("  power iteration did not converge, falling back to eigenvector_centrality_numpy")
        eigenvector = nx.eigenvector_centrality_numpy(Gu_giant)

    centrality = {
        "in_degree": top_n_from_dict(in_degree, name_by_id),
        "out_degree": top_n_from_dict(out_degree, name_by_id),
        "total_degree": top_n_from_dict(total_degree, name_by_id),
        "harmonic": top_n_from_dict(harmonic, name_by_id, decimals=2),
        "betweenness": top_n_from_dict(betweenness, name_by_id, decimals=4),
        "eigenvector": top_n_from_dict(eigenvector, name_by_id, decimals=4),
    }

    # ----------------------------------------------------------- cliques --
    print("Finding cliques...")
    all_links_result = analyze_cliques(Gu, name_by_id, "all-links")

    mutual = nx.Graph()
    mutual.add_nodes_from(G.nodes())
    for u, v in G.edges():
        if G.has_edge(v, u):
            mutual.add_edge(u, v)
    mutual_result = analyze_cliques(mutual, name_by_id, "mutual-only")

    cliques = {
        "all_links": all_links_result,
        "mutual_only": mutual_result,
    }

    # -------------------------------------------------------------- write --
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overview": overview,
        "paths": paths,
        "centrality": centrality,
        "cliques": cliques,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {OUTPUT_PATH.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
