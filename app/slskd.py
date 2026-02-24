import os, httpx
SLSKD_BASE=os.getenv('SLSKD_BASE','http://host.docker.internal:5030')
SLSKD_API_KEY=os.getenv('SLSKD_API_KEY','')
async def search_in_slskd(query:str)->dict:
    url=f"{SLSKD_BASE}/api/v0/searches";payload={'searchText':query,'options':{'timeout':15000}}
    headers={'X-API-Key':SLSKD_API_KEY,'Content-Type':'application/json'}
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post(url,json=payload,headers=headers);r.raise_for_status();return r.json()