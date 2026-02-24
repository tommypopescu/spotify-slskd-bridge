# app/auth.py
import base64
import os
import time
import secrets
import logging
from typing import Optional, Dict, Tuple

import httpx
from starlette.responses import RedirectResponse, Response
from starlette.requests import Request

logger = logging.getLogger("uvicorn")

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8080/callback")
# Scop minim: user-read-private (nu cerem încă playlist-read-private)
SCOPE = os.getenv("SPOTIFY_USER_SCOPE", "user-read-private")

# Mică stocare în memorie (demo). Pentru producție: un vault/DB.
_user_token: Optional[Dict] = None
# mapări state -> timestamp (anti-CSRF)
_pending_states: Dict[str, int] = {}

def _basic_auth_header() -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError("SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET lipsesc din .env")
    return base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

def build_authorize_url(request: Request) -> str:
    state = secrets.token_urlsafe(24)
    _pending_states[state] = int(time.time())
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "show_dialog": "false",
    }
    from urllib.parse import urlencode
    url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    logger.info("[oauth] Redirect to Spotify auth (state=%s)", state)
    return url

def _exchange_code_for_token(code: str) -> Dict:
    headers = {
        "Authorization": f"Basic {_basic_auth_header()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
        resp.raise_for_status()
        return resp.json()

def _refresh_token(refresh_token: str) -> Dict:
    headers = {
        "Authorization": f"Basic {_basic_auth_header()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
        resp.raise_for_status()
        return resp.json()

def set_user_token(payload: Dict) -> None:
    # payload conține: access_token, token_type, expires_in, refresh_token?, scope
    now = int(time.time())
    exp = now + int(payload.get("expires_in", 3600))
    global _user_token
    _user_token = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "expires_at": exp,
        "scope": payload.get("scope", ""),
        "token_type": payload.get("token_type", "Bearer"),
    }
    logger.info("[oauth] Stored user token (exp in %ss; scope=%s)", exp - now, _user_token["scope"])

def get_user_access_token() -> Optional[str]:
    global _user_token
    if not _user_token:
        return None
    now = int(time.time())
    if _user_token["expires_at"] - 30 > now:
        return _user_token["access_token"]
    # refresh dacă avem refresh_token
    if _user_token.get("refresh_token"):
        try:
            data = _refresh_token(_user_token["refresh_token"])
            # Uneori refresh_token nu se întoarce din nou; păstrează-l pe cel vechi
            if "access_token" in data:
                _user_token["access_token"] = data["access_token"]
            if "refresh_token" in data and data["refresh_token"]:
                _user_token["refresh_token"] = data["refresh_token"]
            _user_token["expires_at"] = now + int(data.get("expires_in", 3600))
            logger.info("[oauth] User token refreshed (exp in %ss)", _user_token["expires_at"] - now)
            return _user_token["access_token"]
        except Exception as ex:
            logger.exception("[oauth] Failed to refresh user token: %s", ex)
            return None
    return None

def clear_user_token() -> None:
    global _user_token
    _user_token = None

def validate_state(state: str) -> bool:
    ts = _pending_states.pop(state, None)
    if not ts:
        return False
    # 10 minute TTL
    return (int(time.time()) - ts) < 600