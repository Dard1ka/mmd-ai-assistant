# n8n Workflow Setup

Panduan import & configure n8n workflow untuk MMD AI Assistant.

## Prerequisites

- n8n running via Docker (`docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n`)
- Telegram Bot Token (dari [@BotFather](https://t.me/BotFather))
- OpenAI API Key
- Host Helper FastAPI running di `http://localhost:8000`
- Cloudflare quick tunnel running (untuk HTTPS webhook)

## Import Workflow

1. Buka n8n UI: `http://localhost:5678`
2. Login / register
3. New Workflow → Import from File → pilih `workflow.json` *(export sendiri dari workflow yang sudah jadi)*
4. Set credentials:
   - **Telegram account** → paste bot token
   - **OpenAI account** → paste API key

## Configure AI Agent

1. Klik node **AI Agent**
2. Field **Source for Prompt**: `Define below`
3. Field **Prompt**: 
   ```
   {{ $json.message.text || ($json.message.document ? 'User uploaded file: ' + $json.message.document.file_name + ' (file_id: ' + $json.message.document.file_id + ')' : 'No content') }}
   ```
4. **System Message**: copy-paste dari [`system-message.md`](system-message.md)
5. **Chat Model** subnode → OpenAI Chat Model → model: `gpt-4o-mini`
6. **Memory** subnode → Simple Memory → Session Key: `{{ $('Telegram Trigger').item.json.message.chat.id }}` → window: 30

## Tools Setup (11 total)

Tambah HTTP Request Tool untuk setiap endpoint helper:

| Tool Name | Method | URL | Notes |
|-----------|--------|-----|-------|
| `list_games` | GET | `http://host.docker.internal:8000/list_games` | No params |
| `find_character` | GET | `http://host.docker.internal:8000/find_character` | Params: game, character, min_size_mb |
| `list_motions_grouped` | GET | `http://host.docker.internal:8000/list_motions_grouped` | Params: limit, search |
| `youtube_search` | GET | `http://host.docker.internal:8000/youtube_search` | Param: query |
| `extract_audio_from_url` | POST | `http://host.docker.internal:8000/extract_audio_from_url` | Body: url |
| `list_backgrounds` | GET | `http://host.docker.internal:8000/list_backgrounds` | Params: game, subfolder, kind, limit_per_folder |
| `analyze_background` | GET | `http://host.docker.internal:8000/analyze_bg` | Param: path |
| `send_preview` | POST | `http://host.docker.internal:8000/send_preview_to_telegram` | Body: chat_id (expression), path, caption |
| `start_render` | POST | `http://host.docker.internal:8000/render` | Body: 13 params + chat_id (expression) |
| `check_render_status` | GET | `=http://host.docker.internal:8000/jobs/{{ $fromAI('job_id', '...', 'string') }}` | Path param via expression |
| `upload_pmx_to_library` | POST | `http://host.docker.internal:8000/upload_pmx_from_telegram` | Body: file_id, file_name, game, character |

## Critical Settings

### Telegram Webhook (HTTPS)
- n8n container WAJIB pakai env `WEBHOOK_URL=https://your-cloudflare-tunnel.trycloudflare.com`
- Setiap kali tunnel URL berubah (quick tunnel always changes per restart), recreate n8n container dengan URL baru

### chat_id Auto-fill (Multi-user Support)
- Param `chat_id` di tool `send_preview` & `start_render` HARUS pakai expression (BUKAN "Defined by AI"):
  ```
  {{ $('Telegram Trigger').item.json.message.chat.id }}
  ```
- Ini ensure bot kirim ke chat user yang chat (bukan hardcode 1 user)

### Publish Workflow
- Di n8n v2.0+, "Publish" = activate. Workflow harus published untuk auto-trigger Telegram webhook
- Setiap update System Message / Tools → klik Publish lagi untuk apply

## Test Flow

Setelah semua setup:
1. Kirim message ke bot Telegram (e.g., "halo")
2. Cek `n8n → Executions` tab — harus ada execution baru
3. AI Agent harus reply greeting message
4. Lanjut flow Stage 1-6

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Bot tidak reply | Tunnel URL outdated | Restart cloudflared + recreate n8n container dengan WEBHOOK_URL baru |
| Webhook 530 error | Tunnel disconnected | `cloudflared tunnel --url http://localhost:5678` again |
| AI halu tool call | Memory penuh / model lemah | Increase memory window 30+ atau upgrade ke `gpt-4o` |
| Tool returns "param missing" | Param order salah di tool config | Match order: game, subfolder, kind, limit_per_folder (sesuai helper) |
