# app/spotify.py

import os
import time
import base64
import logging
from typing import List, Dict

import httpx

logger = logging.getLogger("uvicorn")

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_MARKET = os.getenv("SPOTIFY_MARKET", "RO")  # ex.: RO, US, DE (ISO 3166-1 alpha-2)

_token_cache: Dict[str, int | str | None] = {
    "access_token": None,
    "expires_at": 0,
}


async def _get_app_token() -> str:
    """
    Obține un access token prin Client Credentials Flow.
    Cache până aproape de expirare (with 30s skew).
    """
    now = int(time.time())
    if _token_cache["access_token"] and (_token_cache["expires_at"] - 30 > now):
        return _token_cache["access_token"]  # type: ignore

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET lipsesc din .env "
            "(necesare pentru Client Credentials)."
        )

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
            # Extras scurt din body pentru debugging
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


async def _auth_headers() -> Dict[str, str]:
    token = await _get_app_token()
    return {"Authorization": f"Bearer {token}"}


def _extract_playlist_id(raw: str) -> str:
    """
    Acceptă:
      - URL: https://open.spotify.com/playlist/<ID>?si=...
      - URI: spotify:playlist:<ID>
      - ID:  <ID>
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Playlist-ul nu a fost furnizat.")

    if raw.startswith("spotify:playlist:"):
        return raw.split(":")[-1]

    if "open.spotify.com/playlist/" in raw:
        # split pe 'playlist/' și taie query-ul/segmentul următor
        part = raw.split("playlist/")[1]
        part = part.split("?")[0]
        part = part.split("/")[0]
        if not part:
            raise ValueError("Nu am reușit să extrag ID-ul playlistului din URL.")
        return part

    # fallback: presupunem că e deja un ID
    return raw


async def get_playlist_tracks(raw_playlist: str) -> List[Dict]:
    """
    Returnează o listă de dict-uri:
      { 'title': <name>, 'artists': <comma-separated>, 'query': '<artists> - <title>' }
    Pentru Client Credentials funcționează cu playlisturi **publice**.
    """
    playlist_id = _extract_playlist_id(raw_playlist)
    url = f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks"

    items: List[Dict] = []
    # IMPORTANT: adăugăm 'market' pentru context fără user
    params = {
        "limit": 100,
        "additional_types": "track",
        "market": SPOTIFY_MARKET,
    }

    logger.info("[spotify] Fetch playlist items: id=%s market=%s", playlist_id, SPOTIFY_MARKET)

    async with httpx.AsyncClient(timeout=25) as client:
        next_url = url
        next_params = params

        while True:
            resp = await client.get(next_url, headers=await _auth_headers(), params=next_params)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as ex:
                # Mesaj clar pentru 403/404 etc.
                snippet = resp.text[:500]
                logger.error(
                    "[spotify] GET %s → %s; body: %s",
                    str(resp.request.url), resp.status_code, snippet
                )
                if resp.status_code == 403:
                    raise RuntimeError(
                        "Spotify: 403 Forbidden. Pentru Client Credentials sunt permise doar "
                        "playlisturi PUBLICe. Dacă playlistul este privat/colaborativ, "
                        "trebuie Authorization Code Flow + scope (ex.: playlist-read-private). "
                        f"Detalii: {str(resp.request.url)} → 403"
                    ) from ex
                raise RuntimeError(
                    f"Spotify GET {str(resp.request.url)} → {resp.status_code}: {snippet}"
                ) from ex

            data = resp.json()
            for it in data.get("items", []):
                track = it.get("track") or {}
                if not track or track.get("type") != "track":
                    # ignorăm episoade/podcast ori iteme invalide
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
            # când avem 'next', Spotify include deja query-ul; nu mai trimitem params separat
            next_params = {}

    logger.info("[spotify] Parsed %d track(s) from playlist %s", len(items), playlist_id)
    return items