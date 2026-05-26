# 🎬 MMD AI Assistant

AI-powered Telegram bot for automated **MikuMikuDance (MMD)** video rendering via conversational 6-stage workflow.

[![n8n](https://img.shields.io/badge/n8n-workflow-EA4B71?logo=n8n)](https://n8n.io/)
[![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini-412991?logo=openai)](https://platform.openai.com/)
[![Blender](https://img.shields.io/badge/Blender-3.6_LTS-F5792A?logo=blender)](https://www.blender.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_API-26A5E4?logo=telegram)](https://core.telegram.org/bots/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Final Project — Bootcamp DQLab GenAI & n8n Batch 23**
> by **Gregorius Darrell Andika Setya** (@dard1ka)

---

## 🎯 What It Does

User chats with bot on Telegram → AI Agent guide step-by-step pilih asset (karakter, motion, audio, background) → Blender render otomatis di background → Video MP4 hasil otomatis dikirim balik ke chat user.

**Try it live**: [t.me/MMD_Dardika_bot](https://t.me/MMD_Dardika_bot)

```
User : "Halo mau render"
Bot  : "Karakter dari game apa?"
User : "Genshin"
Bot  : [list 13 karakter]
User : "Lumine"
Bot  : [list 15 motion]
User : "Watch Me"
Bot  : [list background HSR] + auto-confirm camera/audio
User : "Natlan Beach"
Bot  : "🎬 Render dimulai! Job ID: abc12345"
       ⏳ (5-10 menit)
Bot  : [kirim video MP4 langsung ke chat] ✅
```

---

## 🏗️ Architecture

```
┌──────────┐        ┌─────────────────┐
│ Telegram │───────▶│ Cloudflare      │
│   User   │        │ Tunnel (HTTPS)  │
└──────────┘        └────────┬────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ n8n (Docker)   │
                    │ port 5678      │
                    │ ┌────────────┐ │
                    │ │ AI Agent   │ │  + Simple Memory
                    │ │ (OpenAI    │ │  + 11 Custom Tools
                    │ │ gpt-4o-mini│ │
                    │ └────────────┘ │
                    └────────┬───────┘
                             │
                             ▼ HTTP
                    ┌────────────────┐
                    │ Host Helper    │
                    │ FastAPI Python │
                    │ port 8000      │
                    └────────┬───────┘
                             │
                ┌────────────┼────────────┐
                ▼            ▼            ▼
           ┌────────┐  ┌─────────┐  ┌─────────┐
           │Blender │  │ yt-dlp  │  │Library  │
           │ + MMD  │  │ YouTube │  │D:\Data  │
           │ + GI   │  │ DL      │  │ MMD\    │
           └────────┘  └─────────┘  └─────────┘
```

---

## ✨ Features

### 🎮 Multi-Game Character Support
- **Genshin Impact**, **Honkai Star Rail**, **Honkai Impact 3rd**, **Wuthering Waves**, dan custom games
- Alias-aware: ketik `HSR`, `Honkai Star Rail`, atau `star rail` — semua resolve ke folder yang sama
- Auto-detect karakter dengan PMX size threshold (default 1MB)

### 💃 Smart Motion Library
- 30+ motion choreography dengan auto-detect Camera.vmd & Facial.vmd
- **Priority-based motion picker**: `Main.vmd` > `Motion.vmd` > `Dance.vmd` > variant files (anti-confusion dengan `OriginalQuickMagic.vmd` dll)
- YouTube preview link untuk setiap motion via yt-dlp search

### 🎵 Audio Pipeline
- Auto-pakai audio dari folder motion
- Fallback: extract audio dari YouTube URL via `yt-dlp + ffmpeg`
- User upload audio custom juga support

### 🖼️ Background System
- Folder hierarchy navigation (e.g., `Background/HSR/Amphoreus/`, `Background/HSR/Planarcadia/`)
- Image + video background support (auto-detect format)
- **Send preview** langsung ke Telegram chat sebelum render
- Tone analysis dengan vision (PIL): brightness, mood, recommended character tone

### 🎨 Anime Rendering
- Blender 3.6 + `mmd_tools` plugin
- **Genshin Shader v2.2.1** by Ben Ayers untuk anime cel-shading
- Auto-detect `Camera.vmd` / `Facial.vmd` di folder motion (defense-in-depth vs AI hallucination)
- Shadow catcher plane untuk bayangan karakter
- Auto-trim intro frames (skip idle T-pose start)
- Smart camera auto-fit kalau Camera.vmd missing

### 🤖 AI Agent Features
- **11 Custom HTTP Tools** dengan AI-defined parameters
- **6-Stage Conversational Flow** dengan auto-advance dalam single reply
- **Simple Memory** per user (session = chat_id, window=30)
- **Anti-hallucination validation** layer
- **Multi-user support** dengan rate limiting (3 render/jam/user)

### 📲 Auto-Delivery
- Video MP4 otomatis dikirim balik ke chat user via Telegram `sendVideo` API setelah render done
- Filename pattern: `{game}_{character}_{motion}_{job_id}.mp4`
- Fallback ke `sendDocument` untuk file <50MB

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Workflow Engine** | [n8n](https://n8n.io/) (Docker) | v2.16+ |
| **AI Model** | OpenAI API (`gpt-4o-mini`) | API v1 |
| **Chat Interface** | Telegram Bot API | Latest |
| **Backend API** | [FastAPI](https://fastapi.tiangolo.com/) + uvicorn | Python 3.10+ |
| **Render Engine** | [Blender](https://www.blender.org/) + [mmd_tools](https://github.com/MMD-Blender/blender_mmd_tools) | 3.6 LTS |
| **Shader** | Genshin Shader v2.2.1 by Ben Ayers | Commercial |
| **Audio/Video** | ffmpeg + yt-dlp | Latest |
| **Tunnel** | Cloudflared (quick tunnel) | Latest |
| **Image Analysis** | Pillow (PIL) | 10.x |

---

## 📂 Project Structure

```
mmd-ai-assistant/
├── README.md                    # This file
├── LICENSE                      # MIT
├── .gitignore                   # Python + Node + Blender
├── .env.example                 # Environment variables template
├── host-helper/
│   ├── app.py                   # FastAPI main (14 endpoints)
│   ├── requirements.txt         # Python dependencies
│   └── README.md
├── mmd-renderer/
│   ├── render_mmd.py            # Blender CLI render script
│   └── README.md
├── n8n-workflow/
│   ├── workflow.json            # Export n8n workflow (user export sendiri)
│   └── system-message.md        # AI Agent system prompt
└── scripts/
    ├── start-all.ps1            # Start all services (n8n + tunnel + helper)
    └── stop-all.ps1             # Stop all services
```

---

## 🚀 Quick Start

### Prerequisites
- Windows 10/11
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [Python 3.10+](https://www.python.org/downloads/)
- [Blender 3.6 LTS](https://www.blender.org/download/lts/3-6/)
- [Blender mmd_tools plugin](https://github.com/MMD-Blender/blender_mmd_tools)
- [Genshin Shader v2.2.1](https://www.youtube.com/@thiagoaoyama) (or similar anime shader)
- Telegram account + bot token (via [@BotFather](https://t.me/BotFather))
- OpenAI API key

### Setup

1. **Clone repo**
   ```bash
   git clone https://github.com/Dard1ka/mmd-ai-assistant.git
   cd mmd-ai-assistant
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env.local
   # Edit .env.local dengan token & path kamu
   ```

3. **Install host helper dependencies**
   ```bash
   cd host-helper
   pip install -r requirements.txt
   ```

4. **Start n8n via Docker**
   ```bash
   docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n
   ```

5. **Import workflow ke n8n**
   - Buka `http://localhost:5678`
   - Import `n8n-workflow/workflow.json`
   - Setup credentials (Telegram, OpenAI)
   - Paste system message dari `n8n-workflow/system-message.md`

6. **Start all services**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1
   ```

7. **Test bot di Telegram**
   - Cari bot kamu di Telegram
   - Ketik `halo mau render`
   - Follow conversational flow

---

## 🎬 6-Stage Conversational Flow

| Stage | What | AI Actions |
|-------|------|-----------|
| **1. Karakter** | User pilih game | `list_games` + `find_character` → tampilkan semua karakter (13-17) |
| **2. Motion** | Pilih dance choreography | `list_motions_grouped` → 15 motion dengan flag camera/facial/audio |
| **3+4. Verification** | Cek camera & audio | Auto-detect Camera.vmd di folder, fallback YouTube extract kalau audio kosong |
| **5. Background** | Pilih background | `list_backgrounds` per game + subfolder nav + image preview via `send_preview` |
| **6. Render** | Render & deliver | Validate path → `start_render` → Blender → auto-send MP4 ke Telegram |

---

## 🧠 11 Custom AI Tools

| Tool | Function |
|------|----------|
| `list_games` | List semua game folder di library |
| `find_character` | Cari karakter (alias-aware: HSR, GI, WW, HI3) |
| `list_motions_grouped` | List motion folder + grouped files |
| `youtube_search` | YouTube search via yt-dlp |
| `extract_audio_from_url` | Download audio dari URL → WAV |
| `list_backgrounds` | List bg dengan subfolder hierarchy |
| `analyze_background` | Vision: brightness/tone analysis |
| `send_preview` | Kirim image/video thumbnail ke Telegram |
| `start_render` | Trigger Blender render async |
| `check_render_status` | Cek status render via job_id |
| `upload_pmx_to_library` | Save uploaded PMX file dari Telegram |

---

## 🐛 Key Challenges & Lessons

### LLM Hallucination
**Problem**: AI Agent claim it used `Camera.vmd` di reply tapi actually pass `"none"` ke render tool.

**Solution**: **Defense-in-depth** — render script auto-detect `Camera.vmd` & `Facial.vmd` di folder motion REGARDLESS of what AI said. Helper validates file existence dan reject fake paths. System prompts include explicit anti-hallucination rules.

### Motion Picker Confusion
**Problem**: Naive picker pilih file `.vmd` terbesar sebagai main motion → `OriginalQuickMagic.vmd` (2.7MB) chosen over `Main.vmd` (878KB) yang sesungguhnya match dengan Camera.vmd.

**Solution**: **Priority-based selection**: `Main.vmd` (priority 0) > `Motion.vmd` (1) > `Dance.vmd` (2) > generic name (5) > variant keywords like `OriginalQuickMagic` (10).

### Alias Mismatch
**Problem**: User type "HSR", folder named "HSR", model folder named "Honkai Star Rail" — partial match fails.

**Solution**: **Bidirectional alias resolution** — `HSR ↔ Honkai Star Rail`, `GI ↔ Genshin Impact`, dll. Folder match checks both directions.

### Memory Loss
**Problem**: After 10+ conversation turns, AI Agent lupa selected character path → hallucinate placeholder like `CharacterName.pmx`.

**Solution**: Memory context window 30 + strict validation rules in system message + helper-level path existence check.

---

## 📊 Bootcamp Materials Coverage

| Material | Status | Implementation |
|----------|--------|----------------|
| Trigger Node | ✅ | Telegram Trigger |
| Action Node | ✅ | Send Message, Send Video |
| HTTP Request | ✅ | 11 HTTP Tools ke FastAPI |
| Webhook | ✅ | Telegram webhook via Cloudflare HTTPS |
| Code Node (Python) | ✅ | FastAPI handler + subprocess Blender |
| AI Agent | ✅ | OpenAI gpt-4o-mini |
| Chat Model | ✅ | OpenAI Chat Model |
| Memory | ✅ | Simple Memory (session=chat_id, window=30) |
| Tools | ✅ | 11 custom HTTP Request Tools |
| Error Handling | ✅ | Try-catch helper, 429 rate limit, 400 path validation |
| Logging | ✅ | Per-job log file |
| Environment Variables | ✅ | .env.local + Docker env |
| Telegram Bot Integration | ✅ | Full sendMessage + sendVideo + sendPhoto |
| AI Ethics | ✅ | Multi-user rate limiting, no data persistence |

---

## 🗺️ Future Roadmap

### Short-term
- [ ] Upgrade to `gpt-4o` (better reliability)
- [ ] Support ZIP upload (texture folder included)
- [ ] Google Sheet logger untuk analytics

### Mid-term
- [ ] Cloudflare Named Tunnel (stable URL)
- [ ] Render queue prioritization (VIP users)
- [ ] Shader presets (anime / realistic / chibi)
- [ ] Web UI dashboard

### Long-term
- [ ] Custom fine-tuned model khusus MMD vocabulary
- [ ] Auto-pose generation dari text prompt
- [ ] Cloud render farm (multi-GPU)
- [ ] SaaS monetization untuk MMD community

---

## 📜 License

MIT License — see [LICENSE](LICENSE) file for details.

**Note**: Genshin Shader v2.2.1 oleh Ben Ayers adalah **commercial product** — perlu beli license sendiri. Repo ini hanya include integration code, BUKAN shader file.

---

## 🙏 Credits

- **Mentor**: [DQLab](https://dqlab.id/) Bootcamp GenAI & n8n Batch 23
- **MMD Community**: [Polygon Movie Maker](https://learnmmd.com/), [LearnMMD](https://learnmmd.com/)
- **mmd_tools**: [MMD-Blender community](https://github.com/MMD-Blender/blender_mmd_tools)
- **Genshin Shader v2.2.1**: Ben Ayers (commercial)
- **AI Layer**: [OpenAI](https://openai.com/), [n8n.io](https://n8n.io/)

---

## 📬 Contact

- **Telegram Bot Demo**: [@MMD_Dardika_bot](https://t.me/MMD_Dardika_bot)
- **GitHub**: [@Dard1ka](https://github.com/Dard1ka)
- **Email**: darrellandika2509@gmail.com

---

<p align="center">
  <i>Built with ❤️ for the MMD community — automation that removes friction between intent and result.</i>
</p>
