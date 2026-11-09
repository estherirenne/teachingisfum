"""TeachingIsFum - catatan persiapan mengajar coding (FastAPI + PostgreSQL)."""
import os
import re
import time
from collections import Counter
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]  # diisi oleh docker-compose
templates = Jinja2Templates(directory="app/templates")


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Buat tabel saat startup (retry sedikit jaga-jaga DB belum siap)
    for attempt in range(10):
        try:
            with get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notes (
                        id SERIAL PRIMARY KEY,
                        kind TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )""")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS analyses (
                        id SERIAL PRIMARY KEY,
                        age_group TEXT NOT NULL,
                        highlights TEXT[] NOT NULL,
                        phrases TEXT[] NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )""")
            break
        except psycopg.OperationalError:
            time.sleep(2)
    yield


app = FastAPI(title="TeachingIsFum", lifespan=lifespan)


# ---------- Skema input ----------
class NoteIn(BaseModel):
    # self_gap = kekurangan saya | student_strength = kelebihan murid | student_improve = perlu dikembangkan
    kind: Literal["self_gap", "student_strength", "student_improve"]
    subject: str = Field(min_length=1, max_length=100)  # nama murid / topik materi
    content: str = Field(min_length=1, max_length=1000)


class AnalyzeIn(BaseModel):
    text: str = Field(min_length=20, max_length=8000)
    age_group: Literal["SD", "SMP", "SMA"]


# ---------- Analisis sederhana (tanpa API key, jalan di CPU) ----------
STOPWORDS = set("yang dan di ke dari untuk dengan ini itu pada adalah atau juga akan dapat the a an of to in is are".split())
BOOST = {"penting", "ingat", "variabel", "loop", "fungsi", "jika", "contoh", "perulangan", "kondisi", "error"}

TEMPLATES = {
    "SD": "Hai teman-teman! Hari ini kita main tebak-tebakan: \"{s}\" Coba bayangin kayak mainan, ya!",
    "SMP": "Oke, perhatiin satu hal penting ini: \"{s}\" Menurut kalian, kapan kita butuh ini?",
    "SMA": "Poin kunci hari ini: \"{s}\" Coba hubungkan dengan project nyata, di mana ini dipakai?",
}


def analyze_text(text: str, age_group: str):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if len(s.strip()) > 15]
    words = [w for w in re.findall(r"\w+", text.lower()) if w not in STOPWORDS and len(w) > 2]
    freq = Counter(words)

    def score(s):  # skor = frekuensi kata kunci + bonus kata penting
        ws = [w for w in re.findall(r"\w+", s.lower()) if w not in STOPWORDS]
        return sum(freq[w] for w in ws) / (len(ws) or 1) + 3 * sum(w in BOOST for w in ws)

    top = sorted(sentences, key=score, reverse=True)[:3]
    return top, [TEMPLATES[age_group].format(s=s) for s in top]


# ---------- Endpoint ----------
@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")


@app.get("/notes")
def list_notes(kind: str | None = None):
    with get_conn() as conn:
        if kind:
            rows = conn.execute("SELECT * FROM notes WHERE kind=%s ORDER BY id DESC", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    return rows


@app.post("/notes", status_code=201)
def create_note(note: NoteIn):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO notes (kind, subject, content) VALUES (%s,%s,%s) RETURNING *",
            (note.kind, note.subject, note.content),
        ).fetchone()
    return row


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id=%s", (note_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="note not found")
    return Response(status_code=204)


@app.post("/analyze", status_code=201)
def analyze(data: AnalyzeIn):
    highlights, phrases = analyze_text(data.text, data.age_group)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analyses (age_group, highlights, phrases) VALUES (%s,%s,%s)",
            (data.age_group, highlights, phrases),
        )
    return {"age_group": data.age_group, "highlights": highlights, "phrases": phrases}


@app.get("/analyses")
def list_analyses():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT 10").fetchall()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
