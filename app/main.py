"""main.py - API + halaman web TeachingIsFum (FastAPI + PostgreSQL + Redis cache)."""
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
import redis
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.planner import build_plan, key_sentences

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL")  # kosong -> app jalan tanpa cache
templates = Jinja2Templates(directory="app/templates")

# ---------- BAGIAN CACHE (Redis) ----------
cache = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2) if REDIS_URL else None
CACHE_TTL = 60  # detik


def cache_get(key):
    try:
        return cache.get(key) if cache else None
    except redis.RedisError:  # Redis mati -> abaikan, app tetap jalan lewat database
        return None


def cache_set(key, value):
    try:
        if cache:
            cache.setex(key, CACHE_TTL, value)
    except redis.RedisError:
        pass


def cache_clear():  # dipanggil setiap data berubah (invalidasi)
    try:
        if cache:
            for k in cache.scan_iter("notes:*"):
                cache.delete(k)
    except redis.RedisError:
        pass


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for _ in range(10):
        try:
            with get_conn() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY, kind TEXT NOT NULL, subject TEXT NOT NULL,
                    content TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now())""")
                conn.execute("""CREATE TABLE IF NOT EXISTS lesson_plans (
                    id SERIAL PRIMARY KEY, age_group TEXT NOT NULL, material TEXT NOT NULL,
                    result JSONB NOT NULL, created_at TIMESTAMPTZ DEFAULT now())""")
            break
        except psycopg.OperationalError:
            time.sleep(2)
    yield


app = FastAPI(title="TeachingIsFum", lifespan=lifespan)


class NoteIn(BaseModel):
    kind: Literal["self_gap", "student_strength", "student_improve"]
    subject: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=1000)


class AnalyzeIn(BaseModel):
    text: str = Field(min_length=20, max_length=8000)
    age_group: Literal["SD", "SMP", "SMA"]


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
    key = f"notes:{kind or 'all'}"
    hit = cache_get(key)
    if hit is not None:  # ada di cache -> tidak menyentuh database
        return Response(hit, media_type="application/json", headers={"X-Cache": "HIT"})
    with get_conn() as conn:
        if kind:
            rows = conn.execute("SELECT * FROM notes WHERE kind=%s ORDER BY id DESC", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    body = json.dumps(jsonable_encoder(rows))
    cache_set(key, body)
    return Response(body, media_type="application/json", headers={"X-Cache": "MISS"})


@app.post("/notes", status_code=201)
def create_note(note: NoteIn):
    with get_conn() as conn:
        row = conn.execute("INSERT INTO notes (kind, subject, content) VALUES (%s,%s,%s) RETURNING *",
                           (note.kind, note.subject, note.content)).fetchone()
    cache_clear()  # data berubah -> hapus cache lama
    return row


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int):
    with get_conn() as conn:
        deleted = conn.execute("DELETE FROM notes WHERE id=%s", (note_id,)).rowcount
    if deleted == 0:
        raise HTTPException(status_code=404, detail="note not found")
    cache_clear()
    return Response(status_code=204)


@app.post("/analyze", status_code=201)
def analyze(data: AnalyzeIn):
    result = build_plan(data.text, data.age_group)
    result["highlights"] = key_sentences(data.text)
    with get_conn() as conn:
        conn.execute("INSERT INTO lesson_plans (age_group, material, result) VALUES (%s,%s,%s)",
                     (data.age_group, data.text, Jsonb(result)))
    return result


@app.get("/analyses")
def list_analyses():
    with get_conn() as conn:
        return conn.execute("SELECT id, age_group, material, result, created_at FROM lesson_plans "
                            "ORDER BY id DESC LIMIT 10").fetchall()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")