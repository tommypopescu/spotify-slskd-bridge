# app/main.py
import logging
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .spotify import get_playlist_tracks
from . import auth
from .slskd import search_in_slskd

logger = logging.getLogger("uvicorn")

app = FastAPI(title="Spotify → slskd bridge (OAuth-ready)")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, playlist: str | None = None):
    tracks = []
    error = None
    logged_in = bool(auth.get_user_access_token())
    if playlist:
        logger.info("[web] Received playlist=%s", playlist)
        try:
            tracks = await get_playlist_tracks(playlist, prefer_user=True)
        except Exception as ex:
            error = str(ex)
            logger.exception("[web] Error while getting playlist tracks")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tracks": tracks,
            "playlist": playlist or "",
            "error": error,
            "logged_in": logged_in,
        },
    )

@app.get("/login")
def login(request: Request):
    url = auth.build_authorize_url(request)
    return RedirectResponse(url)

@app.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse(f"<h3>Eroare login Spotify</h3><pre>{error}</pre>", status_code=400)
    if not code or not state or not auth.validate_state(state):
        return HTMLResponse("<h3>Callback invalid (code/state)</h3>", status_code=400)
    try:
        data = auth._exchange_code_for_token(code)
        auth.set_user_token(data)
    except Exception as ex:
        logger.exception("[oauth] Callback token exchange failed")
        return HTMLResponse(f"<h3>Token exchange failed</h3><pre>{ex}</pre>", status_code=500)
    return RedirectResponse("/")

@app.post("/slskd/search")
async def slskd_search(q: str = Form(...)):
    try:
        data = await search_in_slskd(q)
        return JSONResponse({"ok": True, "q": q, "slskd": data})
    except Exception as ex:
        raise HTTPException(status_code=502, detail=f"slskd error: {ex}")

@app.get("/health")
def health():
    return {"status": "ok"}