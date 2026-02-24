# app/main.py
import logging
import csv, io

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .slskd import search_in_slskd

logger = logging.getLogger("uvicorn")

app = FastAPI(title="Spotify → slskd bridge")

# static & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ------------------------------
# Pagina principală
# ------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tracks": [],
            "playlist": "",
            "error": None,
            "logged_in": False
        },
    )


# ------------------------------
# Upload CSV Exportify
# ------------------------------
@app.post("/upload", response_class=HTMLResponse)
async def upload_playlist(request: Request, playlist_file: UploadFile = File(...)):
    error = None
    tracks = []
    try:
        raw = await playlist_file.read()
        text = raw.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        for row in reader:
            title = (row.get("Track Name") or "").strip()
            artists_raw = (row.get("Artist Name(s)") or "").strip()

            if not title and not artists_raw:
                continue

            # Exportify poate separa artiștii cu ";"
            artists = ", ".join([a.strip() for a in artists_raw.split(";") if a.strip()])

            query = f"{artists} - {title}".strip(" -")

            tracks.append({
                "title": title,
                "artists": artists,
                "query": query
            })

        logger.info("[upload] Parsed %d tracks from %s", len(tracks), playlist_file.filename)

    except Exception as ex:
        error = f"Eroare la parsarea CSV: {ex}"
        logger.exception("[upload] Failed parsing CSV")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tracks": tracks,
            "playlist": f"Fișier: {playlist_file.filename}",
            "error": error,
            "logged_in": False
        },
    )


# ------------------------------
# Căutare slskd
# ------------------------------
@app.post("/slskd/search")
async def slskd_search(q: str = Form(...)):
    try:
        data = await search_in_slskd(q)
        return JSONResponse({"ok": True, "q": q, "slskd": data})
    except Exception as ex:
        raise HTTPException(status_code=502, detail=f"slskd error: {ex}")


# ------------------------------
# Health check
# ------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}