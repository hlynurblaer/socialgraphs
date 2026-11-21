"""Step 5: are artists who are close in the network also close in their lyrics?"""
import networkx as nx
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config


def artist_similarity(df: pd.DataFrame) -> pd.DataFrame:
    """df = songs dataframe with 'artist' and 'tokens'. Returns artist x artist cosine
    similarity of TF-IDF vectors (one document = all of an artist's lyrics)."""
    docs = df.groupby("artist")["tokens"].sum()
    vec = TfidfVectorizer(analyzer=lambda toks: toks, sublinear_tf=True, min_df=2)
    X = vec.fit_transform(docs.values)
    names = [f"A:{a}" for a in docs.index]
    return pd.DataFrame(cosine_similarity(X), index=names, columns=names)


def edge_vs_nonedge(G: nx.Graph, S: pd.DataFrame) -> pd.DataFrame:
    """Similarity for every artist pair, labelled linked / not linked + edge weight."""
    nodes = [n for n in G if n in S.index]
    rows = []
    for i, u in enumerate(nodes):
        for v in nodes[i + 1:]:
            w = G.edges[u, v].get("weight", 1) if G.has_edge(u, v) else 0
            rows.append({"u": u, "v": v, "linked": w > 0, "weight": w, "sim": S.at[u, v]})
    return pd.DataFrame(rows)


def permutation_test(G: nx.Graph, S: pd.DataFrame, n_perm: int = 1000) -> dict:
    """Mean similarity across real edges vs. the same edges after shuffling which artist
    sits on which node. p = share of shuffles at least as similar as reality."""
    nodes = [n for n in G if n in S.index]
    H = G.subgraph(nodes)
    idx = {n: i for i, n in enumerate(nodes)}
    M = S.loc[nodes, nodes].values
    edges = np.array([(idx[u], idx[v]) for u, v in H.edges()])
    if len(edges) == 0:
        return {"observed": np.nan, "null_mean": np.nan, "p_value": np.nan}
    observed = M[edges[:, 0], edges[:, 1]].mean()
    rng = np.random.default_rng(config.RANDOM_SEED)
    null = np.empty(n_perm)
    for k in range(n_perm):
        p = rng.permutation(len(nodes))
        null[k] = M[p[edges[:, 0]], p[edges[:, 1]]].mean()
    return {"observed": observed, "null_mean": null.mean(),
            "p_value": (np.sum(null >= observed) + 1) / (n_perm + 1), "null": null}
