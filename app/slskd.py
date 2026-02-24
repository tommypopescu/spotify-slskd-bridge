# app/slskd.py
import os
import httpx
import logging

logger = logging.getLogger("uvicorn")

SLSKD_BASE = os.getenv("SLSKD_BASE", "http://192.168.1.7:5030")

_raw_key = os.getenv("SLSKD_API_KEY", "") or ""
# Acceptă fie token brut, fie format extins: role=...;cidr=...;TOKEN
SLSKD_API_KEY = _raw_key.split(";")[-1].strip() if _raw_key else ""

async def search_in_slskd(query: str) -> dict:
    url = f"{SLSKD_BASE}/api/v0/searches"
    payload = {"searchText": query, "options": {"timeout": 15000}}
    headers = {
        "X-API-Key": SLSKD_API_KEY,
        "Content-Type": "application/json"
    }

    tail = SLSKD_API_KEY[-4:] if SLSKD_API_KEY else "NONE"
    logger.info("[slskd] POST %s key_present=%s endswith=%s query=%s",
                url, bool(SLSKD_API_KEY), tail, query)

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()