# LBG — AI Ingestion Agent

Pipeline otomatis: **Google Drive → Gemini API → Sanity CMS**.
Mendeteksi file game baru (PS2, PSP, dll) di Google Drive, memperkaya metadata via Gemini, lalu mengunggahnya sebagai dokumen `game` terstruktur ke Sanity.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env            # lalu isi nilainya
```

Letakkan Google OAuth client secret di `credentials/client_secret.json`.
Run pertama akan membuka browser untuk consent dan menyimpan `credentials/token.json`.

## Menjalankan

```bash
python main.py
```

Set `DRY_RUN=true` di `.env` untuk menjalankan tanpa menulis apa pun ke Sanity (mutasi hanya di-log).

## Struktur

| Path | Peran |
|------|-------|
| `config.py` | Muat `.env`, ekspos konstanta bertipe |
| `logging_config.py` | RotatingFileHandler + stdout |
| `clients/drive_client.py` | Google Drive API v3 (OAuth, scan folder/file, paginasi) |
| `clients/gemini_client.py` | Gemini (`gemini-3.5-flash-lite`, JSON mode, rate-limit) |
| `clients/sanity_client.py` | GROQ lookup + mutasi (`createIfNotExists`, patch, buat genre) |
| `core/title_cleaner.py` | Nama file → judul bersih + tag region + nomor disc |
| `core/genre_resolver.py` | Genre Gemini → ref Sanity (buat baru bila belum ada) |
| `core/data_mapper.py` | Rakit dokumen `game` sesuai Aturan Kritis Sanity |
| `core/schema_validator.py` | Validasi output Gemini (lenient) + payload Sanity (strict) |
| `core/file_size_formatter.py` | Bytes → `"XXX MB"` / `"X.XX GB"` |
| `core/state_manager.py` | Dedup via `state/processed_files.json` (atomic write) |
| `main.py` | Orkestrasi seluruh pipeline |

## Keputusan konfigurasi (dikonfirmasi user)

- **URL Drive:** direct download — `https://drive.google.com/uc?id={id}&export=download`
- **Multi-disc:** satu dokumen; disc pertama `createIfNotExists`, disc berikutnya `patch` append ke `downloadLinks`
- **Genre di luar whitelist:** dibuat otomatis di Sanity (`CREATE_MISSING_GENRES=true`)
- **Model Gemini:** `gemini-3.5-flash-lite`

## Test

```bash
python tests/test_core.py
```
