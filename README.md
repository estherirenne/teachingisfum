# TeachingIsFum

Teaching is fum, because learning to teach should be fun. #terinspirasi dari film spongebob yang patrick nya bikin slogan di chumbucket (Chum is Fum!).

Web app untuk membantu persiapan mengajar coding anak SD-SMA: highlight poin penting dari materi mengajar, contoh kalimat mengajar per usia, dan catatan pribadi (improve diri sendiri + perkembangan murid).

**Stack:** FastAPI, PostgreSQL 16, Docker Compose.

## Cara menjalankan
```bash
git clone (https://github.com/estherirenne/teachingisfum.git)
cd teachingisfum
cp .env.example .env
docker compose up -d --build
```
Buka http://localhost:8000. Adminer (opsional): `docker compose --profile tools up -d` lalu http://localhost:8080 (System: PostgreSQL, Server: db).

## Endpoint
`GET /health`, `GET /notes`, `POST /notes`, `DELETE /notes/{id}`, `POST /analyze`, `GET /analyses`

## Sumber
FastAPI, psycopg, Jinja2 (open-source library).

## AI Usage Declaration
- Alat: (isi, mis. Claude)
- Bagian yang dibantu: (isi)
- Contoh prompt utama: (isi)

## Screenshot / Artikel / Video
(isi setelah selesai)
