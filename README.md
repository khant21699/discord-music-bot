# 🎵 Discord Music Bot — Setup Guide

## Requirements
- Python 3.10+
- FFmpeg installed on your system
- A Discord Bot Token

---

## Step 1 — Install FFmpeg

**Windows:**
1. Download from https://ffmpeg.org/download.html
2. Extract and add the `bin/` folder to your system PATH
3. Verify: `ffmpeg -version` in terminal

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg -y
```

---

## Step 2 — Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** → give it a name
3. Go to **Bot** → Click **Add Bot**
4. Under **Privileged Gateway Intents**, enable:
   - ✅ Message Content Intent
5. Copy your **Bot Token**
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Connect`, `Speak`, `Read Message History`
7. Open the generated URL to invite the bot to your server

---

## Step 3 — Configure the Bot

Open `bot.py` and replace the token on line 8:
```python
TOKEN = "YOUR_BOT_TOKEN_HERE"
```

Or set it as an environment variable (recommended):
```bash
# Windows
set DISCORD_TOKEN=your_token_here

# macOS/Linux
export DISCORD_TOKEN=your_token_here
```

---

## Step 4 — Install Dependencies & Run

```bash
cd discord-music-bot
pip install -r requirements.txt
python bot.py
```

You should see: `✅ Logged in as YourBot#1234`

---

## Commands

| Command | Description |
|---|---|
| `!play <song or URL>` | Play a song by name or YouTube URL |
| `!play <playlist URL>` | Queue an entire YouTube playlist |
| `!skip` | Skip the current song |
| `!pause` | Pause playback |
| `!resume` | Resume playback |
| `!stop` | Stop music and disconnect |
| `!queue` | Show the current queue |
| `!nowplaying` | Show current song info |
| `!volume <0-100>` | Adjust volume |
| `!shuffle` | Shuffle the queue |
| `!remove <#>` | Remove song from queue by position |
| `!leave` | Disconnect bot from voice |
| `!help` | Show all commands |

---

## Troubleshooting

**"FFmpeg not found"** → Make sure FFmpeg is installed and in your PATH  
**"No audio"** → Check the bot has `Speak` permission in the voice channel  
**"Token invalid"** → Regenerate the token in the Discord Developer Portal  
**Bot doesn't respond** → Ensure `Message Content Intent` is enabled in the portal
