# app/spotify.py

import os
import time
import base64
import logging
from typing import List, Dict, Optional

import httpx
from . import auth  # <-- folosim user token, dacă este disponibil

logger = logging.getLogger("uvicorn")

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "RO")

_token_cache: Dict[str, int | str | None] = {
    "access_token": None,
    "expires_at": 0,
}

async def _get_app_token() -> str:
    now = int(time.time())
    if _token_cache["access_token"] and (_token_cache["expires_at"] - 30 > now):
        return _token_cache["access_token"]  # type: ignore

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET lipsesc din .env")

    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials"}

    logger.info("[spotify] Requesting app token via Client Credentials")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as ex:
            raise RuntimeError(
                f"Spotify /api/token → {resp.status_code}: {resp.text[:300]}"
            ) from ex

        payload = resp.json()
        access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = now + expires_in
        logger.info("[spotify] Received app token (expires_in=%ss)", expires_in)
        return access_token

async def _auth_headers(prefer_user: bool = True) -> Dict[str, str]:
    token: Optional[str] = None
    if prefer_user:
        token = auth.get_user_access_token()
    if not token:
        token = await _get_app_token()
    return {"Authorization": f"Bearer {token}"}

def _extract_playlist_id(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Playlist-ul nu a fost furnizat.")
    if raw.startswith("spotify:playlist:"):
        return raw.split(":")[-1]
    if "open.spotify.com/playlist/" in raw:
        part = raw.split("playlist/")[1].split("?")[0].split("/")[0]
        if not part:
            raise ValueError("Nu am reușit să extrag ID-ul playlistului din URL.")
        return part
    return raw

async def get_playlist_tracks(raw_playlist: str, prefer_user: bool = True) -> List[Dict]:
    """
    Folosește token de user (dacă e disponibil) pentru a evita restricțiile (403) chiar la playlisturi publice,
    altfel cade pe app token (Client Credentials).  [1](https://developer.spotify.com/documentation/web-api/reference/get-playlist)[2](https://github.com/spotipy-dev/spotipy/issues/484)
    """
    playlist_id = _extract_playlist_id(raw_playlist)
    base_url = f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks"

    items: List[Dict] = []
    params = {
        "limit": 100,
        "additional_types": "track",
        "market": SPOTIFY_MARKET,
    }

    logger.info("[spotify] Fetch playlist items: id=%s market=%s", playlist_id, SPOTIFY_MARKET)

    async with httpx.AsyncClient(timeout=25) as client:
        next_url = base_url
        next_params = params
        while True:
            resp = await client.get(next_url, headers=await _auth_headers(prefer_user=prefer_user), params=next_params)
            if resp.status_code == 403 and prefer_user is False:
                # dacă e 403 cu app token, nu mai avem ce face
                snippet = resp.text[:500]
                logger.error("[spotify] GET %s → 403 (app-token); body: %s", str(resp.request.url), snippet)
                raise RuntimeError(
                    "Spotify: 403 Forbidden chiar și cu app token. Verifică Dev Mode/market. "
                    f"URL: {str(resp.request.url)}"
                )
            if resp.status_code == 403 and prefer_user is True:
                # Retry o singură dată forțând user token (dacă nu era)
                logger.warning("[spotify] 403; retry with user token if available")
                resp = await client.get(next_url, headers=await _auth_headers(prefer_user=True), params=next_params)

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as ex:
                snippet = resp.text[:500]
                logger.error(
                    "[spotify] GET %s → %s; body: %s",
                    str(resp.request.url), resp.status_code, snippet
                )
                raise RuntimeError(
                    f"Spotify GET {str(resp.request.url)} → {resp.status_code}: {snippet}"
                ) from ex

            data = resp.json()
            for it in data.get("items", []):
                track = it.get("track") or {}
                if not track or track.get("type") != "track":
                    continue
                name = (track.get("name") or "").strip()
                artists = ", ".join(
                    [a.get("name", "").strip() for a in track.get("artists", []) if a]
                ).strip()
                if not name:
                    continue
                items.append(
                    {
                        "title": name,
                        "artists": artists,
                        "query": f"{artists} - {name}".strip() if artists else name,
                    }
                )
            next_url = data.get("next")
            if not next_url:
                break
            next_params = {}  # next are deja querystring
    logger.info("[spotify] Parsed %d track(s) from playlist %s", len(items), playlist_id)
    return items