# app/slskd.py
import os, httpx, logging
logger = logging.getLogger("uvicorn")

SLSKD_BASE = os.getenv("SLSKD_BASE", "http://192.168.1.7:5030")
_raw = os.getenv("SLSKD_API_KEY", "")
SLSKD_API_KEY = _raw.split(";")[-1].strip() if _raw else ""  # ← extrage doar tokenul final

async def search_in_slskd(query: str) -> dict:
    url = f"{SLSKD_BASE}/api/v0/searches"
    payload = {"searchText": query, "options": {"timeout": 15000}}
    headers = {"X-API-Key": SLSKD_API_KEY, "Content-Type": "application/json"}

    logger.info("[slskd] POST %s key_present=%s query=%s", url, bool(SLSKD_API_KEY), query)

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()