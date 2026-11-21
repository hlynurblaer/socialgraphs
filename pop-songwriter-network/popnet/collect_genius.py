"""Step 1b: for each artist, get their popular songs + writer/producer credits + lyrics.

Run:  export GENIUS_TOKEN=...   then   python -m popnet.collect_genius
In:   data/processed/artists.json
Out:  data/processed/songs.json         (one dict per song, see `slim_song`)
      data/processed/artist_matches.csv (Wikipedia title -> Genius artist; CHECK BY HAND)
"""
import re
import time
import unicodedata

import pandas as pd
import requests

from . import config
from .cache import cached_json, load_json, save_json

BASE = "https://api.genius.com"


def _get(endpoint: str, params: dict | None = None) -> dict:
    if not config.GENIUS_TOKEN:
        raise RuntimeError("Set the GENIUS_TOKEN environment variable first.")
    headers = {"Authorization": f"Bearer {config.GENIUS_TOKEN}"}
    for attempt in range(5):
        r = requests.get(BASE + endpoint, params=params, headers=headers, timeout=30)
        if r.status_code == 429:                     # rate limited -> wait and retry
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        time.sleep(0.2)
        return r.json()["response"]
    raise RuntimeError(f"Gave up on {endpoint}")


def normalize(name: str) -> str:
    """'Beyoncé' -> 'beyonce', 'P!nk' -> 'pnk'; used for matching names."""
    name = re.sub(r"\s*\(.*?\)", "", name)          # 'Jessie J (singer)' -> 'Jessie J'
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_artist(wiki_title: str) -> dict | None:
    """Search Genius and return the primary artist whose name matches best."""
    if wiki_title in config.GENIUS_MANUAL_IDS:
        gid, gname = config.GENIUS_MANUAL_IDS[wiki_title]
        return {"id": gid, "name": gname}
    query = re.sub(r"\s*\(.*?\)", "", wiki_title)
    res = cached_json(config.DATA_RAW / "genius" / "search" / f"{normalize(query)}.json",
                      lambda: _get("/search", {"q": query}))
    target = normalize(query)
    for hit in res["hits"]:
        a = hit["result"]["primary_artist"]
        if normalize(a["name"]) == target:
            return {"id": a["id"], "name": a["name"]}
    return None  # misses: add them to config.GENIUS_MANUAL_IDS


def artist_song_ids(artist_id: int, n: int) -> list[int]:
    """Ids of the artist's most popular songs where they are the main artist."""
    def fetch():
        ids, page = [], 1
        while page and len(ids) < n:
            res = _get(f"/artists/{artist_id}/songs",
                       {"sort": "popularity", "per_page": 50, "page": page})
            ids += [s["id"] for s in res["songs"] if s["primary_artist"]["id"] == artist_id]
            page = res.get("next_page")
        return ids[:n]
    return cached_json(config.DATA_RAW / "genius" / "artist_songs" / f"{artist_id}.json", fetch)


def song_details(song_id: int) -> dict:
    return cached_json(config.DATA_RAW / "genius" / "songs" / f"{song_id}.json",
                       lambda: _get(f"/songs/{song_id}")["song"])


def slim_song(s: dict) -> dict:
    """Keep only the fields we use."""
    people = lambda key: [{"id": p["id"], "name": p["name"]} for p in s.get(key) or []]
    year = (s.get("release_date_components") or {}).get("year")
    if year is None and s.get("release_date"):          # API now only gives "YYYY-MM-DD"
        year = int(s["release_date"][:4])
    return {
        "song_id": s["id"], "title": s["title"], "url": s["url"], "year": year,
        "artist_id": s["primary_artist"]["id"], "artist": s["primary_artist"]["name"],
        "writers": people("writer_artists"),
        "producers": people("producer_artists"),
        "featured": people("featured_artists"),
    }


def get_lyrics(song: dict) -> str:
    """Lyrics via lyricsgenius (it scrapes the Genius web page). Cached per song."""
    import lyricsgenius
    path = config.DATA_RAW / "genius" / "lyrics" / f"{song['song_id']}.json"

    def fetch():
        g = lyricsgenius.Genius(config.GENIUS_TOKEN, timeout=30, retries=3,
                                remove_section_headers=False)
        return {"lyrics": g.lyrics(song_url=song["url"]) or ""}
    return cached_json(path, fetch)["lyrics"]


def collect_songs() -> list[dict]:
    artists = load_json(config.DATA_PROCESSED / "artists.json")
    matches, songs = [], []
    for i, a in enumerate(artists, 1):
        g = find_artist(a["title"])
        matches.append({"wiki_title": a["title"], "genius_id": g and g["id"],
                        "genius_name": g and g["name"]})
        if not g:
            print(f"[{i}] NO MATCH: {a['title']}")
            continue
        n_kept = 0
        for sid in artist_song_ids(g["id"], config.SONGS_PER_ARTIST):
            try:
                s = slim_song(song_details(sid))
            except Exception as e:                   # one bad song should not stop the run
                print(f"    skip song {sid}: {e}")
                continue
            if s["year"] is None or not (config.YEAR_MIN <= s["year"] <= config.YEAR_MAX):
                continue
            s["wiki_title"] = a["title"]
            s["lyrics"] = ""
            if config.DOWNLOAD_LYRICS and n_kept < config.LYRICS_PER_ARTIST:
                try:
                    s["lyrics"] = get_lyrics(s)
                except Exception as e:
                    print(f"    no lyrics for {s['title']}: {e}")
            songs.append(s)
            n_kept += 1
        print(f"[{i}] {a['title']}: {n_kept} songs")

    pd.DataFrame(matches).to_csv(config.DATA_PROCESSED / "artist_matches.csv", index=False)
    save_json(config.DATA_PROCESSED / "songs.json", songs)
    return songs


if __name__ == "__main__":
    s = collect_songs()
    with_credits = sum(bool(x["writers"] or x["producers"]) for x in s)
    print(f"Saved {len(s)} songs; {with_credits} have writer/producer credits.")
