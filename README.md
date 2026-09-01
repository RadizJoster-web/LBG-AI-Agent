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

### UI review (disarankan)

```bash
python app.py
```

Membuka `http://127.0.0.1:5000/` di browser:

1. Klik **Pindai Google Drive** → semua file yang belum diproses dimuat.
2. Game yang di-upload ke Drive **hari ini** otomatis tercentang; game yang **sudah ada di Sanity** ditandai `SUDAH ADA` dan tidak bisa dipilih.
3. Centang manual bila perlu, lalu **Up Terpilih** atau **Up Semua yang Baru (hari ini)**.
4. Progress bar + log langsung ditampilkan selama upload.

Tidak ada apa pun yang dikirim ke Sanity sampai kamu klik tombol upload.

### CLI (headless / cron)

```bash
python main.py            # scan + tampilkan tabel, TIDAK meng-upload
python main.py --today    # upload game yang di-upload ke Drive hari ini (konfirmasi dulu)
python main.py --all      # upload semua kandidat baru/disc (konfirmasi dulu)
python main.py --today --yes   # tanpa prompt konfirmasi
```

Set `DRY_RUN=true` di `.env` untuk menjalankan tanpa menulis apa pun ke Sanity (mutasi hanya di-log).

## Struktur

| Path | Peran |
|------|-------|
| `app.py` / `web/` | UI review lokal (Flask) — form checkbox + progress bar |
| `config.py` | Muat `.env`, ekspos konstanta bertipe |
| `logging_config.py` | RotatingFileHandler + stdout |
| `clients/drive_client.py` | Google Drive API v3 (OAuth, scan folder/file, paginasi, `createdTime`) |
| `clients/gemini_client.py` | Gemini (`gemini-3.5-flash-lite`, JSON mode, rate-limit, prompt Bahasa Indonesia) |
| `clients/sanity_client.py` | GROQ lookup + mutasi + indeks game lama (dedup judul+platform) |
| `core/scanner.py` | Drive scan → daftar `GameCandidate` (murah, tanpa Gemini) |
| `core/ingest.py` | Proses kandidat terpilih → Sanity, dengan callback progress |
| `core/title_cleaner.py` | Nama file → judul bersih + tag region + nomor disc |
| `core/genre_resolver.py` | Genre Gemini → ref Sanity (buat baru bila belum ada) |
| `core/data_mapper.py` | Rakit dokumen `game` sesuai Aturan Kritis Sanity |
| `core/schema_validator.py` | Validasi output Gemini (lenient) + payload Sanity (strict) |
| `core/file_size_formatter.py` | Bytes → `"XXX MB"` / `"X.XX GB"` |
| `core/state_manager.py` | Dedup via `state/processed_files.json` (atomic write) |
| `main.py` | Entry point CLI headless |

## Keputusan konfigurasi (dikonfirmasi user)

- **URL Drive:** direct download — `https://drive.google.com/uc?id={id}&export=download`
- **Multi-disc:** satu dokumen; disc pertama `createIfNotExists`, disc berikutnya `patch` append ke `downloadLinks`
- **Genre di luar whitelist:** dibuat otomatis di Sanity (`CREATE_MISSING_GENRES=true`)
- **Model Gemini:** `gemini-3.5-flash-lite`
- **`language`:** selalu `"Inggris"` (tidak diminta ke Gemini — CLAUDE.md workflow #3)
- **`fullDescription`:** selalu Bahasa Indonesia meski game-nya berbahasa Inggris
- **UI review:** halaman web lokal (Flask, `127.0.0.1` saja) — mencegah upload massal tak sengaja
- **Deteksi duplikat:** cocokkan `_id` slug **dan** (judul + platform) — menangkap game lama buatan Studio yang ber-`_id` UUID

## Catatan skema Sanity (dari data live, bukan architecture.md)

- `genre` & `platform` → field `name` + `slug.current`
- `region` → field `code` (`USA`/`EUR`/`UK`/`JPN`) + `name`, **tanpa `slug`**; dicocokkan lewat alias di `sanity_client._REGION_ALIAS_GROUPS`
- `scripts/inspect_sanity.py` → dump ulang bentuk dokumen kapan saja

## Test

```bash
python tests/test_core.py
```
