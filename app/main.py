from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .spotify import get_playlist_tracks
from .slskd import search_in_slskd
app = FastAPI(title='Spotify → slskd bridge')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates = Jinja2Templates(directory='app/templates')
@app.get('/', response_class=HTMLResponse)
async def index(request: Request, playlist: str | None = None):
    tracks = []
    error = None
    if playlist:
        try:
            tracks = await get_playlist_tracks(playlist)
        except Exception as ex:
            error = str(ex)
    return templates.TemplateResponse('index.html', {'request': request,'tracks': tracks,'playlist': playlist or '', 'error': error})
@app.post('/slskd/search')
async def slskd_search(q: str = Form(...)):
    try:
        data = await search_in_slskd(q)
        return JSONResponse({'ok': True, 'q': q, 'slskd': data})
    except Exception as ex:
        raise HTTPException(status_code=502, detail=f'slskd error: {ex}')