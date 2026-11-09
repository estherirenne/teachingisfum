"""planner.py - logika perencana urutan mengajar (rule-based, tanpa API key, jalan di CPU)."""

import re
from collections import Counter

# ---------- BAGIAN 1: data per usia ----------
AGE = {
    "SD":  dict(sapa="Halo semuanya!", cap=1, tanya="Siapa yang bisa tebak apa yang akan terjadi?",
                gaya="kalimat pendek, analogi mainan, satu konsep per sesi, banyak tebak-tebakan"),
    "SMP": dict(sapa="Halo semuanya!", cap=2, tanya="Menurut kalian, kenapa hasilnya begini?",
                gaya="analogi sehari-hari, boleh dua konsep per sesi, beri tantangan kecil"),
    "SMA": dict(sapa="Halo semuanya!", cap=2, tanya="Di aplikasi apa yang pernah kalian pakai, hal ini muncul?",
                gaya="hubungkan dengan project nyata, jelaskan alasan di balik kode, dorong eksplorasi"),
}

# ---------- BAGIAN 2: kamus bahasa/tool (tambah entri baru di sini kalau mau) ----------
LANG = {
    "html": dict(name="HTML", re=r"\bhtml\b", role="menyusun kerangka halaman", syntax="<h1>Halo!</h1>",
                 build="kita susun kerangka halamannya dengan HTML",
                 analogy=dict(SD="kerangka rumah dari lego", SMP="denah dan tembok rumah", SMA="struktur dokumen yang dibaca browser")),
    "css": dict(name="CSS", re=r"\bcss\b", role="mengatur warna dan tampilan", syntax="h1 { color: orange; }",
                build="kita percantik tampilannya dengan CSS",
                analogy=dict(SD="cat dan hiasan rumah", SMP="interior dan warna rumah", SMA="aturan tampilan yang dipisah dari struktur")),
    "javascript": dict(name="JavaScript", re=r"javascript|\bjs\b", role="membuat halaman bereaksi saat diklik",
                       syntax="alert('Halo!');", build="kita hidupkan dengan JavaScript supaya bisa diklik",
                       analogy=dict(SD="listrik yang bikin lampu menyala", SMP="saklar yang menghidupkan rumah", SMA="logika yang membuat halaman interaktif")),
    "python": dict(name="Python", re=r"python", role="memberi perintah ke komputer lewat kode",
                   syntax="print('Halo!')", build="kita tulis logikanya dengan Python",
                   analogy=dict(SD="bahasa perintah untuk robot", SMP="bahasa yang mirip kalimat bahasa Inggris", SMA="bahasa serbaguna untuk web, data, dan AI")),
    "scratch": dict(name="Scratch", re=r"scratch", role="merangkai logika lewat blok",
                    syntax="blok 'ketika bendera diklik' lalu 'katakan Halo!'", build="kita susun blok-bloknya",
                    analogy=dict(SD="menyusun balok puzzle", SMP="merakit game dari blok logika", SMA="latihan alur logika sebelum bahasa teks")),
}

