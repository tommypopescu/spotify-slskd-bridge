import time, base64, os
from typing import List, Dict
import httpx
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_API_BASE = 'https://api.spotify.com/v1'
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')
_token_cache={'access_token':None,'expires_at':0}
async def _get_app_token()->str:
    now=int(time.time())
    if _token_cache['access_token'] and _token_cache['expires_at']-30>now:
        return _token_cache['access_token']
    auth=base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=15) as c:
        r=await c.post(SPOTIFY_TOKEN_URL,data={'grant_type':'client_credentials'},headers={'Authorization':f'Basic {auth}','Content-Type':'application/x-www-form-urlencoded'})
        r.raise_for_status();d=r.json()
        _token_cache.update(access_token=d['access_token'],expires_at=now+int(d['expires_in']))
        return d['access_token']
async def _auth_headers():return {'Authorization':f"Bearer {await _get_app_token()}"}
def _extract_playlist_id(raw:str)->str:
    raw=raw.strip()
    if raw.startswith('spotify:playlist:'):return raw.split(':')[-1]
    if 'open.spotify.com/playlist/' in raw: return raw.split('playlist/')[1].split('?')[0].split('/')[0]
    return raw
async def get_playlist_tracks(raw_playlist:str)->List[Dict]:
    pid=_extract_playlist_id(raw_playlist)
    url=f"{SPOTIFY_API_BASE}/playlists/{pid}/tracks";items=[];params={'limit':100,'additional_types':'track'}
    async with httpx.AsyncClient(timeout=20) as c:
        while True:
            r=await c.get(url,headers=await _auth_headers(),params=params);r.raise_for_status();data=r.json()
            for it in data.get('items',[]):
                t=it.get('track') or{}
                if not t or t.get('type')!='track':continue
                name=t.get('name') or'';artists=', '.join([a.get('name','') for a in t.get('artists',[]) if a])
                items.append({'title':name,'artists':artists,'query':f"{artists} - {name}".strip()})
            if not data.get('next'):break
            url=data['next'];params={}
    return items