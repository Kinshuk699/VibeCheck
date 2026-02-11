# VibeCheck 🎧

**Audio Discovery & Mood Board** — Record 10 seconds of audio, identify the song, discover similar tracks, and watch the UI transform to match the music's vibe.

## How It Works

1. **Record** — Click "Record (10s)" to capture audio from your microphone.
2. **Identify** — The audio is sent to [ACRCloud](https://www.acrcloud.com/) for music recognition.
3. **Discover** — The identified track is looked up on [Last.fm](https://www.last.fm/) to fetch 5 similar songs and the top 3 genre/mood tags.
4. **Vibe** — The page background smoothly transitions to a gradient + animated glow that matches the detected genre (electronic → neon purple, chill → sky blue, rock → deep red, and 20+ more).

Each recommended track includes a **▶ YouTube** link for one-click listening.

## Tech Stack

| Layer    | Technology |
|----------|------------|
| Frontend | HTML5, CSS (dynamic variables, transitions, keyframe glow), vanilla JavaScript (MediaRecorder API) |
| Backend  | Python / Flask |
| APIs     | ACRCloud (music recognition), Last.fm (`track.getSimilar`, `track.getTopTags`) |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/VibeCheck.git
cd VibeCheck

# 2. Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install flask requests acrcloud python-dotenv

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

## Project Structure

```
├── app.py            # Flask backend (/identify route + ACRCloud & Last.fm logic)
├── index.html        # Single-page frontend (recorder, results, vibe mapping)
├── .env.example      # Template for API keys
├── .env              # Your local keys (git-ignored)
├── .gitignore
├── vibecheck_specs.md
└── README.md
```

## License

MIT
