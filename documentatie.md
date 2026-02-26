# Documentație proiect: Spotify → slskd Bridge (CSV + Exportify)

**Versiune:** 2026‑02‑24  
**Scop:** Încărcare playlisturi din CSV exportat cu Exportify și trimiterea căutărilor către **slskd** (Soulseek Daemon) – fără a folosi API-ul Spotify.

---

## 1) Arhitectură & flux

```
Exportify → CSV → /upload (FastAPI) → Parse CSV → UI listă piese
   └─ [Buton „Caută”] → POST /slskd/search → slskd /api/v0/searches
   └─ [Caută selectate (10s)] → trimite în serie, 10s între cereri
```

- **Fără API Spotify**: citim doar fișiere CSV (Exportify) încărcate din UI.
- **slskd**: se apelează `POST {SLSKD_BASE}/api/v0/searches` cu header `X-API-Key` și body `{"searchText": "Artist - Titlu"}`.
- **UI**: filtru live, checkbox per piesă, buton „Caută” lipit de melodie, „Caută selectate (10s)”, descarcă CSV, persistentă selecții (localStorage).

---

## 2) Structură proiect

```
app/
 ├─ main.py              # FastAPI: /, /upload, /slskd/search, /health
 ├─ slskd.py             # apel la slskd: POST /api/v0/searches; decupare token din cheie extinsă
 ├─ templates/
 │   ├─ base.html        # layout + includeri CSS/JS
 │   └─ index.html       # UI final (upload, filtrare, checkbox, batch 10s, download CSV)
 └─ static/
     └─ styles.css       # stiluri (opțional)

.env.example             # exemplu pentru variabile mediu
requirements.txt         # fastapi, uvicorn, httpx, jinja2 etc.
docker-compose.yml       # serviciu web + env_file
README.md / documentatie.md
```

---

## 3) Configurare `.env`

Creează `.env` în rădăcina proiectului (lângă `docker-compose.yml`):

```dotenv
SLSKD_BASE=http://192.168.1.7:5030
# Acceptă fie token brut (TOKEN), fie cheie extinsă (role=…;cidr=…;TOKEN). Codul extrage automat TOKEN-ul.
SLSKD_API_KEY=OXMRJ43VWQU71F9L68TZYHNP
```

> **CIDR & Docker:** Dacă în slskd cheia include `cidr=…`, adaugă și **subnetul Docker** al aplicației web (ex. `172.22.0.0/16`). Altfel slskd poate răspunde **401 Unauthorized** chiar cu token corect, deoarece IP-ul sursă (al containerului) nu este permis.

---

## 4) Build & Run

```bash
docker compose down
docker compose up -d --build
```

Accesează UI: `http://<host>:<port>` (ex. `http://omv.local:8087` sau `http://192.168.1.7:8080`).

> După orice modificare în `templates/`, folosește `--build` și **hard reload** în browser (`Ctrl+F5`).

---

## 5) Utilizare UI (cap‑coadă)

1. **Exportă** playlistul din **Exportify** (butonul din UI: „Deschide Exportify în tab nou”).
2. **Încarcă** CSV în formularul „CSV din Exportify” (buton **„Încarcă playlist”**).
3. **Lucrează cu lista**:
   - **Filtru live** (caută în titlu/artiști/query – instant, fără reload).
   - **Checkbox** per piesă; **Selectează/Deselectează toate**.
   - **„Caută”** pe fiecare rând (lipit de melodie) – după succes: ✔️, checkbox devine `disabled`.
   - **„Caută selectate (10s)”** – trimite în serie DOAR piesele bifate (pauză 10s între cereri).
   - **„Descarcă CSV”** – exportă lista afișată (respectă filtrul activ) în `playlist_curent.csv`.
4. **Persistență selecții**:
   - Bifările sunt salvate în `localStorage` (rămân după refresh; se asociază pe textul `query`).

---

## 6) Endpoint-uri backend

### `GET /`
Randare UI inițială.

### `POST /upload`
- Primește `multipart/form-data` cu câmpul `playlist_file` (CSV Exportify).
- Parsează CSV cu `csv.DictReader`.
- Produce listă de dict: `{title, artists, query}` (unde `query = "Artists - Title"`).

