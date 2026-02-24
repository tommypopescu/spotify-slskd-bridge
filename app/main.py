# app/main.py
import logging
import csv, io

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .spotify import get_playlist_tracks
from .slskd import search_in_slskd
# Dacă ai activat OAuth Code Flow anterior, se poate folosi acest import:
# from . import auth

logger = logging.getLogger("uvicorn")

app = FastAPI(title="Spotify → slskd bridge")

# Static + templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ---- Pagina principală (încărcare playlist din URL/ID/URI) ----
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, playlist: str | None = None):
    tracks = []
    error = None
    # Dacă ai OAuth user token, poți calcula logged_in = bool(auth.get_user_access_token())
    logged_in = False

    if playlist:
        logger.info("[web] Received playlist=%s", playlist)
        try:
            # prefer_user=True dacă ai OAuth; altfel rămâne fallback pe Client Credentials
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

# ---- Upload CSV Exportify (nou) ----
@app.post("/upload", response_class=HTMLResponse)
async def upload_playlist(request: Request, playlist_file: UploadFile = File(...)):
    """
    Primește un CSV exportat din Exportify și extrage titlu + artiști,
    construind query-ul 'Artist - Titlu' pentru butonul 'Caută în slskd'.
    """
    error = None
    tracks = []
    try:
        raw = await playlist_file.read()
        text = raw.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        # Capete uzuale în Exportify:
        # "Track Name", "Artist Name(s)", "Track URI", "Album Name", "Genres", etc.
        # (vezi README Exportify pentru lista completă de câmpuri) [1](https://stackoverflow.com/questions/78440381/spotipy-accessing-users-playlist-access-to-localhost-was-denied-http-error-4)
        for row in reader:
            title = (row.get("Track Name") or "").strip()
            artists_raw = (row.get("Artist Name(s)") or "").strip()
            if not title and not artists_raw:
                continue
            # Exportify separă mai mulți artiști cu ';' → afisăm cu ', '
            artists = ", ".join([a.strip() for a in artists_raw.split(";") if a.strip()]) if artists_raw else ""
            query = f"{artists} - {title}".strip(" -")
            tracks.append({
                "title": title,
                "artists": artists,
                "query": query
            })
        logger.info("[upload] Parsed %d tracks from %s", len(tracks), playlist_file.filename)
    except Exception as ex:
        error = f"Eroare la parsarea CSV: {ex}"
        logger.exception("[upload] Failed to parse CSV")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tracks": tracks,
            "playlist": f"Fișier: {playlist_file.filename}",
            "error": error,
            "logged_in": False,  # setează după caz dacă ai OAuth
        },
    )

# ---- slskd: trimite căutarea (existent) ----
@app.post("/slskd/search")
async def slskd_search(q: str = Form(...)):
    try:
        data = await search_in_slskd(q)
        return JSONResponse({"ok": True, "q": q, "slskd": data})
    except Exception as ex:
        raise HTTPException(status_code=502, detail=f"slskd error: {ex}")

# ---- Healthcheck (existent) ----
@app.get("/health")
def health():
    return {"status": "ok"}