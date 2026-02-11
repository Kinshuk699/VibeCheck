# VibeCheck 🎧

**Audio Discovery & Mood Board** — Record 10 seconds of audio, identify the song, discover similar tracks, and watch the UI transform to match the music's vibe.

## How It Works

1. **Record** — Click "Record (10s)" to capture audio from your microphone.
2. **Identify** — The audio is sent to [ACRCloud](https://www.acrcloud.com/) for music recognition.
3. **Discover** — The identified track is looked up on [Last.fm](https://www.last.fm/) to fetch 5 recommended tracks and the top 3 genre/mood tags.
4. **Vibe** — The page background smoothly transitions to a genre-matched gradient + animated glow (20+ genre mappings).
5. **Visualize** — While recording, a full-screen canvas visualizer draws a circular frequency ring using the Web Audio API.
6. **Constellation** — The identified song becomes a center “star”, recommendations become orbiting “stars”, and you can click any star to recursively expand the map.

Each recommended track includes a **▶ YouTube** link for one-click listening.

## Features

- **One-click discovery**: YouTube search link per recommendation.
- **Smart recommendations**: If `track.getSimilar` is empty, the backend falls back to similar artists and/or tag-based top tracks.
- **Mood board**: Genre-driven gradients + glow.
- **Mic visualizer**: Circular spectrum ring (active only while recording).
- **Audio-driven motion**: Average frequency subtly scales the UI container; bass/treble influence pulse + bar height/speed.
- **Music Constellation**: Force-directed “galaxy” map with click-to-expand recursion.
  - **Pan + zoom**: Drag to pan, scroll to zoom.
  - **Gravity slider**: High gravity = tighter cluster; low gravity = sprawling galaxy.
  - **Star size**: Mapped to track popularity (Last.fm playcount).
  - **Line length**: Mapped to similarity score (closer = more similar).
  - **Deduped expansion**: Expansions avoid repeating tracks already in your map; existing stars get new edges instead of duplicates.

## Tech Stack

| Layer    | Technology |
|----------|------------|
| Frontend | HTML5, CSS (dynamic variables, transitions, keyframe glow), vanilla JavaScript (MediaRecorder + Web Audio API + Canvas) |
| Backend  | Python / Flask |
| APIs     | ACRCloud (music recognition), Last.fm (`track.getSimilar`, `track.getTopTags`, plus fallbacks: `artist.getSimilar`, `artist.getTopTracks`, `tag.getTopTracks`, `chart.getTopTracks`, `track.getInfo`) |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Kinshuk699/VibeCheck.git
cd VibeCheck

# 2. Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install flask requests python-dotenv

# 4. Add your API keys
cp .env.example .env
# Edit .env and fill in your real keys

# 5. Run
python app.py
```

Then open **http://127.0.0.1:5000/** and hit Record.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ACRCLOUD_HOST` | ACRCloud endpoint, e.g. `identify-ap-southeast-1.acrcloud.com` |
| `ACRCLOUD_ACCESS_KEY` | ACRCloud project access key |
| `ACRCLOUD_ACCESS_SECRET` | ACRCloud project secret key |
| `LASTFM_API_KEY` | Last.fm API key |

See [`.env.example`](.env.example) for the template.

## API

### `POST /identify`

- **Input**: `multipart/form-data` with an audio file in field `audio` (or `file`).
- **Output**: JSON containing `identified` track info and a `lastfm` block with:
  - `similar_tracks` (up to 5)
  - `top_tags` (up to 3)
  - `similar_sources` (which strategies were used)

### `POST /recommend`

Used by the Constellation click-to-expand logic.

- **Input**: JSON
  - `artist` (string)
  - `title` (string)
  - `exclude` (optional array): `[{"artist":"...","title":"..."}, ...]` tracks to filter out
- **Output**: JSON
  - `seed.playcount` (used for star size)
  - `lastfm.similar_tracks` (up to 5, filtered against `exclude`)
  - `lastfm.top_tags` (used for vibe coloring)

## Project Structure

```
├── app.py            # Flask backend (/identify + /recommend; ACRCloud + Last.fm logic)
├── index.html        # Single-page frontend (recorder, visualizer, mood board, constellation map)
├── .env.example      # Template for API keys
├── .env              # Your local keys (git-ignored)
├── .gitignore
├── vibecheck_specs.md
└── README.md
```

## License

MIT
