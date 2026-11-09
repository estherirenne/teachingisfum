# ---------- Stage 1: BUILDER (install dependency) ----------
# Tag versi spesifik (bukan latest) supaya build selalu konsisten
FROM python:3.12.7-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1
# COPY requirements dulu SEBELUM source code -> layer cache dipakai ulang
# kalau cuma kode yang berubah (pip install tidak diulang)
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---------- Stage 2: RUNTIME (image akhir yang kecil) ----------
FROM python:3.12.7-slim AS runtime
ENV PYTHONUNBUFFERED=1
WORKDIR /app
# Ambil hasil install saja dari builder (tanpa cache pip / tool build)
COPY --from=builder /install /usr/local
# COPY (bukan ADD): ADD bisa auto-extract tar & download URL, tidak kita butuhkan
COPY app ./app
# Jalankan sebagai non-root demi keamanan
RUN useradd -m appuser
USER appuser
EXPOSE 8000
# Exec form (JSON array) -> uvicorn jadi PID 1 dan menerima sinyal stop dengan benar
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
