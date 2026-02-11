from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

app = Flask(__name__)


@app.get("/")
def index():
    return send_from_directory(".", "index.html")


def _acrcloud_signature(*, method: str, uri: str, access_key: str, data_type: str, signature_version: str, timestamp: str, access_secret: str) -> str:
    string_to_sign = "\n".join([method, uri, access_key, data_type, signature_version, timestamp])
    digest = hmac.new(access_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def _pick_first_metadata(acr_response: dict[str, Any]) -> dict[str, Any] | None:
    music = (
        acr_response.get("metadata", {})
        .get("music", [])
    )
    if not music:
        return None
    return music[0]


def _lastfm_get_similar(*, artist: str, track: str, api_key: str, limit: int = 5) -> list[dict[str, Any]]:
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "track.getSimilar",
        "artist": artist,
        "track": track,
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    tracks = payload.get("similartracks", {}).get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]
    out: list[dict[str, Any]] = []
    for t in tracks[:limit]:
        out.append(
            {
                "name": t.get("name"),
                "artist": (t.get("artist") or {}).get("name") if isinstance(t.get("artist"), dict) else t.get("artist"),
                "url": t.get("url"),
                "match": t.get("match"),
            }
        )
    return out


def _lastfm_get_similar_via_artist(*, artist: str, api_key: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fallback 1: get similar *artists*, then pick their top track."""
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "artist.getSimilar",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    artists = payload.get("similarartists", {}).get("artist", [])
    if isinstance(artists, dict):
        artists = [artists]

    out: list[dict[str, Any]] = []
    for a in artists[:limit]:
        a_name = a.get("name")
        if not a_name:
            continue
        # Fetch the artist's top track
        tp = requests.get(url, params={
            "method": "artist.getTopTracks",
            "artist": a_name,
            "api_key": api_key,
            "format": "json",
            "limit": "1",
        }, timeout=15)
        tp.raise_for_status()
        tp_payload = tp.json()
        top_tracks = tp_payload.get("toptracks", {}).get("track", [])
        if isinstance(top_tracks, dict):
            top_tracks = [top_tracks]
        if top_tracks:
            t = top_tracks[0]
            out.append({
                "name": t.get("name"),
                "artist": a_name,
                "url": t.get("url"),
                "match": a.get("match"),
            })
    return out


def _lastfm_get_similar_via_tags(*, tags: list[str], api_key: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fallback 2: use the top tag to find popular tracks in that genre."""
    if not tags:
        return []
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "tag.getTopTracks",
        "tag": tags[0],
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    tracks = payload.get("tracks", {}).get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]
    out: list[dict[str, Any]] = []
    for t in tracks[:limit]:
        out.append({
            "name": t.get("name"),
            "artist": (t.get("artist") or {}).get("name") if isinstance(t.get("artist"), dict) else t.get("artist"),
            "url": t.get("url"),
            "match": None,
        })
    return out


def _lastfm_get_top_tags(*, artist: str, track: str, api_key: str, limit: int = 3) -> list[str]:
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "track.getTopTags",
        "artist": artist,
        "track": track,
        "api_key": api_key,
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    tags = payload.get("toptags", {}).get("tag", [])
    if isinstance(tags, dict):
        tags = [tags]
    names: list[str] = []
    for tag in tags:
        name = tag.get("name")
        if name:
            names.append(str(name))
        if len(names) >= limit:
            break
    return names


