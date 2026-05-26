"""
MMD Render Host Helper — FastAPI server yang dipanggil n8n untuk trigger Blender render.

Endpoints:
  GET  /              → health check
  GET  /assets        → list available .pmx, .vmd, .wav, .mp4 dari library
  POST /render        → start render (multipart: file upload atau path)
  GET  /jobs/{id}     → check render status
  GET  /jobs/{id}/output → download video hasil

Run:
  python app.py
  → http://localhost:8000
  → http://host.docker.internal:8000 (dari dalam Docker container)
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import subprocess
import os
import uuid
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

app = FastAPI(title="MMD Render Helper", version="1.0")

# === Config (configurable via environment variables — see .env.example) ===
LIBRARY_PATH = Path(os.environ.get("MMD_LIBRARY_PATH", "D:/Data MMD"))
RENDER_SCRIPT = os.environ.get(
    "BLENDER_RENDER_SCRIPT",
    str(Path(__file__).parent.parent / "mmd-renderer" / "render_mmd.py")
)
# Jobs dan uploads relatif ke folder script ini
_THIS_DIR = Path(__file__).parent
JOBS_DIR = Path(os.environ.get("JOBS_DIR", str(_THIS_DIR / "jobs")))
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", str(_THIS_DIR / "uploads")))
BLENDER_EXE = os.environ.get("BLENDER_EXE", "blender")  # asumsi sudah di PATH

JOBS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job registry
JOBS = {}

# Rate limiting: chat_id → list of timestamps (jam terakhir)
import time as _time_module
RATE_LIMITS = {}  # {chat_id: [timestamp1, timestamp2, ...]}
RATE_LIMIT_WINDOW = 3600  # 1 jam
RATE_LIMIT_MAX = 3        # max 3 render per jam per user

def check_rate_limit(chat_id: str) -> tuple[bool, str]:
    """Return (allowed, reason). Auto-cleanup expired timestamps."""
    if not chat_id:
        return True, ""
    now = _time_module.time()
    if chat_id not in RATE_LIMITS:
        RATE_LIMITS[chat_id] = []
    # Cleanup expired
    RATE_LIMITS[chat_id] = [t for t in RATE_LIMITS[chat_id] if now - t < RATE_LIMIT_WINDOW]
    if len(RATE_LIMITS[chat_id]) >= RATE_LIMIT_MAX:
        oldest = RATE_LIMITS[chat_id][0]
        wait_min = int((RATE_LIMIT_WINDOW - (now - oldest)) / 60) + 1
        return False, f"Rate limit: max {RATE_LIMIT_MAX} render/jam. Coba lagi dalam {wait_min} menit."
    return True, ""

def register_render_attempt(chat_id: str):
    if chat_id:
        if chat_id not in RATE_LIMITS:
            RATE_LIMITS[chat_id] = []
        RATE_LIMITS[chat_id].append(_time_module.time())


# === Helpers ===
def scan_library(extensions, max_files=200):
    """Scan library folder cari file dengan extension tertentu."""
    results = []
    for ext in extensions:
        for f in LIBRARY_PATH.rglob(f"*{ext}"):
            if len(results) >= max_files:
                break
            results.append({
                "name": f.name,
                "path": str(f),
                "folder": f.parent.name,
                "size_mb": round(f.stat().st_size / 1024 / 1024, 2)
            })
    return results


def run_render(job_id, params):
    """Background task: jalankan Blender + render_mmd.py."""
    job = JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()

    # Stage 6: use readable name if available
    readable = job.get("readable_name")
    output_filename = f"{readable}_{job_id}.mp4" if readable else f"{job_id}.mp4"
    output_path = str(JOBS_DIR / output_filename)
    job["output_path"] = output_path
    job["output_filename"] = output_filename

    cmd = [
        BLENDER_EXE, "-b", "-P", RENDER_SCRIPT, "--",
        params["model"],
        params["motion"],
        params.get("camera", "none"),
        params["audio"],
        output_path,
        str(params.get("duration", "auto")),
        params.get("bg_video", "none"),
        params.get("facial", "none"),
        str(params.get("brightness", 1.0)),
        str(params.get("contrast", 0.0)),
        str(params.get("saturation", 1.0)),
        params.get("physics", "on"),
        params.get("genshin", "auto"),
        params.get("outline", "on"),
    ]
    job["command"] = " ".join(f'"{c}"' if " " in c else c for c in cmd)

    log_path = JOBS_DIR / f"{job_id}.log"
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            proc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, timeout=3600)
        job["return_code"] = proc.returncode
        job["status"] = "done" if proc.returncode == 0 and os.path.exists(output_path) else "failed"
    except subprocess.TimeoutExpired:
        job["status"] = "timeout"
        job["return_code"] = -1
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)

    job["finished_at"] = datetime.now().isoformat()
    if os.path.exists(output_path):
        job["output_size_mb"] = round(os.path.getsize(output_path) / 1024 / 1024, 2)

    # === AUTO-SEND VIDEO KE TELEGRAM ===
    chat_id = job.get("telegram_chat_id")
    if chat_id and job["status"] == "done" and os.path.exists(output_path):
        size_mb = job["output_size_mb"]
        readable = job.get("readable_name") or job_id
        params = job.get("params", {})
        caption = (
            f"🎬 Render selesai!\n"
            f"📦 {readable}\n"
            f"🎮 Game: {params.get('game_name','-')}\n"
            f"👤 Character: {params.get('character_name','-')}\n"
            f"💃 Motion: {params.get('motion_name','-')}\n"
            f"📊 Size: {size_mb} MB | Job: {job_id}"
        )
        try:
            import httpx
            if size_mb < 50:
                # Send via sendVideo (Telegram limit 50MB for bot)
                with open(output_path, "rb") as f:
                    files = {"video": (os.path.basename(output_path), f, "video/mp4")}
                    data = {
                        "chat_id": chat_id,
                        "caption": caption,
                        "supports_streaming": "true",
                    }
                    r = httpx.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                        files=files, data=data, timeout=300
                    )
                    job["telegram_send_result"] = r.json().get("ok")
            else:
                # Send sebagai document (sampai 50MB) atau fallback link
                try:
                    with open(output_path, "rb") as f:
                        files = {"document": (os.path.basename(output_path), f, "video/mp4")}
                        data = {"chat_id": chat_id, "caption": caption}
                        r = httpx.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
                            files=files, data=data, timeout=600
                        )
                        job["telegram_send_result"] = r.json().get("ok")
                except Exception:
                    # File too big, send link only
                    text = f"{caption}\n\n⚠️ File terlalu besar untuk Telegram ({size_mb}MB).\nLokasi: {output_path}"
                    httpx.post(
                        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={"chat_id": chat_id, "text": text},
                        timeout=30
                    )
        except Exception as e:
            job["telegram_send_error"] = str(e)
            # Fallback: send text notification
            try:
                import httpx
                httpx.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"⚠️ Render selesai tapi gagal kirim video ke Telegram.\nJob: {job_id}\nError: {e}\nFile: {output_path}",
                    },
                    timeout=30
                )
            except Exception:
                pass


# === Routes ===
@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "MMD Render Helper",
        "version": "1.0",
        "library": str(LIBRARY_PATH),
        "library_exists": LIBRARY_PATH.exists(),
        "render_script": RENDER_SCRIPT,
        "render_script_exists": os.path.exists(RENDER_SCRIPT),
        "jobs_active": sum(1 for j in JOBS.values() if j["status"] == "running"),
        "jobs_total": len(JOBS),
    }


@app.get("/assets")
def list_assets(kind: Optional[str] = None, search: Optional[str] = None, limit: int = 30):
    """List asset MMD dari library.
    kind: 'model' (.pmx), 'motion' (.vmd), 'audio' (.wav/.mp3), 'bg' (.mp4/.png/.jpg), 'all'
    search: keyword filter di nama file
    """
    kind_map = {
        "model": [".pmx", ".pmd"],
        "motion": [".vmd"],
        "audio": [".wav", ".mp3"],
        "bg": [".mp4", ".png", ".jpg", ".jpeg", ".webm"],
        "all": [".pmx", ".pmd", ".vmd", ".wav", ".mp3", ".mp4", ".png", ".jpg"],
    }
    exts = kind_map.get(kind or "all", kind_map["all"])
    items = scan_library(exts, max_files=500)
    if search:
        s = search.lower()
        items = [i for i in items if s in i["name"].lower() or s in i["folder"].lower()]
    return {
        "kind": kind,
        "search": search,
        "count": len(items),
        "items": items[:limit],
    }


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    """Upload file dari n8n (file dari Telegram dll). Returns server path."""
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
    session_dir = UPLOADS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    out_path = session_dir / file.filename
    with open(out_path, "wb") as f:
        content = await file.read()
        f.write(content)
    return {
        "session_id": session_id,
        "path": str(out_path),
        "size_mb": round(len(content) / 1024 / 1024, 2),
    }


@app.post("/render")
def start_render(
    model: str = Form(...),
    motion: str = Form(...),
    audio: str = Form(...),
    camera: str = Form("none"),
    facial: str = Form("none"),
    bg_video: str = Form("none"),
    duration: str = Form("auto"),
    brightness: float = Form(1.0),
    contrast: float = Form(0.0),
    saturation: float = Form(1.0),
    physics: str = Form("on"),
    genshin: str = Form("auto"),
    outline: str = Form("on"),
    # Stage 6: naming convention
    game_name: str = Form(""),
    character_name: str = Form(""),
    motion_name: str = Form(""),
    # Auto-send: kalau diisi, video langsung dikirim ke telegram chat setelah done
    chat_id: str = Form(""),
    background_tasks: BackgroundTasks = None,
):
    """Start render — async. Returns job_id, poll /jobs/{id} untuk status."""
    # Validate input files exist
    for label, path in [("model", model), ("motion", motion), ("audio", audio)]:
        if not os.path.exists(path):
            raise HTTPException(400, f"File '{label}' tidak ada: {path}")
    if camera != "none" and not os.path.exists(camera):
        raise HTTPException(400, f"Camera file tidak ada: {camera}")

    # === Rate limit check ===
    allowed, reason = check_rate_limit(chat_id)
    if not allowed:
        raise HTTPException(429, reason)
    register_render_attempt(chat_id)

    job_id = str(uuid.uuid4())[:8]

    # Stage 6: build filename pattern
    def sanitize(s):
        return "".join(c for c in s if c.isalnum() or c in "_-").strip("_") or "unknown"
    if game_name or character_name or motion_name:
        readable_name = f"{sanitize(game_name)}_{sanitize(character_name)}_{sanitize(motion_name)}"
    else:
        readable_name = None

    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "readable_name": readable_name,
        "telegram_chat_id": chat_id if chat_id else None,
        "params": {
            "model": model, "motion": motion, "audio": audio, "camera": camera,
            "facial": facial, "bg_video": bg_video, "duration": duration,
            "brightness": brightness, "contrast": contrast, "saturation": saturation,
            "physics": physics, "genshin": genshin, "outline": outline,
            "game_name": game_name, "character_name": character_name, "motion_name": motion_name,
        },
    }

    params = JOBS[job_id]["params"]
    background_tasks.add_task(run_render, job_id, params)
    return {"job_id": job_id, "status": "queued", "poll_url": f"/jobs/{job_id}"}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    job = JOBS[job_id].copy()
    # Add log tail
    log_path = JOBS_DIR / f"{job_id}.log"
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        job["log_tail"] = "".join(lines[-15:])
    return job


@app.get("/jobs/{job_id}/output")
def get_output(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    job = JOBS[job_id]
    if job["status"] != "done":
        raise HTTPException(400, f"Job belum selesai, status: {job['status']}")
    if not os.path.exists(job["output_path"]):
        raise HTTPException(404, "Output file tidak ada")
    return FileResponse(job["output_path"], media_type="video/mp4",
                         filename=f"mmd_render_{job_id}.mp4")


# Alias mapping untuk game-game populer
GAME_ALIASES = {
    "hsr": ["honkai star rail", "star rail", "starrail"],
    "honkaistarrail": ["honkai star rail"],
    "hi3": ["honkai impact", "honkai impact 3rd", "honkai 3"],
    "hi3rd": ["honkai impact"],
    "honkaiimpact": ["honkai impact"],
    "gi": ["genshin", "genshin impact"],
    "genshinimpact": ["genshin"],
    "ww": ["wuthering waves"],
    "wutheringwaves": ["wuthering waves"],
    "zzz": ["zenless zone zero"],
    "punishing": ["punishing gray raven", "pgr"],
    "pgr": ["punishing gray raven"],
}


def resolve_game_aliases(game_query: str):
    """Return list of search keywords yang akan di-match dengan folder name.
    Bidirectional: 'hsr' → ['honkai star rail'] DAN 'honkai star rail' → ['hsr']
    """
    q_raw = game_query.lower()
    q_normalized = q_raw.replace(" ", "").replace("_", "").replace("-", "")
    candidates = {q_raw, q_normalized}

    # Forward: alias key → values
    if q_normalized in GAME_ALIASES:
        candidates.update(GAME_ALIASES[q_normalized])

    # Reverse: cari di values, return key + sibling values
    for key, values in GAME_ALIASES.items():
        values_normalized = [v.lower().replace(" ", "").replace("_", "") for v in values]
        if q_normalized in values_normalized or q_raw in values:
            candidates.add(key)
            candidates.update(values)

    return list(candidates)


def folder_matches_game(folder_name: str, game_candidates: list):
    """Smart match: cek apakah folder name match dengan game candidates bidirectional.
    'HSR' folder match 'honkai star rail' query, dan sebaliknya.
    """
    folder_lower = folder_name.lower()
    folder_normalized = folder_lower.replace(" ", "").replace("_", "").replace("-", "")
    folder_aliases = resolve_game_aliases(folder_name)
    folder_alias_normalized = set()
    for fa in folder_aliases:
        folder_alias_normalized.add(fa.lower())
        folder_alias_normalized.add(fa.lower().replace(" ", "").replace("_", ""))

    for c in game_candidates:
        c_lower = c.lower()
        c_normalized = c_lower.replace(" ", "").replace("_", "").replace("-", "")
        # Direct partial match
        if c_lower in folder_lower or folder_lower in c_lower:
            return True
        if c_normalized in folder_normalized or folder_normalized in c_normalized:
            return True
        # Check via folder's own aliases
        if c_lower in folder_alias_normalized or c_normalized in folder_alias_normalized:
            return True
    return False


@app.post("/upload_pmx_from_telegram")
def upload_pmx_from_telegram(
    file_id: str = Form(...),
    file_name: str = Form(...),
    game: str = Form(...),
    character: str = Form(...),
):
    """Download PMX dari Telegram file_id, save ke library /Model/<game>/<character>/.
    Returns: full path file yang sudah disimpan + status."""
    import httpx
    # Step 1: Get file path dari Telegram API
    try:
        r = httpx.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
            params={"file_id": file_id},
            timeout=30
        )
        info = r.json()
        if not info.get("ok"):
            return {"success": False, "error": f"getFile failed: {info}"}
        file_path = info["result"]["file_path"]  # contoh: documents/file_42.pmx
    except Exception as e:
        return {"success": False, "error": f"getFile request error: {e}"}

    # Step 2: Build save path: /Model/<game>/<character>/file_name.pmx
    safe_game = "".join(c for c in game if c.isalnum() or c in " _-").strip()
    safe_char = "".join(c for c in character if c.isalnum() or c in " _-").strip()
    if not safe_game or not safe_char:
        return {"success": False, "error": "Game atau character name tidak valid"}

    target_dir = LIBRARY_PATH / "Model" / safe_game / safe_char
    target_dir.mkdir(parents=True, exist_ok=True)
    # Pastikan filename ending .pmx
    if not file_name.lower().endswith(".pmx"):
        file_name += ".pmx"
    target_path = target_dir / file_name

    # Step 3: Download file dari Telegram CDN
    try:
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        with httpx.stream("GET", download_url, timeout=120) as response:
            if response.status_code != 200:
                return {"success": False, "error": f"download failed: HTTP {response.status_code}"}
            with open(target_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        return {"success": False, "error": f"download error: {e}"}

    # Step 4: Verify file
    if not target_path.exists():
        return {"success": False, "error": "File tidak tersimpan"}
    size_mb = round(target_path.stat().st_size / 1024 / 1024, 2)

    return {
        "success": True,
        "path": str(target_path),
        "game": safe_game,
        "character": safe_char,
        "file_name": file_name,
        "size_mb": size_mb,
        "warning": "PMX tersimpan TANPA texture folder. Karakter mungkin tampil tanpa texture/transparan." if size_mb < 1.0 else None,
        "note": "Untuk hasil render terbaik, user perlu upload juga folder Texture/ via FTP atau manual copy."
    }


@app.get("/list_games")
def list_games():
    """List semua folder game yang ada di library Model/."""
    model_root = LIBRARY_PATH / "Model"
    if not model_root.exists():
        return {"count": 0, "games": []}
    games = []
    for f in model_root.iterdir():
        if f.is_dir():
            char_count = sum(1 for sub in f.iterdir() if sub.is_dir())
            games.append({"name": f.name, "character_folders": char_count})
    return {
        "count": len(games),
        "games": games,
        "common_aliases": GAME_ALIASES,
    }


@app.get("/find_character")
def find_character(game: str, character: str = "", min_size_mb: Optional[str] = "1.0"):
    try:
        min_size_mb = float(min_size_mb) if min_size_mb and str(min_size_mb).strip() else 1.0
    except (ValueError, TypeError):
        min_size_mb = 1.0
    # Cap min_size_mb to 1.0 — biar small models seperti Skirk (1.95), Lumine (1.21) ke-detect.
    # AI sering halu kirim 2.0 → kita cap supaya defaultnya tetep 1.0
    if min_size_mb > 1.0:
        min_size_mb = 1.0
    """Stage 1: Cari folder karakter berdasarkan game name + char name.
    Returns: list .pmx files yang ukurannya >= min_size_mb (default 2MB).

    MODE LIST: kalau character="" atau "*" atau "all" → return SEMUA karakter di game folder
    MODE SEARCH: kalau character ada nilai → filter cuma yang match nama itu

    Logic: scan D:/Data MMD/Model/{game}*/{character}*/*.pmx
    """
    model_root = LIBRARY_PATH / "Model"
    if not model_root.exists():
        raise HTTPException(404, f"Model folder tidak ada: {model_root}")

    list_mode = character == "" or character.lower() in ("*", "all", "any")
    char_lower = "" if list_mode else character.lower()

    # Resolve aliases (HSR → "honkai star rail", dll)
    game_candidates = resolve_game_aliases(game)

    matches = []

    # Cari folder game (case-insensitive, alias-aware bidirectional)
    for game_folder in model_root.iterdir():
        if not game_folder.is_dir():
            continue
        if not folder_matches_game(game_folder.name, game_candidates):
            continue
        # Cari folder karakter di dalam game
        for char_folder in game_folder.rglob("*"):
            if not char_folder.is_dir():
                continue
            # Skip texture/sph/tex folders (bukan character folder beneran)
            if char_folder.name.lower() in ('tex', 'texture', 'textures', 'sph', 'sub', 'spa'):
                continue
            if not list_mode and char_lower not in char_folder.name.lower():
                continue
            # Cari .pmx file di folder ini
            for pmx in char_folder.glob("*.pmx"):
                size_mb = round(pmx.stat().st_size / 1024 / 1024, 2)
                if size_mb >= min_size_mb:
                    matches.append({
                        "name": pmx.name,
                        "path": str(pmx),
                        "game_folder": game_folder.name,
                        "char_folder": char_folder.name,
                        "size_mb": size_mb,
                        "valid": True,
                    })

    if list_mode:
        suggestion = (
            f"Ditemukan {len(matches)} karakter di game '{game}'. Tampilkan ke user supaya dia pilih."
            if matches
            else f"Tidak ada karakter di library untuk game '{game}'. Tawarkan upload PMX baru atau pilih game lain."
        )
    else:
        suggestion = (
            f"Ditemukan {len(matches)} model valid untuk '{character}'"
            if matches
            else f"Karakter '{character}' di game '{game}' tidak ada di library. Tawarkan upload PMX baru ke user."
        )

    return {
        "game": game,
        "character": character if not list_mode else "(list mode - all)",
        "list_mode": list_mode,
        "min_size_mb": min_size_mb,
        "count": len(matches),
        "found": len(matches) > 0,
        "matches": matches,
        "suggestion": suggestion,
    }


@app.get("/list_motions_grouped")
def list_motions_grouped(limit: Optional[str] = "30", search: Optional[str] = None):
    try:
        limit = int(limit) if limit and str(limit).strip() else 30
    except (ValueError, TypeError):
        limit = 30
    """Stage 2: List motions grouped per folder (1 folder = 1 motion set).
    Returns folder name (= nama motion) + files yang ada (main, camera, facial, audio).
    """
    motion_root = LIBRARY_PATH / "Motion"
    motions = []
    if not motion_root.exists():
        return {"count": 0, "motions": []}

    for folder in motion_root.rglob("*"):
        if not folder.is_dir():
            continue
        if len(motions) >= limit:
            break
        vmds = list(folder.glob("*.vmd"))
        if not vmds:
            continue
        # Categorize VMDs dengan PRIORITY pattern matching:
        # 1. camera/cam → camera_vmd
        # 2. facial/face → facial_vmd
        # 3. Sisanya = motion candidates, dengan priority:
        #    a. Name match "main", "motion", "dance" (prioritas tertinggi — biasanya yang dichoreograph dengan camera)
        #    b. Fallback ke biggest .vmd
        main_vmd = None
        main_vmd_priority = 99  # lower = higher priority (0 = best)
        camera_vmd = None
        facial_vmd = None
        audio_file = None
        # File yang dikenal sebagai motion VARIANT (bukan main motion) — di-skip kecuali no other option
        VARIANT_KEYWORDS = ['originalquickmagic', 'quickmagic', 'original', 'backup', 'old', 'lip']

        for f in folder.iterdir():
            n = f.name.lower()
            if f.suffix.lower() == ".vmd":
                if "cam" in n:
                    camera_vmd = str(f)
                elif "facial" in n or "face" in n:
                    facial_vmd = str(f)
                else:
                    # Determine priority
                    if "main" in n:
                        prio = 0
                    elif "motion" in n:
                        prio = 1
                    elif "dance" in n:
                        prio = 2
                    elif any(kw in n for kw in VARIANT_KEYWORDS):
                        prio = 10  # variant — last resort
                    else:
                        prio = 5  # generic name
                    # Pilih kalau priority lebih baik, atau sama priority tapi file lebih besar
                    if prio < main_vmd_priority or (prio == main_vmd_priority and main_vmd and f.stat().st_size > os.path.getsize(main_vmd)):
                        main_vmd = str(f)
                        main_vmd_priority = prio
            elif f.suffix.lower() in (".wav", ".mp3"):
                audio_file = str(f)
        if not main_vmd:
            continue
        item = {
            "name": folder.name,
            "folder": str(folder),
            "main_vmd": main_vmd,
            "camera_vmd": camera_vmd,
            "facial_vmd": facial_vmd,
            "audio": audio_file,
            "has_camera": camera_vmd is not None,
            "has_facial": facial_vmd is not None,
            "has_audio": audio_file is not None,
        }
        if search and search.lower() not in folder.name.lower():
            continue
        motions.append(item)
    return {"count": len(motions), "motions": motions}


@app.get("/youtube_search")
def youtube_search(query: str, max_results: int = 1):
    """Stage 2/4: Cari YouTube video via yt-dlp. Returns title + URL.
    Default cuma 1 hasil (top match). Append "mmd" ke query kalau belum ada.
    """
    if "mmd" not in query.lower():
        query = f"{query} mmd"
    try:
        result = subprocess.run(
            ["yt-dlp", "--default-search", "ytsearch",
             "--print", "%(title)s||%(webpage_url)s||%(duration)s",
             "--no-warnings", "--skip-download", "--no-playlist",
             "--flat-playlist",
             f"ytsearch{max_results}:{query}"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if result.returncode != 0:
            return {"query": query, "error": result.stderr[-500:], "results": []}
        results = []
        for line in result.stdout.strip().split("\n"):
            if "||" in line:
                parts = line.split("||")
                if len(parts) >= 2:
                    results.append({
                        "title": parts[0],
                        "url": parts[1],
                        "duration_sec": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
                    })
        return {"query": query, "count": len(results), "results": results}
    except subprocess.TimeoutExpired:
        return {"query": query, "error": "Timeout", "results": []}
    except Exception as e:
        return {"query": query, "error": str(e), "results": []}


@app.post("/extract_audio_from_url")
def extract_audio_from_url(url: str = Form(...), output_name: Optional[str] = Form(None)):
    """Stage 4: Extract audio dari YouTube URL → save sebagai WAV.
    Returns path file audio yang sudah di-extract.
    """
    if not output_name:
        output_name = f"extracted_{uuid.uuid4().hex[:8]}"
    out_path = JOBS_DIR / f"{output_name}.wav"
    try:
        result = subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "wav", "--audio-quality", "0",
             "-o", str(out_path).replace(".wav", ".%(ext)s"),
             "--no-playlist", "--no-warnings", url],
            capture_output=True, text=True, timeout=300, encoding="utf-8"
        )
        if result.returncode != 0:
            return {"error": result.stderr[-500:], "url": url}
        if not out_path.exists():
            # yt-dlp might add .wav extension differently, search
            for f in JOBS_DIR.glob(f"{output_name}.*"):
                if f.suffix.lower() == ".wav":
                    out_path = f
                    break
        if not out_path.exists():
            return {"error": "Audio file tidak ketemu setelah extract", "url": url}
        size_mb = round(out_path.stat().st_size / 1024 / 1024, 2)
        return {
            "url": url,
            "audio_path": str(out_path),
            "size_mb": size_mb,
            "duration_sec": None,  # could be extracted via ffprobe if needed
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout extracting audio (>5 min)", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


@app.get("/list_backgrounds")
def list_backgrounds(game: Optional[str] = None, subfolder: Optional[str] = None, kind: Optional[str] = None, limit_per_folder: Optional[str] = "10"):
    # Lenient int parsing
    try:
        limit_per_folder = int(limit_per_folder) if limit_per_folder and str(limit_per_folder).strip() else 10
    except (ValueError, TypeError):
        limit_per_folder = 10
    """Stage 5: List background files dengan folder hierarchy + alias support.
    Param game: filter dengan game name (alias-aware: HSR=Honkai Star Rail, dll)
    Param subfolder: nama subfolder spesifik (kalau user sudah pilih kategori)
    Param kind: 'image' / 'video' / None (all)
    Param limit_per_folder: max files per subfolder (default 10)

    Return structure:
      - subfolders[]: kalau bg folder game ada subfolders → list folder names (untuk user pilih kategori dulu)
      - items[]: list bg files (kalau no subfolders atau subfolder sudah dipilih)
    """
    bg_root = LIBRARY_PATH / "Background"
    image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    video_exts = {'.mp4', '.mov', '.webm', '.avi'}

    # Resolve game alias
    if game:
        game_candidates = resolve_game_aliases(game)
    else:
        game_candidates = None

    # Lenient kind validation: ignore invalid values, treat as None
    valid_kind = kind if kind in ("image", "video") else None

    def file_kind(ext):
        if ext in image_exts: return "image"
        if ext in video_exts: return "video"
        return None

    def file_matches_kind(ext):
        if valid_kind is None: return ext in image_exts or ext in video_exts
        if valid_kind == "image": return ext in image_exts
        if valid_kind == "video": return ext in video_exts
        return False

    # Cari game folder (kalau game disebut)
    target_game_folders = []
    if game_candidates and bg_root.exists():
        for f in bg_root.iterdir():
            if not f.is_dir():
                continue
            if folder_matches_game(f.name, game_candidates):
                target_game_folders.append(f)

    if not target_game_folders and game_candidates:
        return {
            "game": game,
            "found_game_folder": False,
            "subfolders": [],
            "items": [],
            "message": f"Folder background untuk game '{game}' tidak ada. Coba tanpa filter game atau list semua bg."
        }

    # Kalau gak ada filter game, scan semua di Background root
    if not target_game_folders:
        target_game_folders = [bg_root]

    subfolders_info = []
    items = []

    for game_folder in target_game_folders:
        if not game_folder.exists():
            continue
        # Cek apakah ada subfolder
        subdirs = [d for d in game_folder.iterdir() if d.is_dir()]

        if subdirs and not subfolder:
            # MODE: tampilkan subfolders dulu sebagai category
            for sd in subdirs:
                # Count files di subfolder ini
                file_count = sum(1 for f in sd.rglob("*") if f.is_file() and file_matches_kind(f.suffix.lower()))
                if file_count > 0:
                    subfolders_info.append({
                        "name": sd.name,
                        "path": str(sd),
                        "game_folder": game_folder.name,
                        "file_count": file_count,
                    })
            # Juga tampilkan file yg di-root game folder (kalau ada)
            for f in game_folder.iterdir():
                if f.is_file() and file_matches_kind(f.suffix.lower()):
                    items.append({
                        "name": f.name,
                        "path": str(f),
                        "kind": file_kind(f.suffix.lower()),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 2),
                        "subfolder": "(root)",
                        "preview_url": f"http://localhost:8000/preview?path={f}",
                    })
                    if len(items) >= limit_per_folder:
                        break
        else:
            # MODE: subfolder dipilih atau gak ada subfolder → list files
            scan_root = game_folder
            if subfolder:
                sub_path = game_folder / subfolder
                if sub_path.exists() and sub_path.is_dir():
                    scan_root = sub_path
            count_in_folder = 0
            for f in scan_root.rglob("*"):
                if not f.is_file():
                    continue
                ext = f.suffix.lower()
                if not file_matches_kind(ext):
                    continue
                items.append({
                    "name": f.name,
                    "path": str(f),
                    "kind": file_kind(ext),
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 2),
                    "subfolder": str(f.parent.relative_to(game_folder)) if f.parent != game_folder else "(root)",
                    "preview_url": f"http://localhost:8000/preview?path={f}",
                })
                count_in_folder += 1
                if count_in_folder >= limit_per_folder:
                    break

    return {
        "game": game,
        "subfolder": subfolder,
        "kind": kind,
        "found_game_folder": len(target_game_folders) > 0,
        "subfolders": subfolders_info,
        "subfolders_count": len(subfolders_info),
        "items": items,
        "items_count": len(items),
        "hint": (
            "Tampilkan subfolders ke user untuk dia pilih kategori dulu" if subfolders_info
            else "Tampilkan items langsung ke user"
        ),
    }


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


@app.post("/send_preview_to_telegram")
def send_preview_to_telegram(
    chat_id: str = Form(...),
    path: str = Form(...),
    caption: str = Form(""),
    frame_sec: float = Form(1.0),
):
    """Send preview image atau video ke Telegram chat.
    - Image: kirim sebagai photo
    - Video: extract thumbnail frame, kirim sebagai photo (lebih cepat dari upload full video)
    """
    if not os.path.exists(path):
        raise HTTPException(404, f"File tidak ada: {path}")

    ext = os.path.splitext(path)[1].lower()
    image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    video_exts = {'.mp4', '.mov', '.webm', '.avi'}

    import httpx

    if ext in image_exts:
        # Kirim langsung image
        with open(path, "rb") as f:
            files = {"photo": (os.path.basename(path), f, "image/jpeg")}
            data = {"chat_id": chat_id, "caption": caption}
            r = httpx.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                files=files, data=data, timeout=60
            )
        return {"sent": True, "type": "photo", "telegram_response": r.json()}
    elif ext in video_exts:
        # Untuk video: extract thumbnail dulu (lebih reliable + cepat)
        thumb_path = JOBS_DIR / f"_thumb_{uuid.uuid4().hex[:6]}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(frame_sec), "-i", path,
                 "-frames:v", "1", "-q:v", "3", str(thumb_path)],
                capture_output=True, timeout=30
            )
            if not thumb_path.exists():
                raise HTTPException(500, "Gagal extract thumbnail dari video")
            # Send thumbnail dengan caption note bahwa ini video
            with open(thumb_path, "rb") as f:
                files = {"photo": (thumb_path.name, f, "image/jpeg")}
                cap = caption + f"\n🎥 [VIDEO PREVIEW] {os.path.basename(path)}"
                data = {"chat_id": chat_id, "caption": cap.strip()}
                r = httpx.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                    files=files, data=data, timeout=60
                )
            # Cleanup thumb
            try: thumb_path.unlink()
            except: pass
            return {"sent": True, "type": "video_thumbnail", "telegram_response": r.json()}
        except subprocess.TimeoutExpired:
            raise HTTPException(500, "Timeout extracting thumbnail")
    else:
        raise HTTPException(400, f"Unsupported file type: {ext}")


@app.get("/preview")
def get_preview(path: str, frame_sec: float = 1.0):
    """Return preview image dari file (kalau video: extract frame at frame_sec, kalau image: kirim langsung).
    """
    if not os.path.exists(path):
        raise HTTPException(404, "File tidak ada")
    ext = os.path.splitext(path)[1].lower()
    image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    if ext in image_exts:
        return FileResponse(path, media_type="image/" + ext.replace('.', ''))
    # Video: extract frame
    preview_path = JOBS_DIR / f"_preview_{uuid.uuid4().hex[:6]}.jpg"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(frame_sec), "-i", path,
             "-frames:v", "1", "-q:v", "3", str(preview_path)],
            capture_output=True, timeout=30
        )
        if preview_path.exists():
            return FileResponse(str(preview_path), media_type="image/jpeg")
        raise HTTPException(500, "Preview extraction failed")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/analyze_bg")
def analyze_background(path: str):
    """Analisis background (image atau video) → return brightness, dominant tone, type, recommended settings."""
    if not os.path.exists(path):
        raise HTTPException(404, f"File tidak ada: {path}")

    ext = os.path.splitext(path)[1].lower()
    is_video = ext in ('.mp4', '.mov', '.avi', '.webm', '.mkv')
    bg_type = "video" if is_video else "image"

    # Extract frame untuk analyze (kalau video, ambil frame tengah; kalau image langsung pakai)
    import tempfile
    sample_path = path
    if is_video:
        try:
            sample_path = str(JOBS_DIR / f"_bg_sample_{uuid.uuid4().hex[:6]}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "5", "-i", path, "-frames:v", "1", "-q:v", "2", sample_path],
                capture_output=True, timeout=30
            )
            if not os.path.exists(sample_path):
                # Fallback: ambil frame pertama
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-frames:v", "1", "-q:v", "2", sample_path],
                    capture_output=True, timeout=30
                )
        except Exception as e:
            return {"type": bg_type, "error": f"ffmpeg failed: {e}", "path": path}

    # Analyze pixel brightness pakai PIL
    try:
        from PIL import Image, ImageStat
        img = Image.open(sample_path).convert("RGB")
        stat = ImageStat.Stat(img)
        r_mean, g_mean, b_mean = stat.mean
        brightness = (r_mean + g_mean + b_mean) / 3 / 255  # 0..1
        # Dominant tone (very simple)
        if brightness > 0.7:
            mood = "bright/light"
        elif brightness > 0.4:
            mood = "neutral/medium"
        else:
            mood = "dark/moody"
        # Dominant hue check
        if r_mean > g_mean and r_mean > b_mean:
            color_bias = "warm/red"
        elif b_mean > r_mean and b_mean > g_mean:
            color_bias = "cool/blue"
        else:
            color_bias = "balanced/green"

        # Recommended char tone (supaya kontras dengan bg)
        if brightness > 0.65:
            rec_brightness = 0.85  # bg terang → karakter agak redup
            rec_contrast = 0.1
        elif brightness < 0.35:
            rec_brightness = 1.15  # bg gelap → karakter lebih cerah
            rec_contrast = 0.05
        else:
            rec_brightness = 1.0
            rec_contrast = 0.0

        result = {
            "type": bg_type,
            "path": path,
            "brightness": round(brightness, 3),
            "rgb_mean": [round(r_mean, 1), round(g_mean, 1), round(b_mean, 1)],
            "mood": mood,
            "color_bias": color_bias,
            "resolution": {"width": img.width, "height": img.height},
            "recommended_character_tone": {
                "brightness": rec_brightness,
                "contrast": rec_contrast,
                "saturation": 1.0
            },
            "reasoning": f"Background {mood} dengan tone {color_bias}. Disarankan karakter brightness={rec_brightness} biar match."
        }
        # Cleanup sample frame
        if is_video and sample_path != path:
            try:
                os.remove(sample_path)
            except Exception:
                pass
        return result
    except ImportError:
        return {"type": bg_type, "error": "PIL/Pillow tidak terinstall. Run: pip install pillow", "path": path}
    except Exception as e:
        return {"type": bg_type, "error": str(e), "path": path}


@app.get("/jobs")
def list_jobs(limit: int = 20):
    """List semua jobs (recent first)."""
    jobs_sorted = sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)
    return {"count": len(jobs_sorted), "jobs": jobs_sorted[:limit]}


if __name__ == "__main__":
    import uvicorn
    print("\n=== MMD Render Helper ===")
    print("Host:   http://localhost:8000")
    print("Docker: http://host.docker.internal:8000")
    print("Docs:   http://localhost:8000/docs")
    print("=========================\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