Condiții:
- Formularul din `index.html` trebuie să fie **HTML valid**:
  ```html
  /upload
    <input type="file" name="playlist_file" accept=".csv,text/csv" required />
    <button type="submit">Încarcă playlist</button>
  </form>
  ```

### `POST /slskd/search`
- Primește `application/x-www-form-urlencoded` cu `q = <query>`.
- Apelează `search_in_slskd(q)` → `POST {SLSKD_BASE}/api/v0/searches`.
- Returnează `{ok: true, q, slskd: {...}}` la succes; la erori răspunde `502` cu `detail`.

### `GET /health`
- `{"status":"ok"}` – sanity check.

---

## 7) Implementare apel slskd (`slskd.py`)

- Citește `SLSKD_BASE` și `SLSKD_API_KEY` din env.
- Dacă cheia e extinsă (`role=...;cidr=...;TOKEN`), **extrage doar TOKEN-ul**:
  ```py
  raw = os.getenv("SLSKD_API_KEY", "")
  token = raw.split(";")[-1].strip()
  ```
- Trimite `POST` cu header `X-API-Key: <token>` și body JSON:
  ```json
  {"searchText": "Artist - Titlu", "options": {"timeout": 15000}}
  ```
- În log se notează doar ultimele 4 caractere din token (pentru debug, fără a expune cheia completă).

---

## 8) Detalii UI (`templates/index.html`)

- **Fără iframe** pentru Exportify (doar link în tab nou) – multe site-uri blochează embedding (X-Frame-Options / CSP).
- **Buton „Caută”**:
  - Apelă `/slskd/search` via `fetch` (POST, urlencoded).
  - La succes: buton ascuns, ✔️ afișat, checkbox marcat & `disabled`.
- **Batch „Caută selectate (10s)”**:
  - Găsește `.sel:checked:not(:disabled)`.
  - Trimite pe rând, cu `await new Promise(r => setTimeout(r, 10000))` între cereri.
  - La succes: idem ca la „Caută”.
- **Filtru live**: ascunde/afișează `<li>` în funcție de text.
- **Download CSV**: citește DOM-ul curent (`.meta`) și descarcă fișier local.
- **Persistență**: `localStorage['slskd-selected']` conține array de `query` selectate.

---

## 9) Teste rapide

### Upload funcțional
- În DevTools → **Network** trebuie să apară `POST /upload` (200 OK) cu `multipart/form-data`.
- În log vedeți: `[upload] Parsed <N> tracks from <fisier>.csv`.

### slskd conectivitate + cheie
- Din containerul web:
  ```bash
  docker exec -i spotify-slskd-bridge python - <<'PY'
  import os, httpx
  base=os.getenv('SLSKD_BASE'); raw=os.getenv('SLSKD_API_KEY') or ''
  key=raw.split(';')[-1].strip()
  r=httpx.post(f"{base}/api/v0/searches",
               headers={'X-API-Key':key,'Content-Type':'application/json'},
               json={'searchText':'metallica','options':{'timeout':15000}}, timeout=20)
  print('Status:', r.status_code); print('Body:', r.text[:200])
  PY
  ```
- **200/201**: OK.  **401**: verifică **CIDR** în slskd (include și subnetul Docker).

---

## 10) Erori frecvente & remedieri

1. **Butonul „Încarcă playlist” nu face nimic**
   - În `index.html` trebuie să fie taguri HTML reale, **nu entități** (`<form>`, nu `&lt;form`), și formular cu `action="/upload" method="POST" enctype="multipart/form-data"`.
   - Fă **hard reload** și rebuild cu `--build`.

2. **401 la slskd** cu token corect
   - Cheia din slskd are `cidr` care nu include subnetul Docker (ex. `172.22.0.0/16`). Adaugă-l.

3. **Nu se văd modificările**
   - `docker compose up -d --build` + **Ctrl+F5**.

---

## 11) Extensii propuse

- Interval batch configurabil (UI slider: 5–30s).
- „Selectează doar filtrate”.
- Sortare / grupare (după artist, nume; alfabetică).
- Polling pentru starea căutărilor în slskd (`id`, `state`).
- Temă light/dark.

---

## 12) Licență

Proiect intern / demo. Adaptează după nevoi.
