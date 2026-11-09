"""TeachingIsFum - catatan persiapan mengajar coding (FastAPI + PostgreSQL)."""
import os
import re
import time
from collections import Counter
from contextlib import asynccontextmanager
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
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
                    CREATE TABLE IF NOT EXISTS lesson_plans (
                        id SERIAL PRIMARY KEY,
                        age_group TEXT NOT NULL,
                        material TEXT NOT NULL,
                        result JSONB NOT NULL,
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


STOPWORDS = set("yang dan di ke dari untuk dengan ini itu pada adalah atau juga akan dapat the a an of to in is are".split())
BOOST = {"penting", "ingat", "variabel", "loop", "fungsi", "jika", "contoh", "perulangan", "kondisi", "error"}

# ---------- Perencana urutan mengajar (rule-based, tanpa API key, jalan di CPU) ----------
AGE = {
    "SD":  dict(sapa="Halo teman-teman hebat!", cap=1, tanya="Siapa yang bisa tebak apa yang akan terjadi?",
                gaya="kalimat pendek, analogi mainan, satu konsep per sesi, banyak tebak-tebakan"),
    "SMP": dict(sapa="Halo semuanya!", cap=2, tanya="Menurut kalian, kenapa hasilnya begini?",
                gaya="analogi sehari-hari, boleh dua konsep per sesi, beri tantangan kecil"),
    "SMA": dict(sapa="Halo semuanya!", cap=2, tanya="Di aplikasi apa yang pernah kalian pakai, hal ini muncul?",
                gaya="hubungkan dengan project nyata, jelaskan alasan di balik kode, dorong eksplorasi"),
}

# Bahasa/tool: re = kata kunci deteksi, analogy per usia, role, syntax contoh, build = peran saat membangun project
LANG = {
    "html": dict(name="HTML", re=r"\bhtml\b", role="menyusun kerangka halaman", syntax="<h1>Halo!</h1>",
                 build="kita susun kerangka halamannya dengan HTML",
                 analogy=dict(SD="kerangka rumah dari lego", SMP="denah dan tembok rumah",
                              SMA="struktur dokumen yang dibaca browser")),
    "css": dict(name="CSS", re=r"\bcss\b", role="mengatur warna dan tampilan", syntax="h1 { color: orange; }",
                build="kita percantik tampilannya dengan CSS",
                analogy=dict(SD="cat dan hiasan rumah", SMP="interior dan warna rumah",
                             SMA="aturan tampilan yang dipisah dari struktur")),
    "javascript": dict(name="JavaScript", re=r"javascript|\bjs\b", role="membuat halaman bereaksi saat diklik",
                       syntax="alert('Halo!');", build="kita hidupkan dengan JavaScript supaya bisa diklik",
                       analogy=dict(SD="listrik yang bikin lampu menyala", SMP="saklar yang menghidupkan rumah",
                                    SMA="logika yang membuat halaman interaktif")),
    "python": dict(name="Python", re=r"python", role="memberi perintah ke komputer lewat kode",
                   syntax="print('Halo!')", build="kita tulis logikanya dengan Python",
                   analogy=dict(SD="bahasa perintah untuk robot", SMP="bahasa yang mirip kalimat bahasa Inggris",
                                SMA="bahasa serbaguna untuk web, data, dan AI")),
    "scratch": dict(name="Scratch", re=r"scratch", role="merangkai logika lewat blok",
                    syntax="blok 'ketika bendera diklik' lalu 'katakan Halo!'", build="kita susun blok-bloknya",
                    analogy=dict(SD="menyusun balok puzzle", SMP="merakit game dari blok logika",
                                 SMA="latihan alur logika sebelum bahasa teks")),
}

CONCEPT = {
    "variabel": dict(name="Variabel", re=r"variabel|variable", analogy="kotak berlabel untuk menyimpan data",
                     syntax="nama = 'Budi'"),
    "perulangan": dict(name="Perulangan", re=r"perulangan|loop|\bfor\b|while",
                       analogy="menyuruh komputer mengulang tanpa capek", syntax="for i in range(3): print(i)"),
    "kondisi": dict(name="Kondisi (if)", re=r"kondisi|percabangan|\bif\b",
                    analogy="persimpangan jalan: kalau begini ke kiri, kalau tidak ke kanan",
                    syntax="if nilai > 70: print('Lulus')"),
    "fungsi": dict(name="Fungsi", re=r"fungsi|function", analogy="resep masakan yang bisa dipakai berulang",
                   syntax="def sapa(): print('Halo')"),
    "array": dict(name="Array/List", re=r"array|larik", analogy="rak berisi barang yang diberi nomor",
                  syntax="buah = ['apel', 'jeruk']"),
}

PROJECT = [("to-do list", r"to.?do|daftar tugas"), ("kalkulator", r"kalkulator"),
           ("game sederhana", r"game|permainan"), ("kuis", r"kuis|quiz")]


def join_id(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " dan " + items[-1]


def build_plan(text: str, age: str):
    a, low = AGE[age], text.lower()
    langs = [k for k, v in LANG.items() if re.search(v["re"], low)]
    concepts = [k for k, v in CONCEPT.items() if re.search(v["re"], low)]
    proj = next((n for n, r in PROJECT if re.search(r, low)), "project sederhana")
    first = re.split(r"[.!?\n]", text.strip())[0].strip()
    goal = (first[:1].lower() + first[1:])[:140]
    names = join_id([LANG[k]["name"] for k in langs]) if langs else "bahasa pemrograman yang dipilih"

    steps = []
    def add(title, tip, script):
        steps.append({"title": title, "tip": tip, "script": script})

    add("Buka kelas dan ingatkan materi sebelumnya",
        "Recall 2-3 menit supaya murid nyambung dengan pelajaran sebelumnya.",
        f"{a['sapa']} Sebelum mulai, coba ceritakan satu hal yang kalian ingat dari pertemuan lalu. "
        f"Hari ini kita akan belajar {goal}.")
    add("Tunjukkan hasil akhir dulu",
        "Demo hasil jadi sekitar 1 menit supaya murid tahu tujuan dan termotivasi.",
        f"Lihat dulu hasil akhirnya: sebuah {proj}. Di akhir sesi, kalian bisa bikin versi kalian sendiri. Seru, kan?")
    for k in langs:
        l = LANG[k]
        add(f"Kenalkan {l['name']} dulu",
            f"Jelaskan fungsi {l['name']} sebelum menulis kode, pakai analogi sesuai usia {age}.",
            f"Sebelum nulis kode, kenalan dulu dengan {l['name']}. {l['name']} itu ibarat {l['analogy'][age]}. "
            f"Tugasnya: {l['role']}. {a['tanya']}")
    for k in langs:
        l = LANG[k]
        add(f"Syntax pertama {l['name']}",
            "Tulis bareng-bareng, jangan langsung memberi kode jadi.",
            f"Kita tulis bareng ya, satu baris dulu: {l['syntax']} "
            f"Perhatikan tanda-tandanya, satu kurung atau titik bisa mengubah hasilnya!")
    for k in concepts:
        c = CONCEPT[k]
        add(f"Konsep: {c['name']}", "Satu konsep, satu contoh kecil, lalu minta murid mencoba.",
            f"Sekarang konsep {c['name']}: ibarat {c['analogy']}. Contohnya: {c['syntax']} "
            f"Coba ubah sedikit, apa yang berubah?")
    marks = ["Pertama,", "Lalu,", "Terakhir,"]
    parts = [f"{marks[min(i, 2)]} {LANG[k]['build']}." for i, k in enumerate(langs)]
    add("Bangun bareng secara bertahap", "Bangun per lapisan kecil, cek hasil di setiap langkah.",
        f"Sekarang kita bangun {proj} pelan-pelan. " + (" ".join(parts) or "Kita mulai dari satu fitur kecil dulu."))
    add("Latihan mandiri", "Beri tantangan ringan dan keliling untuk membantu murid yang macet.",
        f"Giliran kalian! Coba ubah {proj}-nya dengan ide sendiri, misalnya ganti warna, teks, atau tambah satu fitur. "
        f"Kakak akan keliling untuk bantu.")
    add("Refleksi dan penutup", "Minta murid menjelaskan ulang dengan kata sendiri untuk cek pemahaman.",
        f"Hari ini kita sudah belajar {names}. Siapa yang bisa jelaskan dengan kata sendiri? "
        f"Untuk pertemuan depan, coba kembangkan {proj}-mu di rumah.")

    warnings = [f"Gaya mengajar {age}: {a['gaya']}."]
    if len(langs) > a["cap"]:
        warnings.insert(0, f"Materi ini memuat {len(langs)} bahasa ({names}), cukup berat untuk {age}. "
                           f"Pertimbangkan dipecah per sesi, dan recall dulu pertemuan sebelumnya.")
    if not langs and not concepts:
        warnings.insert(0, "Materi belum menyebut bahasa atau konsep spesifik. Tambahkan (mis. HTML, Python, perulangan) "
                           "supaya analisisnya lebih rinci.")
    return {"age_group": age,
            "detected": {"bahasa": [LANG[k]["name"] for k in langs], "konsep": [CONCEPT[k]["name"] for k in concepts],
                         "project": proj},
            "warnings": warnings, "steps": steps}


def key_sentences(text: str):
    """Kalimat kunci: skor = frekuensi kata + bonus kata penting."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if len(s.strip()) > 15]
    freq = Counter(w for w in re.findall(r"\w+", text.lower()) if w not in STOPWORDS and len(w) > 2)
    def score(s):
        ws = [w for w in re.findall(r"\w+", s.lower()) if w not in STOPWORDS]
        return sum(freq[w] for w in ws) / (len(ws) or 1) + 3 * sum(w in BOOST for w in ws)
    return sorted(sents, key=score, reverse=True)[:3]


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