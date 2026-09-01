# Project: LastBossGames (LBG) - AI Ingestion Agent

## 🎯 Tujuan Utama

Aplikasi ini adalah _pipeline_ otomatisasi berbasis Python untuk _website_ LastBossGames. Tugas utamanya mendeteksi _file_ game baru (PS2, PSP, dll) di Google Drive, mengekstrak metadatanya secara otomatis menggunakan Gemini API, dan mengunggahnya sebagai dokumen terstruktur ke Sanity CMS. Tujuannya memangkas waktu _data entry_ manual 10-15 menit per game.

## 🛠 Tech Stack

- **Bahasa:** Python murni (tanpa _framework_ web)
- **Ekstraksi:** Google Drive API v3 (membaca folder, nama _file_, ukuran)
- **AI Agent:** Gemini API (`gemini-3.5-flash-lite` dengan `response_mime_type: "application/json"`)
- **Database:** Sanity CMS API (via `requests`, Project ID: `liftuy21`, Dataset: `production`)

## ⚠️ Aturan Kritis Sanity CMS (JANGAN DILANGGAR)

Setiap mutasi `createIfNotExists` ke Sanity harus mematuhi skema ini secara mutlak:

1. **`fullDescription`**: WAJIB berformat _array of Portable Text blocks_, BUKAN _string_ mentah.
   _(Contoh: `[{"_type": "block", "children": [{"_type": "span", "text": "Output Gemini di sini..."}]}]`)_
2. **`platform`**: _Single reference object_ (contoh: `{"_type": "reference", "_ref": "..."}`). Platform didapat dari nama folder Drive.
3. **`language`**: _Single string_ (contoh: `"English"`).
4. **`genre`**: Nama _key_ wajib `genre` (bukan `genres`). Berformat _array of reference objects_ dengan `_key`. ID Referensi ditarik dinamis dari Sanity.
5. **`region`**: _Single reference object_. Region diekstrak dari _tag_ pada nama _file_ (contoh: `(USA)`).
6. **`fileSize`**: Harus diisi di DUA tempat: di _root level_ dokumen dan di dalam tiap _item_ objek pada _array_ `downloadLinks`.
7. **Gambar**: Biarkan `thumbnail` bernilai `null` dan `screenshots` sebagai _array_ kosong `[]`. Gambar ditangani secara manual.
8. **`popularityScore`**: Selalu _hardcode_ ke nilai `0`.

## 🧠 Alur Kerja Utama (Workflow)

1. **Drive Scan**: Pindai folder platform (PS2, PSP, dll) ditanggal sekarang, dapatkan _file_ baru (cek `processed_files.json` untuk _deduplication_).
2. **Clean & Extract**: Bersihkan judul _file_ dari ekstensi (`.zip`) dan ekstrak atribut seperti part number jika ada.
3. **Enrichment (Gemini)**: Kirim judul bersih ke Gemini API untuk mendapatkan data _developer_, _publisher_, _releaseYear_, _language_ (tidak perlu dikirim langsung berikan defaault 'Inggris'), dan _genre_ (berdasarkan _whitelist_ genre dari Sanity jika tidak ada bisa buat baru).
4. **Reference Match**: Petakan teks output AI ke dalam referensi ID Sanity yang valid.
5. **Mutation**: Rakit _payload_ JSON final dan kirim ke Sanity _endpoint_.

## 🤖 Perintah Khusus untuk Claude Code

- Baca dokumen arsitektur (jika disediakan) sebelum memulai penulisan kode.
- Tulis kode secara modular (pisahkan _client_ Drive, Gemini, dan Sanity di _file_ berbeda).
- JANGAN pernah membuat asumsi terkait _mapping_ skema; rujuk selalu ke bagian "Aturan Kritis Sanity CMS" di atas.
- Tanyakan format URL Drive (_direct_ atau _viewer_) dan penanganan multi-disc kepada _user_ sebelum menyusun modul _mapper_.