@app.post("/identify")
def identify():
    # Expected: multipart/form-data with a file field named "audio" (or "file").
    audio_file = request.files.get("audio") or request.files.get("file")
    if audio_file is None:
        return jsonify({"error": "missing_audio_file", "hint": "POST multipart/form-data with field 'audio'"}), 400

    audio_bytes = audio_file.read()
    if not audio_bytes:
        return jsonify({"error": "empty_audio_file"}), 400

    # ACRCloud credentials (placeholders by default)
    acr_host = os.getenv("ACRCLOUD_HOST", "YOUR_ACRCLOUD_HOST")  # e.g. "identify-us-west-2.acrcloud.com"
    acr_access_key = os.getenv("ACRCLOUD_ACCESS_KEY", "YOUR_ACRCLOUD_ACCESS_KEY")
    acr_access_secret = os.getenv("ACRCLOUD_ACCESS_SECRET", "YOUR_ACRCLOUD_ACCESS_SECRET")

    # Last.fm credentials (placeholder by default)
    lastfm_api_key = os.getenv("LASTFM_API_KEY", "YOUR_LASTFM_API_KEY")

    # Build ACRCloud signed request (HTTP REST API)
    http_method = "POST"
    http_uri = "/v1/identify"
    data_type = "audio"
    signature_version = "1"
    timestamp = str(int(time.time()))
    signature = _acrcloud_signature(
        method=http_method,
        uri=http_uri,
        access_key=acr_access_key,
        data_type=data_type,
        signature_version=signature_version,
        timestamp=timestamp,
        access_secret=acr_access_secret,
    )

    acr_url = f"https://{acr_host}{http_uri}"
    files = {"sample": (audio_file.filename or "audio.wav", audio_bytes)}
    data = {
        "access_key": acr_access_key,
        "data_type": data_type,
        "signature_version": signature_version,
        "signature": signature,
        "timestamp": timestamp,
        "sample_bytes": str(len(audio_bytes)),
    }

    try:
        acr_resp = requests.post(acr_url, data=data, files=files, timeout=30)
        acr_resp.raise_for_status()
        acr_payload = acr_resp.json()
    except requests.RequestException as e:
        return jsonify({"error": "acrcloud_request_failed", "details": str(e)}), 502
    except ValueError:
        return jsonify({"error": "acrcloud_invalid_json"}), 502

    status = (acr_payload.get("status") or {})
    if status.get("code") != 0:
        return jsonify({"error": "acrcloud_no_match", "acrcloud_status": status, "raw": acr_payload}), 404

    first = _pick_first_metadata(acr_payload)
    if first is None:
        return jsonify({"error": "acrcloud_no_metadata", "raw": acr_payload}), 502

    identified_artist = ((first.get("artists") or [{}])[0]).get("name") or first.get("artist")
    identified_title = first.get("title")

    if not identified_artist or not identified_title:
        return jsonify({"error": "acrcloud_missing_artist_or_title", "raw": acr_payload}), 502

    # --- Fetch top tags first (needed for tag-based fallback) ---
    try:
        top_tags = _lastfm_get_top_tags(artist=str(identified_artist), track=str(identified_title), api_key=lastfm_api_key, limit=3)
    except requests.RequestException as e:
        top_tags = []
        lastfm_tags_error = str(e)
    else:
        lastfm_tags_error = None

    # --- Fetch similar tracks with cascading fallbacks ---
    similar_source = "track.getSimilar"
    try:
        similar_tracks = _lastfm_get_similar(artist=str(identified_artist), track=str(identified_title), api_key=lastfm_api_key, limit=5)
    except requests.RequestException as e:
        similar_tracks = []
        lastfm_similar_error = str(e)
    else:
        lastfm_similar_error = None

    # Fallback 1: similar artists → their top tracks
    if not similar_tracks:
        similar_source = "artist.getSimilar"
        try:
            similar_tracks = _lastfm_get_similar_via_artist(artist=str(identified_artist), api_key=lastfm_api_key, limit=5)
        except requests.RequestException:
            similar_tracks = []

    # Fallback 2: tag-based top tracks
    if not similar_tracks and top_tags:
        similar_source = "tag.getTopTracks"
        try:
            similar_tracks = _lastfm_get_similar_via_tags(tags=top_tags, api_key=lastfm_api_key, limit=5)
        except requests.RequestException:
            similar_tracks = []

    result = {
        "identified": {
            "artist": identified_artist,
            "title": identified_title,
            "album": (first.get("album") or {}).get("name") if isinstance(first.get("album"), dict) else first.get("album"),
            "release_date": first.get("release_date"),
            "duration_ms": first.get("duration_ms"),
            "score": first.get("score"),
            "acrid": first.get("acrid"),
        },
        "lastfm": {
            "similar_tracks": similar_tracks,
            "similar_source": similar_source,
            "top_tags": top_tags,
            "errors": {
                "similar": lastfm_similar_error,
                "tags": lastfm_tags_error,
            },
        },
        "raw": {
            "acrcloud": acr_payload,
        },
    }

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
