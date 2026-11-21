"""Runs steps 2-5 on FAKE data (made-up artists, writers and word lists).
Use it to check the code works before the real download is finished:  python test_toy.py
"""
import random

from popnet import build_networks as bn
from popnet import combine, network_analysis as na, text_analysis as ta

random.seed(0)
WORDS = {  # each fake "scene" has its own vocabulary, so the test has a signal to find
    0: "dance night party lights floor tonight fire neon club move".split(),
    1: "heart cry rain alone tears broken goodbye cold lonely memory".split(),
    2: "money city drive fast gold crown boss shine diamond street".split(),
}
WRITERS = {0: ["Writer A", "Writer B", "Writer C"], 1: ["Writer D", "Writer E"],
           2: ["Writer F", "Writer G", "Writer H"]}

songs = []
for a in range(30):
    scene = a % 3
    for s in range(8):
        writers = random.sample(WRITERS[scene], 2)
        if random.random() < 0.15:                   # some cross-scene work
            writers.append(random.choice(WRITERS[(scene + 1) % 3]))
        lyrics = "\n".join(" ".join(random.choices(WORDS[scene] + WORDS[(scene + 1) % 3][:2], k=8))
                           for _ in range(12))
        songs.append({"song_id": a * 100 + s, "title": f"Song {s}", "url": "", "year": 2015,
                      "artist_id": a, "artist": f"Artist {a}",
                      "writers": [{"id": 0, "name": w} for w in writers], "producers": [],
                      "featured": [], "lyrics": "[Chorus]\n" + lyrics})

# Step 2
B = bn.build_bipartite(songs)
G = bn.project_artists(B, min_weight=1)
print("Bipartite:", B.number_of_nodes(), "nodes |", "Projection:", na.basic_stats(G))

# Step 3
part, Q = na.communities(G)
print(f"Louvain: {len(set(part.values()))} communities, modularity {Q:.3f}")
print("Null modularity mean:", na.modularity_null(G, n_samples=5).mean().round(3))
print(na.compare_with_random(G, n_samples=3))
print(na.top_creators(B, k=3))
print(na.top_centrality(G, k=3))

# Step 4
df = ta.songs_dataframe(songs)
df["community"] = df["artist"].map(lambda a: part.get(f"A:{a}"))
top = ta.tfidf_by_group(df.groupby("community")["tokens"].sum().to_dict(), top_n=5)
for c, words in top.items():
    print(f"Community {c}:", [w for w, _ in words])
toy_labmt = {"party": 7.6, "dance": 7.2, "lights": 6.6, "tears": 2.7, "cry": 2.4,
             "alone": 2.6, "money": 7.3, "gold": 7.0}
df["happiness"] = df["tokens"].map(lambda t: ta.happiness(t, toy_labmt))
print(df.groupby("community")["happiness"].mean().round(2))

# Step 5
S = combine.artist_similarity(df)
pairs = combine.edge_vs_nonedge(G, S)
print(pairs.groupby("linked")["sim"].mean().round(3))
res = combine.permutation_test(G, S, n_perm=200)
print(f"Edge similarity {res['observed']:.3f} vs null {res['null_mean']:.3f}, p = {res['p_value']:.3f}")
print("\nAll steps ran OK.")