# ---------- BAGIAN 3: kamus konsep (analogi, permainan tanpa komputer, contoh Scratch, tantangan) ----------
CONCEPT = {
    "variabel": dict(name="Variabel", re=r"variabel|variable", analogy="kotak berlabel untuk menyimpan data",
        syntax="nama = 'Budi'", scratch="buat variabel 'skor', lalu pakai blok 'ubah skor sebesar 1'",
        unplug="Siapkan satu kotak bertuliskan 'skor' berisi kertas angka 0. Setiap ada yang menjawab benar, ganti kertas di dalamnya.",
        challenge="menghitung skor setiap kali disentuh"),
    "perulangan": dict(name="Perulangan (looping)", re=r"perulangan|loop|looping|\bfor\b|while",
        analogy="menyuruh komputer mengulang tanpa capek", syntax="for i in range(3): print(i)",
        scratch="blok 'ulangi 10 kali' yang berisi 'gerak 10 langkah'",
        unplug="Minta semua murid menepuk tangan 5 kali, lalu 20 kali. Tanya: capek nggak? Ada cara yang lebih singkat untuk menyuruhnya?",
        challenge="berjalan memutari panggung dengan blok ulangi"),
    "kondisi": dict(name="Kondisi (jika)", re=r"kondisi|percabangan|\bif\b|\bjika\b",
        analogy="persimpangan jalan: kalau begini ke kiri, kalau tidak ke kanan", syntax="if nilai > 70: print('Lulus')",
        scratch="blok 'jika menyentuh warna merah maka katakan Aduh!'",
        unplug="Mainkan 'Kalau kakak angkat kartu merah, kalian berdiri. Kalau biru, kalian duduk.'",
        challenge="berkata 'Aduh!' hanya saat menyentuh tepi panggung"),
    "fungsi": dict(name="Fungsi", re=r"fungsi|function|blok sendiri", analogy="resep masakan yang bisa dipakai berulang",
        syntax="def sapa(): print('Halo')", scratch="blok buatanmu sendiri bernama 'joget'",
        unplug="Buat satu gerakan joget dan beri nama 'joget'. Setiap kakak sebut 'joget', kalian ulangi gerakan yang sama persis.",
        challenge="menari dengan satu blok buatanmu sendiri"),
    "array": dict(name="Array/List", re=r"array|larik", analogy="rak berisi barang yang diberi nomor",
        syntax="buah = ['apel', 'jeruk']", scratch="blok 'daftar' untuk menyimpan nama teman-temanmu",
        unplug="Baris-kan 5 murid dan beri nomor 1 sampai 5. Panggil 'nomor 3!' dan lihat siapa yang maju.",
        challenge="menyebutkan nama teman-temanmu satu per satu"),
}

PROJECT = [("to-do list", r"to.?do|daftar tugas"), ("kalkulator", r"kalkulator"),
           ("game sederhana", r"game|permainan"), ("kuis", r"kuis|quiz")]


