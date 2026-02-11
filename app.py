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
        "autocorrect": "1",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise requests.HTTPError(f"Last.fm error {payload.get('error')}: {payload.get('message')}")
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


def _track_key(track: dict[str, Any]) -> tuple[str, str]:
    artist = (track.get("artist") or "")
    name = (track.get("name") or "")
    return (str(artist).strip().lower(), str(name).strip().lower())


def _merge_unique_tracks(
    base: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    out = list(base)
    seen = {_track_key(t) for t in out}
    for t in incoming:
        if len(out) >= limit:
            break
        key = _track_key(t)
        if key == ("", "") or key in seen:
            continue
        out.append(t)
        seen.add(key)
    return out


def _normalize_lastfm_artist(artist: str) -> str:
    # ACRCloud sometimes returns artist strings like "A/B/C" or "A & B".
    # For Last.fm calls, prefer the primary artist.
    s = str(artist or "").strip()
    for sep in ["/", "&", ",", ";"]:
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    for token in [" feat. ", " feat ", " ft. ", " ft ", " featuring "]:
        if token in s.lower():
            idx = s.lower().find(token)
            s = s[:idx].strip()
    return s


def _lastfm_get_similar_via_artist(*, artist: str, api_key: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fallback 1: get similar *artists*, then pick their top track."""
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "artist.getSimilar",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
        "autocorrect": "1",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise requests.HTTPError(f"Last.fm error {payload.get('error')}: {payload.get('message')}")
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
            "autocorrect": "1",
        }, timeout=15)
        tp.raise_for_status()
        tp_payload = tp.json()
        if "error" in tp_payload:
            continue
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
    if "error" in payload:
        raise requests.HTTPError(f"Last.fm error {payload.get('error')}: {payload.get('message')}")
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


def _lastfm_get_chart_top_tracks(*, api_key: str, limit: int = 5) -> list[dict[str, Any]]:
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "chart.getTopTracks",
        "api_key": api_key,
        "format": "json",
        "limit": str(limit),
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise requests.HTTPError(f"Last.fm error {payload.get('error')}: {payload.get('message')}")
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
        "autocorrect": "1",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise requests.HTTPError(f"Last.fm error {payload.get('error')}: {payload.get('message')}")
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

    # Normalize artist for Last.fm (ACRCloud may return multi-artist strings).
    lastfm_artist = _normalize_lastfm_artist(str(identified_artist))
    lastfm_track = str(identified_title).strip()

    # --- Fetch top tags first (needed for tag-based fallback) ---
    try:
        top_tags = _lastfm_get_top_tags(artist=lastfm_artist, track=lastfm_track, api_key=lastfm_api_key, limit=3)
    except requests.RequestException as e:
        top_tags = []
        lastfm_tags_error = str(e)
    else:
        lastfm_tags_error = None

    # --- Fetch recommendations using a merged strategy (up to 5 unique tracks) ---
    limit = 5
    similar_tracks: list[dict[str, Any]] = []
    similar_sources: list[str] = []

    # Strategy 1: track.getSimilar
    try:
        from_track = _lastfm_get_similar(artist=lastfm_artist, track=lastfm_track, api_key=lastfm_api_key, limit=limit)
    except requests.RequestException as e:
        from_track = []
        lastfm_similar_error = str(e)
    else:
        lastfm_similar_error = None

    if from_track:
        similar_sources.append("track.getSimilar")
        similar_tracks = _merge_unique_tracks(similar_tracks, from_track, limit=limit)

    # Strategy 2: artist.getSimilar → top track per artist (fill remaining)
    if len(similar_tracks) < limit:
        try:
            from_artist = _lastfm_get_similar_via_artist(artist=lastfm_artist, api_key=lastfm_api_key, limit=limit)
        except requests.RequestException:
            from_artist = []
        if from_artist:
            similar_sources.append("artist.getSimilar")
            similar_tracks = _merge_unique_tracks(similar_tracks, from_artist, limit=limit)

    # Strategy 3: tag.getTopTracks (fill remaining; try tags in order)
    if len(similar_tracks) < limit and top_tags:
        tag_collected: list[dict[str, Any]] = []
        for tag in top_tags:
            if len(tag_collected) >= limit:
                break
            try:
                from_tag = _lastfm_get_similar_via_tags(tags=[tag], api_key=lastfm_api_key, limit=limit)
            except requests.RequestException:
                continue
            tag_collected = _merge_unique_tracks(tag_collected, from_tag, limit=limit)
        if tag_collected:
            similar_sources.append("tag.getTopTracks")
            similar_tracks = _merge_unique_tracks(similar_tracks, tag_collected, limit=limit)

    # Final fallback: chart.getTopTracks (guarantees some recommendations)
    if len(similar_tracks) < limit:
        try:
            from_chart = _lastfm_get_chart_top_tracks(api_key=lastfm_api_key, limit=limit)
        except requests.RequestException:
            from_chart = []
        if from_chart:
            similar_sources.append("chart.getTopTracks")
            similar_tracks = _merge_unique_tracks(similar_tracks, from_chart, limit=limit)

    # Back-compat: keep a single field, but also expose detailed sources.
    similar_source = "merged" if len(similar_sources) > 1 else (similar_sources[0] if similar_sources else "none")

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
            "similar_sources": similar_sources,
            "top_tags": top_tags,
            "query": {
                "artist": lastfm_artist,
                "track": lastfm_track,
            },
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


@app.post("/recommend")
def recommend():
    """Return similar tracks + tags for a given artist/title (no audio needed).

    Expects JSON body: {"artist": "...", "title": "..."}
    Returns the same lastfm block as /identify so the frontend can reuse logic.
    """
    body = request.get_json(silent=True) or {}
    artist = (body.get("artist") or "").strip()
    title = (body.get("title") or "").strip()

    if not artist or not title:
        return jsonify({"error": "missing_artist_or_title",
                        "hint": "POST JSON with 'artist' and 'title'"}), 400

    # --- Build an exclusion set from tracks the frontend already has ---
    raw_exclude = body.get("exclude") or []  # [{"artist":"...","title":"..."}]
    exclude_keys: set[tuple[str, str]] = set()
    for ex in raw_exclude:
        a = str(ex.get("artist") or "").strip().lower()
        t = str(ex.get("title") or "").strip().lower()
        if a or t:
            exclude_keys.add((a, t))
    # Also exclude the seed itself
    exclude_keys.add((artist.strip().lower(), title.strip().lower()))

    lastfm_api_key = os.getenv("LASTFM_API_KEY", "YOUR_LASTFM_API_KEY")
    lastfm_artist = _normalize_lastfm_artist(artist)
    lastfm_track = title

    # --- Top tags ---
    try:
        top_tags = _lastfm_get_top_tags(artist=lastfm_artist, track=lastfm_track,
                                        api_key=lastfm_api_key, limit=3)
    except requests.RequestException:
        top_tags = []

    # --- Playcount (used for star size in the constellation) ---
    playcount = None
    try:
        info_resp = requests.get("https://ws.audioscrobbler.com/2.0/", params={
            "method": "track.getInfo",
            "artist": lastfm_artist,
            "track": lastfm_track,
            "api_key": lastfm_api_key,
            "format": "json",
            "autocorrect": "1",
        }, timeout=15)
        info_resp.raise_for_status()
        info_payload = info_resp.json()
        playcount = int(info_payload.get("track", {}).get("playcount", 0))
    except Exception:
        pass

    # --- Similar tracks (merged strategy, over-fetch then filter) ---
    desired = 5
    fetch_limit = desired + len(exclude_keys) + 10  # over-fetch to compensate for exclusions
    similar_tracks: list[dict[str, Any]] = []
    similar_sources: list[str] = []

    try:
        from_track = _lastfm_get_similar(artist=lastfm_artist, track=lastfm_track,
                                         api_key=lastfm_api_key, limit=fetch_limit)
    except requests.RequestException:
        from_track = []
    if from_track:
        similar_sources.append("track.getSimilar")
        similar_tracks = _merge_unique_tracks(similar_tracks, from_track, limit=fetch_limit)

    if len(similar_tracks) < fetch_limit:
        try:
            from_artist = _lastfm_get_similar_via_artist(artist=lastfm_artist,
                                                         api_key=lastfm_api_key, limit=fetch_limit)
        except requests.RequestException:
            from_artist = []
        if from_artist:
            similar_sources.append("artist.getSimilar")
            similar_tracks = _merge_unique_tracks(similar_tracks, from_artist, limit=fetch_limit)

    if len(similar_tracks) < fetch_limit and top_tags:
        tag_collected: list[dict[str, Any]] = []
        for tag in top_tags:
            if len(tag_collected) >= fetch_limit:
                break
            try:
                from_tag = _lastfm_get_similar_via_tags(tags=[tag], api_key=lastfm_api_key, limit=fetch_limit)
            except requests.RequestException:
                continue
            tag_collected = _merge_unique_tracks(tag_collected, from_tag, limit=fetch_limit)
        if tag_collected:
            similar_sources.append("tag.getTopTracks")
            similar_tracks = _merge_unique_tracks(similar_tracks, tag_collected, limit=fetch_limit)

    if len(similar_tracks) < desired:
        try:
            from_chart = _lastfm_get_chart_top_tracks(api_key=lastfm_api_key, limit=fetch_limit)
        except requests.RequestException:
            from_chart = []
        if from_chart:
            similar_sources.append("chart.getTopTracks")
            similar_tracks = _merge_unique_tracks(similar_tracks, from_chart, limit=fetch_limit)

    # --- Filter out excluded tracks and trim to desired count ---
    filtered: list[dict[str, Any]] = []
    for t in similar_tracks:
        key = _track_key(t)  # (artist.lower(), name.lower())
        if key in exclude_keys:
            continue
        filtered.append(t)
        if len(filtered) >= desired:
            break
    similar_tracks = filtered

    similar_source = "merged" if len(similar_sources) > 1 else (similar_sources[0] if similar_sources else "none")

    return jsonify({
        "seed": {"artist": artist, "title": title, "playcount": playcount},
        "lastfm": {
            "similar_tracks": similar_tracks,
            "similar_source": similar_source,
            "similar_sources": similar_sources,
            "top_tags": top_tags,
            "query": {"artist": lastfm_artist, "track": lastfm_track},
        },
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
