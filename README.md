# Football Analytics Hub

Platform analisis statistik sepak bola dan simulator kombinasi pertandingan (parlay) untuk tujuan **edukasi dan analisis data**.

> **Disclaimer:** Prediksi berbasis statistik dan tidak menjamin hasil. Aplikasi ini bukan ajakan untuk berjudi. Perjudian dilarang di Indonesia.

---

## Arsitektur & Teknologi
- **Backend & Model Prediksi**: FastAPI (Python 3.12), SQLAlchemy, Alembic (migrasi rollbackable), APScheduler (worker otomatis), Pydantic v2, SciPy/NumPy.
- **Model Matematis (`dixon-coles-elo-v2-calibrated`)**: Dixon-Coles Bivariate Poisson + Rating Elo + Kalibrasi *Temperature Scaling* + Fitur Kontekstual (kekuatan jadwal / SoS, hari istirahat, dampak cedera, bobot form terbaru).
- **Database & Cache**: PostgreSQL 16 + Redis 7 (via Docker Compose), dengan fallback SQLite & in-memory cache untuk pengembangan lokal.
- **Frontend**: Next.js 14 (App Router, TypeScript, Tailwind CSS, Zod, Recharts) + UI HTML langsung pada `GET /` dengan Light/Dark mode tokens (`IBM Plex Sans`, `tabular-nums`).

---

## 1. Setup & Menjalankan Aplikasi

### Opsi A: Docker Compose (Direkomendasikan untuk Produksi)
1. Salin `.env.example` menjadi `.env`:
   ```bash
   cp .env.example .env
   ```
2. Isi API key pada `.env` bila memakai `football-data`, `api-football`, atau `footystats` (atau biarkan `DATA_PROVIDER=fotmob` / `mock`).
3. Jalankan seluruh layanan (PostgreSQL, Redis, Backend, Worker, Frontend):
   ```bash
   docker compose up --build
   ```
4. Akses:
   - Frontend Next.js: `http://localhost:3000`
   - Backend API & UI HTML: `http://localhost:8000` (Swagger Docs: `http://localhost:8000/docs`)

### Opsi B: Menjalankan Lokal di Windows (Tanpa Docker)
1. Masuk ke folder `backend` dan aktifkan `.venv`:
   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m scripts.seed
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   *(Atau klik dua kali `jalankan_football_hub.bat` di folder root).*
2. Jalankan worker scheduler di terminal terpisah (opsional):
   ```powershell
   .\.venv\Scripts\python.exe -m app.worker
   ```

---

## 2. Konfigurasi Environment (`.env`)

Lihat `.env.example`:
- `DATA_PROVIDER`: `mock` | `football-data` | `api-football` | `fotmob` | `footystats`
- `FOOTBALL_DATA_API_KEY`: API key dari `football-data.org`
- `API_FOOTBALL_KEY`: API key dari `api-football.com`
- `FOOTYSTATS_API_KEY`: API key dari `footystats.org`
- `DATABASE_URL`: String koneksi PostgreSQL atau SQLite
- `REDIS_URL`: String koneksi Redis
- `JWT_SECRET`, `JWT_ALGORITHM`, `GOOGLE_CLIENT_ID`: Konfigurasi autentikasi opsional

---

## 3. Jadwal Job Otomatis (`backend/app/worker.py`)

Worker APScheduler berjalan terpisah (`fah_worker` di Docker Compose) dengan jalur berikut:
1. **Sinkronisasi Harian (`02:00 WIB` / `Asia/Jakarta`)**: Mengambil jadwal, klasemen, statistik tim, laporan cedera, dan hasil kemarin, lalu menghitung ulang prediksi.
2. **Polling Live (`interval 45 detik`)**: Hanya memanggil API eksternal bila di database terdapat laga berstatus `LIVE` atau dalam jendela `±15–120 menit` dari *kickoff* agar kuota API tetap hemat.
3. **Resiliensi & Observability**: Dilengkapi *token-bucket rate limiter*, `ETag`/`If-Modified-Since`, *retry exponential backoff + jitter*, *circuit breaker*, pencatatan di tabel `sync_log`, dan penanda `"Data mungkin tertunda"` pada `/health` bila API eksternal gagal.

---

## 4. Cara Menambah Liga Baru

1. Tambahkan kode liga ke `DEFAULT_LEAGUES` pada `backend/app/services/ingestion.py`.
2. Tambahkan pemetaan nama kanonik di `LEAGUE_CANONICAL` pada `backend/app/services/normalizer.py`.
3. Tambahkan ID liga sesuai provider:
   - `FOTMOB_LEAGUE_IDS` di `backend/app/adapters/fotmob.py`
   - `API_FOOTBALL_LEAGUE_IDS` di `backend/app/adapters/api_football.py`
4. Tambahkan opsi filter `<option>` pada dropdown liga di `backend/app/static/index.html`.
5. Jalankan `python -m scripts.seed` atau `POST /ingest/sync`.

---

## 5. Cara Menjalankan Test & Backtest

Dari folder `backend/`:
- **Unit & Resilience Tests**:
  ```bash
  python -m pytest -v
  ```
- **Walk-Forward Backtesting (bebas data leakage)**:
  ```bash
  python -m scripts.backtest
  ```
  Laporan mencakup **Total Laga Dievaluasi**, **Akurasi 1X2 (%)**, **Brier Score**, **Log Loss**, dan **Kalibrasi** per *probability bin*.
- **Migrasi Database (Alembic)**:
  ```bash
  python -m alembic upgrade head
  python -m alembic downgrade -1
  ```
