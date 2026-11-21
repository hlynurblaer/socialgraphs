"""FAKE songs for testing (made-up artists, writers and word lists). Never report these."""
import random

SCENES = {
    0: "dance night party lights floor tonight fire neon club move body".split(),
    1: "heart cry rain alone tears broken goodbye cold lonely memory sorry".split(),
    2: "money city drive fast gold crown boss shine diamond street flex".split(),
    3: "summer sun beach wave sky blue ocean free young wild golden".split(),
    4: "love forever kiss sweet together hold touch dream angel close".split(),
    5: "fight strong rise power stand loud scream brave war survive".split(),
}


def toy_songs(n_artists: int = 90, songs_each: int = 12, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    writers = {s: [f"Writer {s}{c}" for c in "ABCDEFG"] for s in SCENES}
    super_producers = ["Super Producer X", "Super Producer Y"]      # work across scenes
    songs = []
    for a in range(n_artists):
        scene = a % len(SCENES)
        for k in range(songs_each):
            w = rng.sample(writers[scene][: rng.randint(3, 7)], 2)
            if rng.random() < 0.12:
                w.append(rng.choice(writers[(scene + 1) % len(SCENES)]))
            if rng.random() < 0.08:
                w.append(rng.choice(super_producers))
            vocab = SCENES[scene] * 3 + SCENES[(scene + 1) % len(SCENES)]
            lyrics = "\n".join(" ".join(rng.choices(vocab, k=8)) for _ in range(14))
            songs.append({
                "song_id": a * 1000 + k, "title": f"Song {k}", "url": "",
                "year": 2000 + (scene * 4 + rng.randint(0, 6)) % 26,
                "artist_id": a, "artist": f"Toy Artist {a}", "wiki_title": f"Toy Artist {a}",
                "writers": [{"id": 0, "name": x} for x in w], "producers": [],
                "featured": [], "lyrics": "[Chorus]\n" + lyrics,
            })
    return songs
