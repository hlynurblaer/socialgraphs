"""All settings in one place. Change things here, not inside the other files."""
import os
from pathlib import Path

# ---- Paths ----
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
for _p in (DATA_RAW, DATA_PROCESSED, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# ---- APIs ----
GENIUS_TOKEN = os.environ.get("GENIUS_TOKEN", "")
# Wikipedia asks every script to send a User-Agent with a way to contact you.
USER_AGENT = os.environ.get("WIKI_USER_AGENT", "02805-pop-network/0.1 (DTU student course project)")

# ---- Which artists ----
# Wikipedia list pages to pull artist links from.
# TODO: open each page in a browser to check it exists and fits; add more if needed.
ARTIST_LIST_PAGES = [
    "List of dance-pop artists",
]
# Artists you want for sure, even if they are not on the lists above.
SEED_ARTISTS = [
    "Katy Perry", "Taylor Swift", "Jessie J", "Ariana Grande", "Lady Gaga", "Rihanna",
    "Britney Spears", "Kesha", "Dua Lipa", "Selena Gomez", "Demi Lovato", "Miley Cyrus",
    "Ed Sheeran", "Justin Bieber", "Sia", "Ellie Goulding", "Rita Ora", "Charli XCX",
    "Olivia Rodrigo", "Billie Eilish", "Sabrina Carpenter", "The Weeknd", "Bruno Mars",
    "Beyonc\u00e9", "Christina Aguilera", "Pink (singer)", "Kelly Clarkson", "Camila Cabello",
    "Halsey (singer)", "Lizzo", "Doja Cat", "Harry Styles", "Shawn Mendes", "Meghan Trainor",
    "Zara Larsson", "Tove Lo", "Anne-Marie (singer)", "Little Mix", "One Direction",
    "Jason Derulo", "Carly Rae Jepsen", "Avril Lavigne", "Lorde", "Adele", "Sam Smith",
]
MAX_ARTISTS = 400         # start small; raise to 200-400 when everything works

# ---- Songs ----
SONGS_PER_ARTIST = 30     # most popular songs per artist on Genius (for credits)
LYRICS_PER_ARTIST = 15    # lyrics only for the top songs (lyrics download is the slow part)
YEAR_MIN, YEAR_MAX = 2000, 2025
DOWNLOAD_LYRICS = True

# ---- Network ----
MIN_EDGE_WEIGHT = 2       # artist-artist edge only if they share >= this many songwriters
RANDOM_SEED = 42

# ---- Manual Genius matches ----
# Wikipedia title -> (Genius artist id, Genius name) for artists the automatic name match
# misses (e.g. "P!nk", "Solange", stage names). Checked by hand via Genius search.
GENIUS_MANUAL_IDS = {
    "Pink (singer)": (345, "P!nk"), "Robyn": (1182, "Robyn"), "Prince (musician)": (660, "Prince"),
    "Jewel (singer)": (584449, "Jewel"), "Dev (singer)": (1038, "DEV"), "Hurts (duo)": (79399, "Hurts"),
    "T-ara": (18368, "T-ara"), "Five (group)": (148045, "Five"), "Annie (singer)": (288743, "Annie"),
    "Yazz": (1602555, "Yazz (Singer)"), "Mel and Kim": (372285, "Mel & Kim"),
    "Play (Swedish group)": (7431, "Play"), "Yuri (Mexican singer)": (2070069, "Yuri (MEX)"),
    "Globe (band)": (8233, "globe"), "Kisses (band)": (371340, "Kisses (Duo)"),
    "Luciana (singer)": (33538, "Luciana"), "Laila Bagge Wahlgren": (1213016, "Laila (SWE)"),
    "Speed (Japanese band)": (170161, "SPEED (JPN)"), "NRG (South Korean band)": (4025449, "NRG (KOR)"),
    "Move (Japanese band)": (2708616, "m.o.v.e (JPN)"), "Delorean (band)": (4770586, "DELOREAN (Band)"),
    "Cause and Effect (band)": (359269, "Cause & Effect"), "Joy (Austrian band)": (1555143, "Joy (AUT)"),
    "Company B (band)": (349615, "Company B"), "Private (band)": (356880, "Private"),
    "MiChi": (23965, "Michi"), "Choi Ye-na": (2304606, "YENA"),
    "Her Majesty & the Wolves": (368242, "Her Majesty And The Wolves"),
    "Jolin Tsai": (587674, "Jolin Tsai"), "Lisa Lisa and Cult Jam": (67252, "Lisa Lisa & Cult Jam"),
    "Momoiro Clover Z": (1430865, "Momoiro Clover Z"), "Teddy Sinclair": (22118, "Natalia Kills"),
    "Ricki-Lee Coulter": (365472, "Ricki-Lee"), "Seiko Matsuda": (290869, "Seiko Matsuda"),
    "Solange Knowles": (8371, "Solange"), "Tiffany Darwish": (4299, "Tiffany"),
    "Dan Snaith": (22962, "Caribou"), "James Murphy (electronic musician)": (1169, "LCD Soundsystem"),
    "Dev Hynes": (39971, "Devonté Hynes"),
}
