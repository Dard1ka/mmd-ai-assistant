# MMD AI Assistant

A Telegram bot that automates MikuMikuDance (MMD) video rendering through a conversational AI workflow. Users select a character, motion, audio, and background through chat; the system renders the video in Blender and delivers the result back to Telegram.

Built as the final project for DQLab Bootcamp GenAI & n8n Batch 23 by Gregorius Darrell Andika Setya.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Blender 3.6](https://img.shields.io/badge/blender-3.6_LTS-orange.svg)](https://www.blender.org/)

Live demo: [t.me/MMD_Dardika_bot](https://t.me/MMD_Dardika_bot)

---

## Overview

MikuMikuDance is a free 3D animation software used widely in the anime dance video community since 2008. Producing a single 15-second video typically requires manually selecting a character model, body motion file, camera file, facial expression file, audio track, and background, then tuning shaders and render settings. Setup commonly takes longer than the dance itself.

This project replaces the desktop workflow with a Telegram chat. The user has a conversation, the system handles asset discovery, file validation, YouTube audio extraction, Blender rendering, and video delivery.

## How It Works

```
User (Telegram)
      |
      v
Cloudflare Tunnel (HTTPS)
      |
      v
n8n (Docker) ----- OpenAI gpt-4o-mini
   |              Simple Memory
   |              11 HTTP Tools
   |
   v
FastAPI Helper (port 8000)
   |
   +---> Blender 3.6 + mmd_tools + Genshin Shader
   +---> yt-dlp + ffmpeg
   +---> Local library (D:/Data MMD/)
```

The conversation runs in six stages, all advancing automatically within a single reply when possible.

| Stage | Description |
|-------|-------------|
| 1. Character | User picks a game; bot lists every valid character from the library |
| 2. Motion | Bot lists 15 motion options with flags for camera, facial, and audio availability |
| 3. Camera & Facial | Bot verifies what is available in the motion folder |
| 4. Audio | If audio is missing, bot offers YouTube extraction |
| 5. Background | Bot lists backgrounds filtered by game, with subfolder navigation and preview support |
| 6. Render | Bot validates paths, triggers Blender, and delivers the MP4 to chat |

## Features

- Multi-game character library with alias resolution (HSR, Honkai Star Rail, GI, Genshin Impact, WW, HI3, etc.)
- Priority-based motion file selection that prefers `Main.vmd` over variant files like `OriginalQuickMagic.vmd`
- Automatic detection of `Camera.vmd` and `Facial.vmd` in the motion folder as a safeguard against AI tool-call errors
- YouTube audio extraction through yt-dlp with ffmpeg conversion to WAV
- Background hierarchy navigation (subfolder per game category) with image and video preview sent directly to the user
- Auto-trim intro frames to skip idle T-pose at the start of motion data
- Smart camera auto-fit when no camera file is provided (calculates character bounding box)
- Multi-user support with per-user rate limiting (3 renders per hour)
- Automatic video delivery via Telegram Bot API after render completion

## Tech Stack

| Layer | Component |
|-------|-----------|
| Workflow engine | n8n (Docker) |
| Language model | OpenAI API, gpt-4o-mini |
| Chat interface | Telegram Bot API |
| Backend API | FastAPI, uvicorn (Python 3.10+) |
| Render engine | Blender 3.6 LTS with mmd_tools plugin |
| Shader | Genshin Shader v2.2.1 by Ben Ayers (commercial, not included) |
| Audio and video | ffmpeg, yt-dlp |
| Tunnel | Cloudflared quick tunnel |
| Image analysis | Pillow |

## Project Structure

```
mmd-ai-assistant/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── host-helper/
│   ├── app.py                  FastAPI backend with 14 endpoints
│   ├── requirements.txt
│   └── README.md
├── mmd-renderer/
│   ├── render_mmd.py           Blender CLI render script (16 args)
│   └── README.md
├── n8n-workflow/
│   ├── workflow.json           Exported n8n workflow (user export)
│   └── system-message.md       AI Agent system prompt
└── scripts/
    ├── start-all.ps1           Service launcher (n8n, tunnel, helper)
    └── stop-all.ps1
```

## Setup

### Prerequisites

- Windows 10 or 11
- Docker Desktop
- Python 3.10 or newer
- Blender 3.6 LTS with the [mmd_tools](https://github.com/MMD-Blender/blender_mmd_tools) plugin installed
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An OpenAI API key
- ffmpeg available on PATH

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/Dard1ka/mmd-ai-assistant.git
   cd mmd-ai-assistant
   ```

2. Configure environment variables:
   ```
   copy .env.example .env.local
   ```
   Open `.env.local` and fill in your tokens and paths.

3. Install Python dependencies for the helper:
   ```
   cd host-helper
   pip install -r requirements.txt
   ```

4. Start the n8n container:
   ```
   docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n
   ```

5. Import the workflow into n8n:
   - Open `http://localhost:5678`
   - Import `n8n-workflow/workflow.json`
   - Configure Telegram and OpenAI credentials
   - Paste the contents of `n8n-workflow/system-message.md` into the AI Agent's System Message field

6. Start all services:
   ```
   powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1
   ```

The script starts the n8n container, opens a Cloudflare tunnel for HTTPS, and runs the FastAPI helper. It also handles tunnel URL changes by recreating the container with the new `WEBHOOK_URL` environment variable.

### Usage

Send a message to your bot. The conversation will begin with a greeting and proceed through the six stages described above.

Example exchange:

```
User: halo mau render
Bot:  Karakter dari game apa?
User: Genshin
Bot:  Ditemukan 13 karakter dari Genshin: ...
User: Lumine
Bot:  Oke pakai Lumine.
      Motion tersedia (15 pilihan): ...
User: Watch Me
Bot:  Pakai motion Watch Me.
      Background untuk Genshin: ...
User: Natlan Beach
Bot:  Render dimulai. Job ID: abc12345
      [5-10 minutes later]
Bot:  [delivers MP4 video to chat]
```

## AI Agent Tools

The agent has 11 custom HTTP Request Tools that map to FastAPI helper endpoints.

| Tool | Purpose |
|------|---------|
| `list_games` | Enumerate game folders in the library |
| `find_character` | Search characters within a game (alias-aware) |
| `list_motions_grouped` | List motion folders with categorized files |
| `youtube_search` | Search YouTube via yt-dlp for preview links |
| `extract_audio_from_url` | Download and convert audio from a YouTube URL |
| `list_backgrounds` | List backgrounds with subfolder hierarchy |
| `analyze_background` | Vision analysis for brightness and tone |
| `send_preview` | Send an image or video thumbnail to Telegram |
| `start_render` | Trigger an asynchronous Blender render |
| `check_render_status` | Query job status and tail the render log |
| `upload_pmx_to_library` | Save a PMX file uploaded through Telegram |

## Notes on Reliability

Large language models can produce inconsistent tool calls. Three defensive measures address this:

1. The render script independently scans the motion folder for `Camera.vmd` and `Facial.vmd` regardless of what the agent claims it passed.
2. The FastAPI helper validates that every file path in a render request exists on disk before launching Blender.
3. The system prompt includes explicit anti-hallucination rules, validation checklists before tool calls, and a memory window of 30 turns.

## Bootcamp Material Coverage

| Material | Implementation |
|----------|----------------|
| Trigger node | Telegram Trigger |
| Action node | Telegram Send Message, Send Video |
| HTTP Request | 11 HTTP Tools targeting the FastAPI helper |
| Webhook | Telegram webhook via Cloudflare tunnel |
| Code node | Python subprocess calls to Blender |
| AI Agent | OpenAI gpt-4o-mini |
| Chat Model | OpenAI Chat Model node |
| Memory | Simple Memory keyed by chat_id, window 30 |
| Tools | 11 HTTP Request Tools with AI-defined parameters |
| Error handling | Helper try-except, HTTP 429 rate limiting, HTTP 400 path validation |
| Logging | Per-job log file written to `host-helper/jobs/{id}.log` |
| Environment variables | `.env.local` and Docker `-e` flags |
| Telegram integration | sendMessage, sendVideo, sendPhoto, sendDocument |
| AI ethics | Per-user rate limiting, no persistent storage of user data |

## Roadmap

- Upgrade the chat model to gpt-4o for improved tool-call reliability
- Accept ZIP uploads so character texture folders can be included
- Integrate Google Sheets for render history logging
- Move from Cloudflare quick tunnel to a named tunnel for a stable URL
- Render queue prioritization and a small web dashboard
- Shader presets (anime, realistic, chibi)

## License

MIT License. See [LICENSE](LICENSE) for details.

Genshin Shader v2.2.1 by Ben Ayers is a separate commercial product and is not included in this repository. Users must purchase their own license to use it.

MMD character models used during development belong to their respective creators and are not redistributed here.

## Credits

- [DQLab](https://dqlab.id/) — Bootcamp GenAI & n8n Batch 23
- [n8n.io](https://n8n.io/) — Workflow engine
- [OpenAI](https://openai.com/) — Language model
- [Blender Foundation](https://www.blender.org/) — Render engine
- [mmd_tools](https://github.com/MMD-Blender/blender_mmd_tools) — PMX and VMD support for Blender
- Ben Ayers — Genshin Shader v2.2.1 (commercial)
- The MMD community, including [LearnMMD](https://learnmmd.com/) and contributors on Reddit, Bilibili, and YouTube

## Contact

- Bot demo: [@MMD_Dardika_bot](https://t.me/MMD_Dardika_bot)
- GitHub: [@Dard1ka](https://github.com/Dard1ka)
- Email: darrellandika2509@gmail.com
