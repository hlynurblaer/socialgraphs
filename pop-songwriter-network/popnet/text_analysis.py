"""Step 4: text analysis (course weeks 5-7)."""
import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from . import config

# Words that fill pop lyrics but say nothing. TODO: grow this list after looking at counts.
LYRIC_STOP_WORDS = {"oh", "ooh", "yeah", "ah", "na", "la", "hey", "uh", "woah", "whoa",
                    "baby", "gonna", "wanna", "gotta", "like", "just", "got", "don", "ll",
                    "ve", "re", "im", "cause", "let", "know", "da", "mmm", "ya",
                    "wan", "ayy", "ay", "eh", "mm", "ha", "huh", "uh", "ohh", "ooh", "doo", "redone"}
STOP_WORDS = set(ENGLISH_STOP_WORDS) | LYRIC_STOP_WORDS
MIN_ENGLISH_SHARE = 0.25   # songs below this share of English stop words are dropped


def clean_lyrics(text: str) -> str:
    """Remove Genius extras: '[Chorus: X]', the 'Lyrics' header, 'Embed' at the end."""
    text = re.sub(r"\[.*?\]", " ", text)
    text = re.sub(r"^.*?Lyrics", "", text, count=1, flags=re.S)   # header line from lyricsgenius
    text = re.sub(r"\d*Embed$", "", text.strip())
    return text.lower()


def _is_contraction(t: str) -> bool:
    """"i'm", "don't", "you'll" ... -> True (stop word + clitic, or any n't)."""
    if "'" not in t:
        return False
    base = t.split("'", 1)[0]
    return t.endswith("n't") or base in STOP_WORDS or base in {"i", "y", "ya"}


def tokenize(text: str, remove_stop: bool = True) -> list[str]:
    tokens = re.findall(r"[a-z']+", text.lower().replace("\u2019", "'"))
    tokens = [t.strip("'") for t in tokens if len(t.strip("'")) > 1]
    if not remove_stop:
        return tokens
    return [t for t in tokens if t not in STOP_WORDS and not _is_contraction(t)]


def english_share(text: str) -> float:
    """Share of tokens that are English stop words: ~0.45 for English lyrics,
    < 0.2 for Swedish, Spanish, Korean, ... Used to keep only English songs."""
    toks = tokenize(text, remove_stop=False)
    return float(np.mean([t in ENGLISH_STOP_WORDS for t in toks])) if toks else 0.0


def unique_lines(text: str) -> str:
    """Keep each line once, so a chorus sung 6 times does not count 6 times."""
    return "\n".join(dict.fromkeys(l.strip() for l in text.splitlines() if l.strip()))


def songs_dataframe(songs: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(songs)
    df["clean"] = df["lyrics"].fillna("").map(clean_lyrics).map(unique_lines)
    df["clean"] = df["clean"].str.replace("\u2019", "'")
    df["english"] = df["clean"].map(english_share)
    df["tokens"] = df["clean"].map(tokenize)
    df = df[df["tokens"].map(len) > 20]            # drop instrumentals / failed downloads
    return df[df["english"] >= MIN_ENGLISH_SHARE]   # the lexicon and stop words are English


def tfidf_by_group(docs: dict[str, list[str]], top_n: int = 15) -> dict[str, list[tuple]]:
    """docs = {group: tokens}. One document per group -> top TF-IDF words per group."""
    groups = list(docs)
    vec = TfidfVectorizer(analyzer=lambda toks: toks, sublinear_tf=True)
    X = vec.fit_transform([docs[g] for g in groups])
    vocab = np.array(vec.get_feature_names_out())
    out = {}
    for i, g in enumerate(groups):
        row = X[i].toarray().ravel()
        idx = row.argsort()[::-1][:top_n]
        out[g] = list(zip(vocab[idx], row[idx].round(3)))
    return out


def tfidf_artist_idf(groups: dict, artist_tokens: dict, top_n: int = 15,
                     min_artists: int = 5) -> dict[str, list[tuple]]:
    """Characteristic words of groups of artists (e.g. communities).
    groups = {group: [artist, ...]}, artist_tokens = {artist: tokens}.
    tfidf(t, g) = (1 + ln k_tg) * (ln((1 + N) / (1 + n_t)) + 1), where k_tg is the number of
    artists in g who use t, N the number of artists and n_t the number using t anywhere.
    Counting artists rather than occurrences stops one song that repeats a word
    ("button", "bam") from defining a whole community; with only a handful of groups an
    IDF over groups would be almost flat, so the IDF is taken over artists. Words used by
    fewer than `min_artists` artists (names, one-off ad-libs) are skipped."""
    sets = {a: set(t) for a, t in artist_tokens.items()}
    n_t = Counter(t for v in sets.values() for t in v)
    N = len(sets)
    out = {}
    for g, members in groups.items():
        k = Counter(t for a in members if a in sets for t in sets[a]
                    if n_t[t] >= min_artists and len(t) > 2)
        sc = {t: (1 + np.log(c)) * (np.log((1 + N) / (1 + n_t[t])) + 1) for t, c in k.items()}
        norm = np.sqrt(sum(v * v for v in sc.values())) or 1.0
        best = sorted(sc, key=lambda t: (-sc[t], t))[:top_n]
        out[g] = [(t, round(sc[t] / norm, 3)) for t in best]
    return out


def wordcloud_for(word_scores: dict[str, float], path) -> None:
    from wordcloud import WordCloud
    wc = WordCloud(width=800, height=400, background_color="white")
    wc.generate_from_frequencies(word_scores).to_file(str(path))


# ---- LabMT sentiment (Dodds et al. 2011) ----
def load_labmt(path=None) -> dict[str, float]:
    """LabMT word -> happiness (1-9). Works with the paper's Data_Set_S1.txt (3 info lines
    first) and with labMT1.txt from the `labMTsimple` package (pip install labMTsimple)."""
    path = path or config.DATA_RAW / "labmt.txt"
    lines = open(path, encoding="utf-8").read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.lower().startswith("word"))
    header = lines[start].split("\t")
    col = next(i for i, h in enumerate(header) if h.startswith("happ"))
    out = {}
    for l in lines[start + 1:]:
        parts = l.split("\t")
        if len(parts) > col:
            out[parts[0]] = float(parts[col])
    return out


def happiness(tokens: list[str], labmt: dict[str, float], exclude_neutral: float = 1.0) -> float:
    """Average LabMT happiness. Words within +-exclude_neutral of 5 are skipped
    (the 'delta h' trick from the paper) so neutral words don't drown the signal."""
    counts = Counter(t for t in tokens if t in labmt and abs(labmt[t] - 5) >= exclude_neutral)
    total = sum(counts.values())
    return np.nan if total == 0 else sum(labmt[w] * c for w, c in counts.items()) / total


def vader_score(text: str) -> float:
    """Second opinion: VADER compound score (-1 sad ... +1 happy)."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    return SentimentIntensityAnalyzer().polarity_scores(text)["compound"]
