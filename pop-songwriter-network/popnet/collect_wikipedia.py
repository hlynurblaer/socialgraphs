"""Step 1a: build the artist list and download each artist's Wikipedia page.

Run:  python -m popnet.collect_wikipedia
Out:  data/processed/artists.json  -> [{"title": ..., "wikitext": ...}, ...]
"""
import re
import time

import requests

from . import config
from .cache import cached_json, safe_name, save_json

API = "https://en.wikipedia.org/w/api.php"
session = requests.Session()
session.headers["User-Agent"] = config.USER_AGENT


def _api(params: dict) -> dict:
    params = {"format": "json", "formatversion": 2, **params}
    for attempt in range(6):
        r = session.get(API, params=params, timeout=30)
        if r.status_code == 429:                     # too many requests -> wait, retry
            time.sleep(int(r.headers.get("Retry-After", 0)) or 5 * 2 ** attempt)
            continue
        r.raise_for_status()
        time.sleep(0.1)  # be polite
        return r.json()
    r.raise_for_status()


def get_links(title: str) -> list[str]:
    """All article links (namespace 0) on a Wikipedia page."""
    links, cont = [], {}
    while True:
        data = _api({"action": "query", "prop": "links", "titles": title,
                     "plnamespace": 0, "pllimit": "max", "redirects": 1, **cont})
        for page in data["query"]["pages"]:
            links += [l["title"] for l in page.get("links", [])]
        if "continue" not in data:
            return links
        cont = data["continue"]


def get_wikitext(title: str) -> dict:
    """Wikitext of one page (follows redirects). Returns {'title', 'wikitext'}."""
    data = _api({"action": "query", "prop": "revisions", "rvprop": "content",
                 "rvslots": "main", "titles": title, "redirects": 1})
    page = data["query"]["pages"][0]
    if "missing" in page:
        return {"title": title, "wikitext": ""}
    text = page["revisions"][0]["slots"]["main"]["content"]
    return {"title": page["title"], "wikitext": text}


def get_wikitexts(titles: list[str]) -> dict[str, dict]:
    """Up to 50 pages in ONE request (much kinder to the API than one call per page).
    Returns {requested title: {'title': resolved title, 'wikitext': ...}}."""
    out, cont = {}, {}
    while True:
        data = _api({"action": "query", "prop": "revisions", "rvprop": "content",
                     "rvslots": "main", "titles": "|".join(titles), "redirects": 1, **cont})
        q = data["query"]
        alias = {t: t for t in titles}
        for step in ("normalized", "redirects"):
            for m in q.get(step, []):
                for k, v in alias.items():
                    if v == m["from"]:
                        alias[k] = m["to"]
        pages = {pg["title"]: pg for pg in q["pages"]}
        for req, final in alias.items():
            pg = pages.get(final, {})
            if "revisions" in pg:
                out[req] = {"title": final,
                            "wikitext": pg["revisions"][0]["slots"]["main"]["content"]}
        if "continue" not in data:
            break
        cont = data["continue"]
    for req in titles:
        out.setdefault(req, {"title": req, "wikitext": ""})
    return out


def prefetch(titles: list[str]) -> None:
    """Download (in batches of 50) every title that is not cached yet."""
    todo = [t for t in dict.fromkeys(titles)
            if not (config.DATA_RAW / "wikipedia" / f"{safe_name(t)}.json").exists()]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        for req, page in get_wikitexts(batch).items():
            save_json(config.DATA_RAW / "wikipedia" / f"{safe_name(req)}.json", page)
        print(f"  fetched {min(i + 50, len(todo))}/{len(todo)} pages")
        time.sleep(3)


def cached_page(title: str) -> dict:
    path = config.DATA_RAW / "wikipedia" / f"{safe_name(title)}.json"
    return cached_json(path, lambda: get_wikitext(title))


def is_musical_artist(wikitext: str) -> bool:
    """Keep only pages with a musician infobox (drops genre/label/city links)."""
    if re.search(r"\{\{\s*Infobox musical artist", wikitext, re.I):
        return True
    return bool(re.search(r"\{\{\s*Infobox person", wikitext, re.I)) and \
        bool(re.search(r"singer|musician|songwriter|rapper", wikitext[:5000], re.I))


def wiki_links_in(wikitext: str) -> set[str]:
    """Titles linked from a page's wikitext, e.g. [[Katy Perry|Perry]] -> 'Katy Perry'."""
    return {m.split("|")[0].split("#")[0].strip()
            for m in re.findall(r"\[\[([^\]]+)\]\]", wikitext)}


def collect_artists() -> list[dict]:
    candidates = list(config.SEED_ARTISTS)
    for list_page in config.ARTIST_LIST_PAGES:
        links = cached_json(config.DATA_RAW / "wikipedia" / f"LIST_{safe_name(list_page)}.json",
                            lambda p=list_page: get_links(p))
        print(f"{list_page}: {len(links)} links")
        candidates += links

    prefetch(candidates)
    artists, seen = [], set()
    for title in dict.fromkeys(candidates):          # keeps order, removes duplicates
        if len(artists) >= config.MAX_ARTISTS:
            break
        page = cached_page(title)
        if page["title"] in seen or not is_musical_artist(page["wikitext"]):
            continue
        seen.add(page["title"])
        artists.append(page)
        print(f"  [{len(artists)}] {page['title']}")

    save_json(config.DATA_PROCESSED / "artists.json", artists)
    return artists


if __name__ == "__main__":
    a = collect_artists()
    print(f"Saved {len(a)} artists to {config.DATA_PROCESSED / 'artists.json'}")
