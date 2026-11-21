"""Step 2: turn songs into networks.

Node names: artists are 'A:<name>', songwriters/producers are 'C:<name>' (C = creator),
so someone who is both (e.g. Ed Sheeran) is not mixed up.
"""
from collections import defaultdict
from itertools import combinations

import networkx as nx

from .collect_wikipedia import wiki_links_in


# Teams that Genius sometimes credits as one name and sometimes as their members.
CREATOR_ALIASES = {"Mikkel Storleer Eriksen": "Stargate", "Tor Erik Hermansen": "Stargate"}


def creator_names(song: dict, include_producers: bool = True) -> set[str]:
    """Distinct writer/producer names on a song, teams merged, the artist themself removed."""
    people = song["writers"] + (song["producers"] if include_producers else [])
    return {CREATOR_ALIASES.get(c["name"], c["name"]) for c in people} - {song["artist"]}


def build_bipartite(songs: list[dict], include_producers: bool = True) -> nx.Graph:
    """Artist -- creator edges. Edge weight = number of songs together.
    The artist's own credit on their own song is skipped (it says nothing about links)."""
    B = nx.Graph()
    for s in songs:
        artist = f"A:{s['artist']}"
        B.add_node(artist, bipartite="artist", kind="artist")
        for c in creator_names(s, include_producers):
            node = f"C:{c}"
            B.add_node(node, bipartite="creator", kind="creator")
            w = B.edges[artist, node]["weight"] + 1 if B.has_edge(artist, node) else 1
            B.add_edge(artist, node, weight=w)
    return B


def project_artists(B: nx.Graph, min_weight: int = 1) -> nx.Graph:
    """Artist -- artist network. Weight = number of creators they share.
    Keeps only edges with weight >= min_weight (fights the 'hairball')."""
    G = nx.Graph()
    G.add_nodes_from(n for n, d in B.nodes(data=True) if d["kind"] == "artist")
    shared = defaultdict(int)
    for c, d in B.nodes(data=True):
        if d["kind"] != "creator":
            continue
        for a1, a2 in combinations(sorted(B.neighbors(c)), 2):
            shared[(a1, a2)] += 1
    for (a1, a2), w in shared.items():
        if w >= min_weight:
            G.add_edge(a1, a2, weight=w)
    return G


def build_features(songs: list[dict]) -> nx.Graph:
    """Artist -- artist if one featured on the other's song (weight = number of songs)."""
    G = nx.Graph()
    for s in songs:
        a = f"A:{s['artist']}"
        G.add_node(a)
        for f in s["featured"]:
            b = f"A:{f['name']}"
            if b != a:
                w = G.edges[a, b]["weight"] + 1 if G.has_edge(a, b) else 1
                G.add_edge(a, b, weight=w)
    return G


def build_wiki_links(artists: list[dict]) -> nx.DiGraph:
    """Directed: A -> B if A's Wikipedia page links to B's page (backup network)."""
    titles = {a["title"] for a in artists}
    D = nx.DiGraph()
    D.add_nodes_from(titles)
    for a in artists:
        for t in wiki_links_in(a["wikitext"]) & titles:
            if t != a["title"]:
                D.add_edge(a["title"], t)
    return D


def creator_names_by_artist(B: nx.Graph) -> dict[str, set[str]]:
    return {a: set(B.neighbors(a)) for a, d in B.nodes(data=True) if d["kind"] == "artist"}
