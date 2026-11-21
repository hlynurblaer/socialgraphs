# Pop Songwriter Network — 02805 Final Project

**Research question:** Is pop music one big family built by a few songwriters, and do artists
who share songwriters also sound alike in their lyrics?

## Folder layout

```
pop-songwriter-network/
├── popnet/                  # all the real code lives here
│   ├── config.py            # paths, settings, API token
│   ├── cache.py             # save/load JSON so nothing is downloaded twice
│   ├── collect_wikipedia.py # Step 1a: artist list + Wikipedia pages
│   ├── collect_genius.py    # Step 1b: songs, credits, lyrics from Genius
│   ├── build_networks.py    # Step 2: bipartite, projected, features, wiki-link networks
│   ├── network_analysis.py  # Step 3: stats, degree, random nets, centrality, communities
│   ├── text_analysis.py     # Step 4: cleaning, TF-IDF, word clouds, LabMT sentiment
│   └── combine.py           # Step 5: lyric similarity vs network + permutation test
├── notebooks/
│   └── explainer_notebook.ipynb   # the hand-in notebook (course sections)
├── website/
│   └── index.html           # the story page (GitHub Pages)
├── data/
│   ├── raw/                 # cached API responses (not committed)
│   └── processed/           # cleaned tables, graphs
├── figures/                 # saved plots for the website
├── test_toy.py              # runs the pipeline on fake data (no internet needed)
└── requirements.txt
```

## What's done and what's left

| Step | Status |
| --- | --- |
| Wikipedia data (322 artists, `data/processed/artists.json`) | Done |
| LabMT word list (`data/raw/labmt.txt`) | Done |
| Genius songs, credits, lyrics | **You run this (needs your token)** |
| Paper text (`paper/main.tex`) | Written; numbers fill in automatically |
| Figures, tables, numbers | `make_paper_assets.py` makes them from the data |

## Finish the paper in 4 steps

1. **Genius download** (on your own computer; the lyrics site blocks cloud machines):
   ```bash
   pip install -r requirements.txt
   export GENIUS_TOKEN="your-token"      # Windows PowerShell: $env:GENIUS_TOKEN="your-token"
   python -m popnet.collect_genius
   ```
   ~322 artists x 30 songs; expect a few hours. It caches everything, so if it stops,
   just run it again and it continues where it left off.
   Then open `data/processed/artist_matches.csv` and check artists with no Genius match.
2. **Make the results:** `python make_paper_assets.py`
   (this replaces the red "TOY DATA" banner and every number, table and figure).
3. **Overleaf:** upload `paper/main.tex`, `paper/references.bib`, `paper/results.tex`,
   `paper/tables/` and `paper/figures/` into your PNAS template project. Compile.
4. **Edit the orange text:** search for `\Verify` in `main.tex`. Each one is an
   interpretation that must match the real numbers. Fix it, then remove the `\Verify{}`.

## Setup

```bash
pip install -r requirements.txt
export GENIUS_TOKEN="your-token"   # from https://genius.com/api-clients
```

Put the LabMT word list (`Data_Set_S1.txt` from Dodds et al. 2011, used in the course)
in `data/raw/labmt.txt`.

## Run order

```bash
python -m popnet.collect_wikipedia   # -> data/processed/artists.json
python -m popnet.collect_genius      # -> data/processed/songs.json
python test_toy.py                   # sanity check of steps 2-5 on fake data
```

Then open `notebooks/explainer_notebook.ipynb` and run it top to bottom.

Start small: set `MAX_ARTISTS = 20` in `config.py` until everything works end to end.

## Rules

- Never commit `data/raw/` or your Genius token.
- Before publishing the website, copy the PNGs you use from `figures/` into `website/figures/`.
- Never put full lyrics on the website — only counts, scores and word clouds.
