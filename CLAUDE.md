# Project: LastBossGames (LBG) - AI Ingestion Agent

## 🎯 Tujuan Utama

Aplikasi ini adalah _pipeline_ otomatisasi berbasis Python untuk _website_ LastBossGames. Tugas utamanya mendeteksi _file_ game baru (PS2, PSP, dll) di Google Drive, mengekstrak metadatanya secara otomatis menggunakan Gemini API, dan mengunggahnya sebagai dokumen terstruktur ke Sanity CMS. Tujuannya memangkas waktu _data entry_ manual 10-15 menit per game.

## 🛠 Tech Stack

- **Bahasa:** Python murni. _Pengecualian (disetujui user 2026-09-01):_ **Flask** dipakai HANYA untuk UI review lokal (`app.py`, bind ke `127.0.0.1`) tempat user mencentang game mana yang di-up. Pipeline inti tetap tanpa _framework_.
- **Ekstraksi:** Google Drive API v3 (membaca folder, nama _file_, ukuran, `createdTime`)
- **AI Agent:** Gemini API (`gemini-3.5-flash-lite` dengan `response_mime_type: "application/json"`)
- **Database:** Sanity CMS API (via `requests`, Project ID: `liftuy21`, Dataset: `production`)

## ⚠️ Aturan Kritis Sanity CMS (JANGAN DILANGGAR)

Setiap mutasi `createIfNotExists` ke Sanity harus mematuhi skema ini secara mutlak:

1. **`fullDescription`**: WAJIB berformat _array of Portable Text blocks_, BUKAN _string_ mentah.
   _(Contoh: `[{"_type": "block", "children": [{"_type": "span", "text": "Output Gemini di sini..."}]}]`)_
2. **`platform`**: _Single reference object_ (contoh: `{"_type": "reference", "_ref": "..."}`). Platform didapat dari nama folder Drive.
3. **`language`**: _Single string_. Selalu `"Inggris"` (tidak diminta ke Gemini) — lihat `config.DEFAULT_LANGUAGE`.
4. **`genre`**: Nama _key_ wajib `genre` (bukan `genres`). Berformat _array of reference objects_ dengan `_key`. ID Referensi ditarik dinamis dari Sanity.
5. **`region`**: _Single reference object_. Region diekstrak dari _tag_ pada nama _file_ (contoh: `(USA)`).
6. **`fileSize`**: Harus diisi di DUA tempat: di _root level_ dokumen dan di dalam tiap _item_ objek pada _array_ `downloadLinks`.
7. **Gambar**: Biarkan `thumbnail` bernilai `null` dan `screenshots` sebagai _array_ kosong `[]`. Gambar ditangani secara manual.
8. **`popularityScore`**: Selalu _hardcode_ ke nilai `0`.

## 🧠 Alur Kerja Utama (Workflow)

1. **Drive Scan**: Pindai folder platform (PS2, PSP, dll), dapatkan _file_ baru (cek `processed_files.json` untuk _deduplication_).
2. **Clean & Extract**: Bersihkan judul _file_ dari ekstensi (`.zip`) dan ekstrak atribut seperti part number / disc / tag region jika ada.
3. **Dedup vs Sanity**: Cek tiap kandidat terhadap game yang SUDAH ada di Sanity — cocokkan `_id` slug DAN (judul + platform), karena game lama buatan Studio ber-`_id` UUID acak. Yang sudah ada tidak di-up ulang.
4. **Review (UI lokal)**: Tampilkan daftar kandidat di `app.py`; game yang di-upload ke Drive hari ini otomatis tercentang. User memilih lalu klik "Up Terpilih" / "Up Semua yang Baru". Tanpa klik, tidak ada mutasi.
5. **Enrichment (Gemini)**: Kirim judul bersih ke Gemini untuk _developer_, _publisher_, _releaseYear_, dan _genre_ (whitelist genre dari Sanity; jika tidak ada, buat genre baru). `fullDescription` WAJIB Bahasa Indonesia. `language` TIDAK diminta ke Gemini — selalu `"Inggris"` (`config.DEFAULT_LANGUAGE`).
6. **Reference Match**: Petakan teks output AI ke dalam referensi ID Sanity yang valid.
7. **Mutation**: `createIfNotExists` untuk game baru; multi-disc → `patch` append ke `downloadLinks` dokumen yang sama.

## 🤖 Perintah Khusus untuk Claude Code

- Baca dokumen arsitektur (jika disediakan) sebelum memulai penulisan kode.
- Tulis kode secara modular (pisahkan _client_ Drive, Gemini, dan Sanity di _file_ berbeda).
- JANGAN pernah membuat asumsi terkait _mapping_ skema; rujuk selalu ke bagian "Aturan Kritis Sanity CMS" di atas.
- Tanyakan format URL Drive (_direct_ atau _viewer_) dan penanganan multi-disc kepada _user_ sebelum menyusun modul _mapper_.