def join_id(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " dan " + items[-1]


# ---------- BAGIAN 4: mesin utama ----------
def build_plan(text: str, age: str):
    a, low = AGE[age], text.lower()
    langs = [k for k, v in LANG.items() if re.search(v["re"], low)]
    concepts = [k for k, v in CONCEPT.items() if re.search(v["re"], low)]
    proj = next((n for n, r in PROJECT if re.search(r, low)), None)

    # Deteksi MODE: pengenalan konsep (fokus ide) vs membangun project (fokus hasil jadi)
    is_project = bool(proj) or bool(re.search(r"\b(web|website|aplikasi|app)\b", low))
    is_intro = bool(re.search(r"pengenalan|konsep|dasar|intro|mengenal", low))
    mode = "project" if is_project and not is_intro else "concept"

    proj_name = proj or "project sederhana"
    first = re.split(r"[.!?\n]", text.strip())[0].strip()
    goal = (first[:1].lower() + first[1:])[:140]
    names = join_id([LANG[k]["name"] for k in langs]) if langs else "bahasa pemrograman yang dipilih"
    use_scratch = "scratch" in langs
    tool = "Scratch" if use_scratch else names

    steps = []
    def add(title, tip, script):
        steps.append({"title": title, "tip": tip, "script": script})

    add("Buka kelas dan ingatkan materi sebelumnya",
        "Recall 2-3 menit supaya murid nyambung dengan pelajaran sebelumnya.",
        f"{a['sapa']} Sebelum mulai, coba ceritakan satu hal yang kalian ingat dari pertemuan lalu. "
        f"Hari ini kita akan belajar {goal}.")

    if mode == "concept":
        # ----- Alur PENGENALAN KONSEP: rasakan dulu -> beri nama -> contoh -> latihan terpandu -> tantangan mini -----
        for k in concepts:
            c = CONCEPT[k]
            add(f"Permainan pembuka tanpa komputer: {c['name']}",
                "Aktivitas fisik 3-5 menit supaya murid merasakan masalahnya dulu sebelum diberi solusi (unplugged).",
                f"Sebelum buka laptop, ayo main dulu! {c['unplug']} {a['tanya']}")
        for k in langs:
            l = LANG[k]
            add(f"Kenalkan {l['name']} secara singkat",
                f"Jelaskan fungsi {l['name']} dengan analogi sesuai usia {age}, jangan terlalu panjang.",
                f"Sekarang kita pakai {l['name']}. {l['name']} itu ibarat {l['analogy'][age]}. Tugasnya: {l['role']}.")
            if k == "scratch":
                add("Kenalan dengan tampilan Scratch",
                    "Cukup 3 hal: panggung, karakter (fuecoco), dan blok perintah. Jangan jelaskan semua menu.",
                    "Lihat layar ini: ini panggung, ini karakter namanya fuecoco, dan ini blok-blok perintah berwarna. "
                    "Kita tarik satu blok ke tengah, lalu klik bendera hijau. Lihat, karakternya bergerak!")
        for k in concepts:
            c = CONCEPT[k]
            demo = c["scratch"] if use_scratch else c["syntax"]
            add(f"Kenalkan konsep {c['name']}", "Beri nama konsepnya SETELAH murid mengalaminya lewat permainan.",
                f"Tadi kalian sudah merasakannya sendiri. Nama kerennya: {c['name']}! Ibarat {c['analogy']}.")
            add(f"Contoh {c['name']} di {tool}", "Peragakan di layar, murid mengamati dulu sebelum mencoba.",
                f"Sekarang aku peragakan: {demo}. Perhatikan apa yang terjadi di layar!")
            add(f"Latihan terpandu: {c['name']}", "Ikuti langkah satu per satu bersama murid, tanpa membuat project utuh.",
                "Ayo ikuti aku pelan-pelan. Ubah angkanya sedikit, tebak dulu hasilnya, baru klik jalankan. "
                "Siapa yang tebakannya benar?")
            add(f"Tantangan mini: {c['name']}", "Satu tantangan kecil saja, boleh dikerjakan berpasangan.",
                f"Tantangan kecil: coba buat karaktermu {c['challenge']}. Boleh minta bantuan teman atau aku ya!")
        if not concepts:
            add("Jelaskan ide utama dengan contoh kecil", "Pilih satu ide saja, beri contoh kecil lalu minta murid mencoba.",
                f"Hari ini kita fokus pada satu ide: {goal}. aku kasih contoh kecil dulu nih, lalu setelah itu giliran kalian ya yang coba.")
        cn = join_id([CONCEPT[k]["name"] for k in concepts]) if concepts else "ide hari ini"
        add("Refleksi dan penutup", "Minta murid menjelaskan ulang dengan kata sendiri untuk cek pemahaman.",
            f"Hari ini kita belajar {cn}. Siapa yang bisa jelaskan dengan kata sendiri? "
            f"Kenapa pakai {cn} lebih gampang daripada menulis berkali-kali?")
    else:
        # ----- Alur MEMBANGUN PROJECT -----
        add("Tunjukkan hasil akhir dulu", "Demo hasil jadi sekitar 1 menit supaya murid tahu tujuan dan termotivasi.",
            f"Lihat dulu hasil akhirnya: sebuah {proj_name}. Di akhir sesi, nanti kalian bisa bikin versi kalian sendiri seperti ini. Seru, kan?")
        for k in langs:
            l = LANG[k]
            add(f"Kenalkan {l['name']} dulu", f"Jelaskan fungsi {l['name']} sebelum menulis kode, pakai analogi sesuai usia {age}.",
                f"Sebelum nulis kode, kenalan dulu dengan {l['name']}. {l['name']} itu ibarat {l['analogy'][age]}. "
                f"Tugasnya: {l['role']}. {a['tanya']}")
        for k in langs:
            l = LANG[k]
            add(f"Syntax pertama {l['name']}", "Tulis bareng-bareng, jangan langsung memberi kode jadi.",
                f"Kita tulis bareng ya, satu baris dulu: {l['syntax']} Perhatikan tanda-tandanya, satu kurung atau titik bisa mengubah hasilnya!")
        for k in concepts:
            c = CONCEPT[k]
            add(f"Konsep: {c['name']}", "Satu konsep, satu contoh kecil, lalu minta murid mencoba.",
                f"Sekarang konsep {c['name']}: ibarat {c['analogy']}. Contohnya: {c['syntax']} Coba ubah sedikit, apa yang berubah?")
        marks = ["Pertama,", "Lalu,", "Terakhir,"]
        parts = [f"{marks[min(i, 2)]} {LANG[k]['build']}." for i, k in enumerate(langs)]
        add("Bangun bareng secara bertahap", "Bangun per lapisan kecil, cek hasil di setiap langkah.",
            f"Sekarang kita bangun {proj_name} pelan-pelan. " + (" ".join(parts) or "Kita mulai dari satu fitur kecil dulu."))
        add("Latihan mandiri", "Beri tantangan ringan dan keliling untuk membantu murid yang macet.",
            f"Giliran kalian! Coba ubah {proj_name}-nya dengan ide sendiri, misalnya ganti warna, teks, atau tambah satu fitur. Kakak akan keliling untuk bantu.")
        add("Refleksi dan penutup", "Minta murid menjelaskan ulang dengan kata sendiri untuk cek pemahaman.",
            f"Hari ini kita sudah belajar {names}. Siapa yang bisa jelaskan dengan kata sendiri? "
            f"Untuk pertemuan depan, coba kembangkan {proj_name}-mu di rumah.")

    # ----- Peringatan / hal yang perlu diperhatikan -----
    warnings = [f"Gaya mengajar {age}: {a['gaya']}."]
    if mode == "concept":
        warnings.insert(0, "Mode pengenalan konsep: fokus murid memahami ide, bukan membuat aplikasi atau web utuh.")
    if age == "SD" and set(langs) & {"html", "css", "javascript", "python"}:
        warnings.insert(0, "Untuk SD, sebaiknya mulai dari Scratch (blok) dulu. Bahasa teks seperti HTML, CSS, JavaScript, atau Python cenderung terlalu berat.")
    if age == "SD" and len(concepts) > 1:
        warnings.insert(0, f"Materi memuat {len(concepts)} konsep. Untuk SD, pilih satu konsep per sesi (sekitar 30-45 menit).")
    elif len(langs) > a["cap"]:
        warnings.insert(0, f"Materi ini memuat {len(langs)} bahasa ({names}), cukup berat untuk {age}. Pertimbangkan dipecah per sesi dan recall dulu pertemuan sebelumnya.")
    if not langs and not concepts:
        warnings.insert(0, "Materi belum menyebut bahasa atau konsep spesifik. Tambahkan (mis. Scratch, Python, perulangan) supaya analisisnya lebih rinci.")

    return {"age_group": age,
            "detected": {"bahasa": [LANG[k]["name"] for k in langs], "konsep": [CONCEPT[k]["name"] for k in concepts],
                         "project": proj_name if mode == "project" else "tidak ada (fokus pengenalan konsep)"},
            "warnings": warnings, "steps": steps}


# ---------- BAGIAN 5: kalimat kunci (hanya tampil kalau materi punya >= 2 kalimat) ----------
STOPWORDS = set("yang dan di ke dari untuk dengan ini itu pada adalah atau juga akan dapat the a an of to in is are".split())
BOOST = {"penting", "ingat", "variabel", "loop", "fungsi", "jika", "contoh", "perulangan", "kondisi", "error"}


def key_sentences(text: str):
    sents = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", text) if len(s.strip()) > 15]
    if len(sents) < 2:
        return []
    freq = Counter(w for w in re.findall(r"\w+", text.lower()) if w not in STOPWORDS and len(w) > 2)
    def score(s):
        ws = [w for w in re.findall(r"\w+", s.lower()) if w not in STOPWORDS]
        return sum(freq[w] for w in ws) / (len(ws) or 1) + 3 * sum(w in BOOST for w in ws)
    return sorted(sents, key=score, reverse=True)[:3]