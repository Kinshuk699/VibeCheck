# Project: VibeCheck - Audio Discovery & Mood Board

## Core Objective

Build a local web app that:

1. Records 10 seconds of audio via the microphone.
2. Identifies the song using ACRCloud.
3. Finds similar tracks and genre/mood tags using Last.fm.
4. Updates the UI background (Mood Board) based on the song's tags.

## Technical Requirements

- **Frontend:** HTML5 (MediaRecorder API), CSS (Dynamic Variables), JavaScript.
- **Backend:** Python (Flask).
- **APIs:** - ACRCloud (Music Recognition).
  - Last.fm (Discovery/Similarity via `track.getSimilar` and `track.getTopTags`).

## Step-by-Step Logic

- **Recognition:** Send audio blob to Flask -> Forward to ACRCloud -> Get Artist/Title.
- **Discovery:** Use Artist/Title to query Last.fm for similar songs and top tags.
- **Visuals:** Map top tags (e.g., 'chill', 'electronic', 'rock') to a `vibeTheme` object in JS that updates the CSS background color and animation pulse.
