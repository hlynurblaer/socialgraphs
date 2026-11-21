"""Make every number, table and figure the paper uses.

    python make_paper_assets.py          # real data (needs data/processed/songs.json)
    python make_paper_assets.py --toy    # FAKE data, only to test the paper layout

Writes:  paper/results.tex   (\\newcommand macros with every number in the text)
         paper/tables/*.tex  (table bodies)
         paper/figures/*.pdf
"""
import argparse
import unicodedata
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import normalized_mutual_info_score

from popnet import build_networks as bn
from popnet import combine, config
from popnet import network_analysis as na
from popnet import text_analysis as ta
from popnet.cache import load_json

PAPER = config.ROOT / "paper"
FIG, TAB = PAPER / "figures", PAPER / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)

COL_W, FULL_W = 3.42, 7.0            # PNAS: 8.7 cm column, 17.8 cm full width (inches)
plt.rcParams.update({"font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
                     "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "font.family": "sans-serif"})
PALETTE = ["#2a6fdb", "#e8743b", "#19a979", "#d64f8b", "#8e6bd1", "#c9a227", "#4fb3c9", "#945ecf"]
GREY = "#b8b8b8"

macros: dict[str, str] = {}


def M(name: str, value, fmt: str | None = None) -> None:
    """Store a number for the paper: \\Name in LaTeX."""
    macros[name] = fmt.format(value) if fmt is not None else str(value)


def tex(s: str) -> str:
    """Make a name safe for pdflatex: fold accents, drop non-Latin characters, escape."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"), ("~", r"\~{}"),
                 ("^", r"\^{}")]:
        s = s.replace(a, b)
    return s.strip() or "?"


def shown(word: str) -> str:
    """Words as printed in the paper: slurs are partly masked (analysis is unchanged)."""
    return {"nigga": "n*gga", "niggas": "n*ggas"}.get(word, word)


def name(node: str) -> str:
    return node.split(":", 1)[1] if ":" in node else node


def fmt_p(p: float) -> str:
    """For math mode: \\PermP -> 'p<0.001' or 'p=0.012' (use as $\\PermP$)."""
    return r"p<0.001" if p < 0.001 else f"p={p:.3f}"


# --------------------------------------------------------------------------------------
def wikipedia_part():
    artists = load_json(config.DATA_PROCESSED / "artists.json")
    D = bn.build_wiki_links(artists)
    M("WikiArtists", D.number_of_nodes(), "{:,}")
    M("WikiLinks", D.number_of_edges(), "{:,}")
    top = sorted(D.in_degree(), key=lambda x: -x[1])[:3]
    M("WikiTopThree", ", ".join(f"{tex(t)} ({k})" for t, k in top))
    U = D.to_undirected()
    wiki_part, wiki_q = na.communities(U)
    M("WikiModularity", wiki_q, "{:.2f}")
    return artists, D, wiki_part


def main(toy: bool):
    artists, D, wiki_part = wikipedia_part()

    if toy:
        from popnet.toy import toy_songs
        songs = toy_songs()
        M("DataStatus", r"{\color{red}\textbf{[TOY DATA -- NOT REAL RESULTS. Run make\_paper\_assets.py on the Genius data.]}}")
    else:
        songs = load_json(config.DATA_PROCESSED / "songs.json")
        M("DataStatus", "")

    # ---------------- data stats ----------------
    M("YearMin", config.YEAR_MIN); M("YearMax", config.YEAR_MAX)
    M("SongsPerArtist", config.SONGS_PER_ARTIST); M("LyricsPerArtist", config.LYRICS_PER_ARTIST)
    M("MinEdgeWeight", config.MIN_EDGE_WEIGHT)
    n_art = len({s["artist"] for s in songs})
    M("NumArtists", n_art, "{:,}")
    M("NumSongs", len(songs), "{:,}")
    with_credits = [s for s in songs if s["writers"] or s["producers"]]
    M("NumSongsCredits", len(with_credits), "{:,}")
    if not toy:
        matches = pd.read_csv(config.DATA_PROCESSED / "artist_matches.csv")
        M("NumGeniusMatched", int(matches["genius_id"].notna().sum()))
        M("NumManualMatched", len(config.GENIUS_MANUAL_IDS))
        M("NumNoSongs", int(matches["genius_id"].notna().sum()) - n_art)
    else:
        M("NumGeniusMatched", "--"); M("NumManualMatched", "--"); M("NumNoSongs", "--")
    M("PctSongsCredits", 100 * len(with_credits) / max(len(songs), 1), "{:.0f}")

    # ---------------- networks ----------------
    B = bn.build_bipartite(songs)
    creators = [n for n, d in B.nodes(data=True) if d["kind"] == "creator"]
    M("NumCreators", len(creators), "{:,}")
    M("NumBipEdges", B.number_of_edges(), "{:,}")
    G = bn.project_artists(B, min_weight=config.MIN_EDGE_WEIGHT)
    st = na.basic_stats(G)
    M("NumEdges", st["edges"], "{:,}")
    M("Density", st["density"], "{:.3f}")
    M("AvgDegree", st["avg_degree"], "{:.1f}")
    M("GiantSize", st["giant_size"], "{:,}")
    M("GiantPct", 100 * st["giant_size"] / max(st["nodes"], 1), "{:.0f}")
    M("NumIsolated", nx.number_of_isolates(G), "{:,}")
    giant = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    rnd = na.compare_with_random(giant, n_samples=10)
    M("Clust", rnd.loc["real", "avg_clustering"], "{:.2f}")
    M("ClustER", rnd.loc["ER", "avg_clustering"], "{:.2f}")
    M("ClustConfig", rnd.loc["config", "avg_clustering"], "{:.2f}")

    # ---------------- hubs ----------------
    cdeg = pd.Series({c: B.degree(c) for c in creators}).sort_values(ascending=False)
    csongs = Counter()
    for s in songs:
        for c in bn.creator_names(s):
            csongs[f"C:{c}"] += 1
    M("TopCreator", tex(name(cdeg.index[0]))); M("TopCreatorArtists", int(cdeg.iloc[0]))
    M("MedianCreatorArtists", cdeg.median(), "{:.0f}")
    M("PctOneArtistCreators", 100 * (cdeg == 1).mean(), "{:.0f}")
    top1 = set(cdeg.index[: max(1, int(np.ceil(0.01 * len(cdeg))))])
    M("NumTopOnePct", len(top1))
    reached = {a for c in top1 for a in B.neighbors(c)}
    M("PctReachedTopOne", 100 * len(reached) / max(n_art, 1), "{:.0f}")
    k = min(500, B.number_of_nodes())
    btw = nx.betweenness_centrality(B, k=k, seed=config.RANDOM_SEED)
    cbtw = pd.Series({c: btw[c] for c in creators}).rank(ascending=False, method="min")
    rows = [rf"{i} & {tex(name(c))} & {int(cdeg[c])} & {csongs[c]} & {int(cbtw[c])} \\"
            for i, c in enumerate(cdeg.index[:10], 1)]
    (TAB / "top_creators.tex").write_text(
        "\\begin{tabular}{rlrrr}\n\\# & Songwriter/producer & Artists & Songs & Betw. \\\\\n\\midrule\n"
        + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n")
    abtw = nx.betweenness_centrality(giant, seed=config.RANDOM_SEED, k=min(500, len(giant)))
    bridge = max(abtw, key=abtw.get)
    M("BridgeArtist", tex(name(bridge)))

    # ---------------- communities ----------------
    part, Q = na.communities(giant)
    null = na.modularity_null(giant, n_samples=20)
    M("Modularity", Q, "{:.2f}"); M("ModNullMean", null.mean(), "{:.2f}"); M("ModNullStd", null.std(), "{:.2f}")
    sizes = Counter(part.values())
    M("NumComms", len(sizes)); M("NumCommsBig", sum(v >= 5 for v in sizes.values()))
    big = [c for c, _ in sizes.most_common(6)]
    relabel = {c: i + 1 for i, c in enumerate(big)}          # C1 = biggest
    med_year = pd.DataFrame(songs).groupby("artist")["year"].median()
    for n in giant:
        y = med_year.get(name(n))
        giant.nodes[n]["year"] = float(y) if y is not None and not np.isnan(y) else 0.0
    M("YearAssort", nx.numeric_assortativity_coefficient(giant, "year"), "{:.2f}")

    # ---------------- text ----------------
    lyr = [s for s in songs if s.get("lyrics")]
    df = ta.songs_dataframe(lyr) if lyr else pd.DataFrame(columns=["artist", "tokens", "year"])
    M("NumSongsLyrics", len(df), "{:,}")
    M("NumTokens", int(df["tokens"].map(len).sum()) if len(df) else 0, "{:,}")
    df["community"] = df["artist"].map(lambda a: relabel.get(part.get(f"A:{a}")))
    labmt = ta.load_labmt()
    df["happiness"] = df["tokens"].map(lambda t: ta.happiness(t, labmt))
    dfc = df.dropna(subset=["community"]).astype({"community": int})
    # Community vocabularies: TF from the community, IDF from artists (see ta.tfidf_artist_idf).
    top_words = ta.tfidf_artist_idf(dfc.groupby("community")["artist"].unique().to_dict(),
                                    df.groupby("artist")["tokens"].sum().to_dict(), top_n=8)
    hap = dfc.groupby("community")["happiness"].agg(["mean", "sem", "count"])
    groups = [g["happiness"].dropna().values for _, g in dfc.groupby("community")]
    if len(groups) > 1:
        H, p = stats.kruskal(*groups)
        M("KruskalH", H, "{:.1f}"); M("KruskalP", fmt_p(p))
    M("HappyMean", df["happiness"].mean(), "{:.2f}")
    if hap.shape[0]:
        M("HappiestComm", f"C{int(hap['mean'].idxmax())}"); M("HappiestVal", hap["mean"].max(), "{:.2f}")
        M("SaddestComm", f"C{int(hap['mean'].idxmin())}"); M("SaddestVal", hap["mean"].min(), "{:.2f}")
    yy = df.dropna(subset=["happiness", "year"])
    rho, p = stats.spearmanr(yy["year"], yy["happiness"])
    M("YearRho", rho, "{:.2f}"); M("YearRhoP", fmt_p(p))

    deg = dict(giant.degree(weight="weight"))
    rows = []
    for c in big:
        members = sorted([n for n in part if part[n] == c], key=lambda n: -deg[n])
        lab = relabel[c]
        words = ", ".join(shown(w) for w, _ in top_words.get(lab, [])[:5]) or "--"
        h = f"{hap.loc[lab, 'mean']:.2f}" if lab in hap.index else "--"
        yrs = [giant.nodes[n]["year"] for n in members if giant.nodes[n]["year"] > 0]
        rows.append(rf"C{lab} & {len(members)} & {int(np.median(yrs)) if yrs else '--'} & "
                    rf"{', '.join(tex(name(n)) for n in members[:3])} & {tex(words)} & {h} \\")
    (TAB / "communities.tex").write_text(
        "\\begin{tabular*}{\\textwidth}{@{\\extracolsep{\\fill}}lrr>{\\raggedright\\arraybackslash}p{4.6cm}>{\\raggedright\\arraybackslash}p{4.6cm}r@{}}\n"
        "Comm. & Artists & Year & Best-connected artists & Top TF-IDF words & Happiness \\\\\n\\midrule\n"
        + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular*}\n")

    # ---------------- network + text ----------------
    S = combine.artist_similarity(df)
    pairs = combine.edge_vs_nonedge(giant, S)
    sim_l, sim_u = pairs.loc[pairs.linked, "sim"].mean(), pairs.loc[~pairs.linked, "sim"].mean()
    M("SimLinked", sim_l, "{:.3f}"); M("SimUnlinked", sim_u, "{:.3f}")
    M("SimRatio", sim_l / sim_u, "{:.2f}")
    res = combine.permutation_test(giant, S, n_perm=1000)
    M("PermObserved", res["observed"], "{:.3f}"); M("PermNull", res["null_mean"], "{:.3f}")
    M("PermP", fmt_p(res["p_value"])); M("NumPerm", "1,000")
    wrho, wp = stats.spearmanr(pairs.loc[pairs.linked, "weight"], pairs.loc[pairs.linked, "sim"])
    M("WeightRho", wrho, "{:.2f}"); M("WeightRhoP", fmt_p(wp))
    same = pairs.apply(lambda r: part.get(r.u) == part.get(r.v), axis=1)
    M("SimSameComm", pairs.loc[same, "sim"].mean(), "{:.3f}")
    M("SimDiffComm", pairs.loc[~same, "sim"].mean(), "{:.3f}")

    # ---------------- credits vs Wikipedia ----------------
    to_wiki = {s["artist"]: s.get("wiki_title") for s in songs}
    common = [n for n in giant if to_wiki.get(name(n)) in wiki_part]
    if not toy and len(common) > 10:
        a = [part[n] for n in common]; b = [wiki_part[to_wiki[name(n)]] for n in common]
        nmi = normalized_mutual_info_score(a, b)
        rng = np.random.default_rng(config.RANDOM_SEED)
        nmi_null = np.mean([normalized_mutual_info_score(a, rng.permutation(b)) for _ in range(200)])
        M("WikiNMI", nmi, "{:.2f}"); M("WikiNMINull", nmi_null, "{:.2f}")
        U = D.to_undirected()
        lk = [U.has_edge(to_wiki[name(u)], to_wiki[name(v)]) for u, v in giant.edges()
              if to_wiki.get(name(u)) in U and to_wiki.get(name(v)) in U]
        nodes = [to_wiki[name(n)] for n in common]
        M("PctCreditEdgesOnWiki", 100 * np.mean(lk) if lk else 0, "{:.0f}")
        M("PctRandomOnWiki", 100 * nx.density(U.subgraph(nodes)), "{:.1f}")
    else:
        for k_ in ["WikiNMI", "WikiNMINull", "PctCreditEdgesOnWiki", "PctRandomOnWiki"]:
            M(k_, r"\textbf{[--]}")

    # ---------------- robustness: edge threshold theta ----------------
    word = {1: "One", 3: "Three"}
    for th in (1, 3):
        Gt = bn.project_artists(B, min_weight=th)
        gt = Gt.subgraph(max(nx.connected_components(Gt), key=len)).copy()
        _, qt = na.communities(gt)
        nt = na.modularity_null(gt, n_samples=10)
        rt = combine.permutation_test(gt, S, n_perm=1000)
        M(f"Theta{word[th]}Giant", gt.number_of_nodes(), "{:,}")
        M(f"Theta{word[th]}Q", qt, "{:.2f}"); M(f"Theta{word[th]}QNull", nt.mean(), "{:.2f}")
        M(f"Theta{word[th]}SimObs", rt["observed"], "{:.3f}")
        M(f"Theta{word[th]}SimNull", rt["null_mean"], "{:.3f}")
        M(f"Theta{word[th]}P", fmt_p(rt["p_value"]))

    # ---------------- figures ----------------
    fig_network(giant, part, relabel)
    fig_degrees(cdeg, G)
    fig_words(top_words, part, relabel, giant)
    fig_similarity(pairs, res, hap)

    # ---------------- write macros ----------------
    lines = ["% AUTO-GENERATED by make_paper_assets.py -- do not edit by hand"]
    lines += [rf"\newcommand{{\{k}}}{{{v}}}" for k, v in macros.items()]
    (PAPER / "results.tex").write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(macros)} numbers, 2 tables and 4 figures to {PAPER}")


# --------------------------------------------------------------------------------------
def _community_layout(giant, part):
    """Each community gets its own spring layout, placed around a circle (bigger
    communities get more room), so the families are visible instead of one hairball."""
    sizes = Counter(part[n] for n in giant)
    order = [c for c, _ in sizes.most_common()]
    pos, angle = {}, 0.0
    total = sum(np.sqrt(v) for v in sizes.values())
    for c in order:
        members = [n for n in giant if part[n] == c]
        sub = giant.subgraph(members)
        share = np.sqrt(sizes[c]) / total
        angle += np.pi * share
        centre = np.array([np.cos(angle), 0.62 * np.sin(angle)]) * (0 if len(order) == 1 else 1.0)
        angle += np.pi * share
        local = nx.spring_layout(sub, weight="weight", seed=config.RANDOM_SEED, iterations=200,
                                 k=1.2 / np.sqrt(max(len(sub), 1)))
        radius = 0.33 * np.sqrt(sizes[c] / max(sizes.values()))
        for n, xy in local.items():
            pos[n] = centre + radius * np.asarray(xy)
    return pos


def fig_network(giant, part, relabel):
    pos = _community_layout(giant, part)
    deg = dict(giant.degree())
    colours = [PALETTE[relabel[part[n]] - 1] if part[n] in relabel else GREY for n in giant]
    fig, ax = plt.subplots(figsize=(FULL_W, 3.7))
    nx.draw_networkx_edges(giant, pos, ax=ax, alpha=0.05, width=0.35)
    nx.draw_networkx_nodes(giant, pos, ax=ax, node_color=colours, linewidths=0.3, edgecolors="white",
                           node_size=[4 + 1.6 * deg[n] ** 0.9 for n in giant])
    for c in relabel:                                   # two best-connected artists per community
        members = sorted((n for n in giant if part[n] == c), key=deg.get, reverse=True)
        for j, n in enumerate(members[:2]):                # first label above, second below
            ax.annotate(name(n), pos[n], fontsize=5.5, ha="center",
                        va="bottom" if j == 0 else "top",
                        xytext=(0, 4 if j == 0 else -4), textcoords="offset points",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
    for c, lab in relabel.items():
        ax.scatter([], [], c=PALETTE[lab - 1], s=12, label=f"C{lab}")
    ax.legend(loc="lower left", frameon=False, ncol=6)
    ax.axis("off")
    fig.tight_layout(); fig.savefig(FIG / "fig1_network.pdf"); plt.close(fig)


def _logbin(values):
    v = np.asarray([x for x in values if x > 0], dtype=float)
    bins = np.unique(np.logspace(0, np.log10(v.max() + 1), 18).astype(int))
    h, e = np.histogram(v, bins=bins, density=True)
    c = np.sqrt(e[:-1] * e[1:])
    return c[h > 0], h[h > 0]


def fig_degrees(cdeg, G):
    fig, ax = plt.subplots(figsize=(COL_W, 2.4))
    x, y = _logbin(cdeg.values)
    ax.loglog(x, y, "o-", ms=3, lw=1, color=PALETTE[0], label="Songwriters/producers: artists per creator")
    x, y = _logbin([d for _, d in G.degree()])
    ax.loglog(x, y, "s-", ms=3, lw=1, color=PALETTE[1], label="Artists: degree in projected network")
    ax.set_xlabel("Degree $k$"); ax.set_ylabel("$p(k)$")
    ax.set_xticks([1, 2, 5, 10, 20, 50])
    ax.xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout(); fig.savefig(FIG / "fig2_degrees.pdf"); plt.close(fig)


def fig_words(top_words, part, relabel, giant):
    labs = sorted(top_words)[:6]
    fig, axes = plt.subplots(2, 3, figsize=(FULL_W, 3.0))
    for ax, lab in zip(axes.flat, labs):
        words = top_words[lab][::-1]
        ax.barh([shown(w) for w, _ in words], [s for _, s in words], color=PALETTE[lab - 1], height=0.7)
        size = sum(1 for n in part if relabel.get(part[n]) == lab)
        ax.set_title(f"C{lab} ({size} artists)", loc="left", fontweight="bold")
        ax.tick_params(axis="y", length=0)
        ax.set_xlabel("TF-IDF")
    for ax in list(axes.flat)[len(labs):]:
        ax.axis("off")
    fig.tight_layout(); fig.savefig(FIG / "fig3_words.pdf"); plt.close(fig)


def fig_similarity(pairs, res, hap):
    fig, axes = plt.subplots(1, 3, figsize=(FULL_W, 2.2))
    # (A) similarity by number of shared creators
    p = pairs.copy()
    p["bin"] = pd.cut(p["weight"], [-0.5, 0.5, 1.5, 2.5, 3.5, 5.5, np.inf],
                      labels=["0", "1", "2", "3", "4-5", "6+"])
    g = p.groupby("bin", observed=True)["sim"].agg(["mean", "sem", "count"])
    g = g[g["count"] >= 3]
    ax = axes[0]
    ax.errorbar(range(len(g)), g["mean"], yerr=1.96 * g["sem"], fmt="o-", ms=3, lw=1, color=PALETTE[0], capsize=2)
    ax.set_xticks(range(len(g))); ax.set_xticklabels(g.index)
    ax.set_xlabel("Shared songwriters/producers (edge weight)"); ax.set_ylabel("Lyric cosine similarity")
    ax.set_title("A", loc="left", fontweight="bold")
    # (B) permutation test
    ax = axes[1]
    ax.hist(res["null"], bins=40, color=GREY)
    ax.axvline(res["observed"], color=PALETTE[1], lw=1.5)
    ax.annotate("observed", (res["observed"], ax.get_ylim()[1] * 0.9), xytext=(-4, 0),
                textcoords="offset points", ha="right", color=PALETTE[1], fontsize=6)
    ax.set_xlabel("Mean similarity across edges (shuffled)"); ax.set_ylabel("Count")
    ax.set_title("B", loc="left", fontweight="bold")
    # (C) happiness per community
    ax = axes[2]
    h = hap.sort_index()
    for i, lab in enumerate(h.index):
        ax.errorbar(i, h.loc[lab, "mean"], yerr=1.96 * h.loc[lab, "sem"], fmt="o", ms=4,
                    color=PALETTE[int(lab) - 1], capsize=2)
    ax.set_xticks(range(len(h))); ax.set_xticklabels([f"C{int(l)}" for l in h.index])
    ax.set_ylabel("LabMT happiness"); ax.set_title("C", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(FIG / "fig4_similarity.pdf"); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--toy", action="store_true", help="use fake data to test the layout")
    main(ap.parse_args().toy)
