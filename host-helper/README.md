# Host Helper (FastAPI)

Backend Python helper yang bridge antara **n8n** dan **filesystem + Blender + YouTube**.

## Run

```bash
pip install -r requirements.txt

# Set environment variable
export TELEGRAM_BOT_TOKEN=your_token_here   # Linux/Mac
$env:TELEGRAM_BOT_TOKEN="your_token_here"   # Windows PowerShell

python app.py
# Server runs at http://localhost:8000
# Swagger docs: http://localhost:8000/docs
```

## Endpoints (14 total)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Health check |
| `/list_games` | GET | List game folder di library |
| `/find_character?game=X&character=Y` | GET | Cari karakter (alias-aware) |
| `/list_motions_grouped?limit=N&search=X` | GET | List motion folders + categorized files |
| `/list_backgrounds?game=X&subfolder=Y` | GET | List bg dengan subfolder hierarchy |
| `/preview?path=X` | GET | Return preview image file |
| `/send_preview_to_telegram` | POST | Kirim image/video thumbnail ke Telegram |
| `/youtube_search?query=X` | GET | yt-dlp YouTube search |
| `/extract_audio_from_url` | POST | Download audio dari URL → WAV |
| `/analyze_bg?path=X` | GET | Vision analysis (brightness, mood) |
| `/upload_pmx_from_telegram` | POST | Save uploaded PMX dari Telegram |
| `/render` | POST | Trigger Blender render async |
| `/jobs/{id}` | GET | Job detail + log_tail |
| `/jobs/{id}/output` | GET | Download MP4 result |

## Configuration

Edit constants di top of `app.py`:

```python
LIBRARY_PATH = Path("D:/Data MMD")              # Your MMD library
RENDER_SCRIPT = "path/to/render_mmd.py"
BLENDER_EXE = "blender"                          # Must be in PATH
```

## Key Features

- **Alias resolution**: HSR ↔ Honkai Star Rail, GI ↔ Genshin, dll
- **Priority motion picker**: Main > Motion > Dance > generic > variant
- **Rate limiting**: 3 renders/jam per chat_id
- **Auto-send video**: setelah render done, kirim MP4 ke Telegram

## Dependencies

- FastAPI + uvicorn — REST API
- httpx — HTTP client (Telegram + cloud APIs)
- Pillow — image analysis
- yt-dlp — YouTube extraction (requires ffmpeg in PATH)
- subprocess — Blender CLI execution
