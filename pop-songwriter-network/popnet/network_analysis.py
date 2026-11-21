"""Step 3: network analysis (course weeks 1-4)."""
import random

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

from . import config


def basic_stats(G: nx.Graph) -> dict:
    comps = list(nx.connected_components(G)) if not G.is_directed() else \
        list(nx.weakly_connected_components(G))
    giant = G.subgraph(max(comps, key=len)) if comps else G
    return {
        "nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
        "density": nx.density(G),
        "avg_degree": 2 * G.number_of_edges() / max(G.number_of_nodes(), 1),
        "components": len(comps), "giant_size": giant.number_of_nodes(),
        "avg_clustering": nx.average_clustering(G.to_undirected()),
    }


def plot_degree_distribution(degrees, label: str, ax=None, loglog: bool = True):
    """Histogram of degrees with log-spaced bins (the course way)."""
    degrees = np.array([d for d in degrees if d > 0])
    ax = ax or plt.gca()
    if loglog and degrees.max() > 1:
        bins = np.logspace(0, np.log10(degrees.max() + 1), 20)
        hist, edges = np.histogram(degrees, bins=bins, density=True)
        centers = (edges[:-1] + edges[1:]) / 2
        ax.loglog(centers[hist > 0], hist[hist > 0], "o-", label=label)
    else:
        ax.hist(degrees, bins=30, alpha=0.6, label=label)
    ax.set_xlabel("degree k"); ax.set_ylabel("P(k)"); ax.legend()
    return ax


def compare_with_random(G: nx.Graph, n_samples: int = 10) -> pd.DataFrame:
    """Real network vs Erdos-Renyi (same n, p) and configuration model (same degrees)."""
    rng = config.RANDOM_SEED
    n, p = G.number_of_nodes(), nx.density(G)
    rows = [{"network": "real", **_summary(G)}]
    for i in range(n_samples):
        er = nx.gnp_random_graph(n, p, seed=rng + i)
        cm = nx.Graph(nx.configuration_model([d for _, d in G.degree()], seed=rng + i))
        cm.remove_edges_from(nx.selfloop_edges(cm))
        rows += [{"network": "ER", **_summary(er)}, {"network": "config", **_summary(cm)}]
    return pd.DataFrame(rows).groupby("network").mean()


def _summary(G):
    return {"avg_clustering": nx.average_clustering(G),
            "max_degree": max((d for _, d in G.degree()), default=0)}


def top_centrality(G: nx.Graph, k: int = 10) -> pd.DataFrame:
    """Top-k nodes by degree, betweenness and eigenvector centrality."""
    deg = dict(G.degree(weight="weight"))
    btw = nx.betweenness_centrality(G)
    try:
        eig = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        eig = {n: np.nan for n in G}
    df = pd.DataFrame({"strength": deg, "betweenness": btw, "eigenvector": eig})
    return df.sort_values("betweenness", ascending=False).head(k)


def top_creators(B: nx.Graph, k: int = 20) -> pd.Series:
    """Songwriters/producers who worked with the most artists (bipartite degree)."""
    deg = {n: B.degree(n) for n, d in B.nodes(data=True) if d["kind"] == "creator"}
    return pd.Series(deg, name="n_artists").sort_values(ascending=False).head(k)


def communities(G: nx.Graph) -> tuple[dict, float]:
    """Louvain communities. Returns ({node: community_id}, modularity)."""
    comms = nx.community.louvain_communities(G, weight="weight", seed=config.RANDOM_SEED)
    comms = sorted(comms, key=len, reverse=True)
    part = {n: i for i, c in enumerate(comms) for n in c}
    return part, nx.community.modularity(G, comms, weight="weight")


def modularity_null(G: nx.Graph, n_samples: int = 50) -> np.ndarray:
    """Modularity of Louvain on degree-preserving shuffles of G (is ours higher?)."""
    values = []
    for i in range(n_samples):
        H = G.copy()
        n_swaps = max(1, 2 * H.number_of_edges())
        try:
            nx.double_edge_swap(H, nswap=n_swaps, max_tries=n_swaps * 20, seed=config.RANDOM_SEED + i)
        except nx.NetworkXAlgorithmError:
            pass
        comms = nx.community.louvain_communities(H, seed=config.RANDOM_SEED + i)
        values.append(nx.community.modularity(H, comms))
    return np.array(values)


def assortativity(G: nx.Graph, attr: str) -> float:
    """Do artists link to similar artists? attr = node attribute (e.g. 'country')."""
    if all(isinstance(v, (int, float)) for _, v in G.nodes(data=attr) if v is not None):
        return nx.numeric_assortativity_coefficient(G, attr)
    return nx.attribute_assortativity_coefficient(G, attr)


def interactive_html(G: nx.Graph, partition: dict, path) -> None:
    """Interactive network for the website (size = degree, colour = community)."""
    from pyvis.network import Network
    net = Network(height="700px", width="100%", bgcolor="#ffffff", notebook=False)
    deg = dict(G.degree())
    for n in G:
        net.add_node(n, label=n.removeprefix("A:"), group=partition.get(n, -1),
                     size=5 + 2 * np.sqrt(deg[n]))
    for u, v, d in G.edges(data=True):
        net.add_edge(u, v, value=d.get("weight", 1))
    net.write_html(str(path))
