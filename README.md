# 🎵 Discord Music Bot — Setup Guide

This bot uses a **static FFmpeg 7 engine** to bypass YouTube streaming restrictions. It is optimized for low-resource Linux instances (like Oracle Cloud) but also runs on Windows.

---

## 🐧 Linux Guide (Oracle Cloud / Ubuntu / Debian)

### 🛠 Prerequisites
- **Python 3.10+**
- **Discord Bot Token** (with Message Content Intent enabled)
- **Linux Environment** (Ubuntu/Debian)

---

### 🚀 Step 1 — Install FFmpeg (Static Build)

We use a static binary to avoid conflicts with outdated system versions.

1. **Download:**
   ```bash
   wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
   ```

2. **Extract:**
   ```bash
   tar xvf ffmpeg-release-amd64-static.tar.xz
   ```

3. **Verify Path:**
   Run `ls /home/ubuntu/discord-music-bot/ffmpeg-7.0.2-amd64-static/ffmpeg`.
   Ensure this matches the `FFMPEG_EXE` path in `bot.py`.

---

### 🤖 Step 2 — Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a **New Application**.
3. Under **Bot**, enable **Message Content Intent**.
4. Copy your **Token**.
5. Use **OAuth2 → URL Generator** to invite the bot (Scopes: `bot`; Permissions: `Connect`, `Speak`, `Send Messages`).

---

### ⚙️ Step 3 — Configuration

Set your token as an environment variable:

```bash
export DISCORD_TOKEN="YOUR_ACTUAL_TOKEN_HERE"
# Optional: if using a proxy
export YDL_PROXY="http://yourproxy:port"
```

---

### 🏃 Step 4 — Run

```bash
pip install -r requirements.txt
python3.12 bot.py
```

---

## 🪟 Windows Guide

### 🛠 Prerequisites
- **Python 3.10+** — Download from [python.org](https://www.python.org/downloads/) (check **Add Python to PATH** during install)
- **Discord Bot Token** (with Message Content Intent enabled)

---

### 🚀 Step 1 — Install FFmpeg

1. **Download** the latest Windows build from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) (choose a Windows release, e.g. from gyan.dev).
2. **Extract** the archive (e.g. to `C:\ffmpeg`).
3. **Add to PATH:**
   - Open **Start → Search "Environment Variables"**.
   - Under **System Variables**, select `Path` → **Edit** → **New**.
   - Add the path to the `bin` folder, e.g. `C:\ffmpeg\bin`.
4. **Verify** by opening a new terminal and running:
   ```powershell
   ffmpeg -version
   ```
   Confirm it reports **version 7.x**.
5. **Update `bot.py`:** Set `FFMPEG_EXE` to `"ffmpeg"` (since it is now on your PATH), or provide the full path e.g. `C:\ffmpeg\bin\ffmpeg.exe`.

---

### 🤖 Step 2 — Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a **New Application**.
3. Under **Bot**, enable **Message Content Intent**.
4. Copy your **Token**.
5. Use **OAuth2 → URL Generator** to invite the bot (Scopes: `bot`; Permissions: `Connect`, `Speak`, `Send Messages`).

---

### ⚙️ Step 3 — Configuration

Set your token as an environment variable in PowerShell:

```powershell
$env:DISCORD_TOKEN="YOUR_ACTUAL_TOKEN_HERE"
# Optional: if using a proxy
$env:YDL_PROXY="http://yourproxy:port"
```

Or set it permanently via **System Properties → Environment Variables**.

---

### 🏃 Step 4 — Run

```powershell
pip install -r requirements.txt
python bot.py
```

---

## 🎵 Commands

| Command | Description |
|---|---|
| `!play <query>` | Play a song or YouTube URL |
| `!play <playlist>` | Queue an entire YouTube playlist |
| `!skip` | Skip the current track |
| `!pause` / `!resume` | Toggle playback |
| `!stop` | Disconnect and clear queue |
| `!queue` / `!q` | View the current queue |
| `!nowplaying` / `!np` | Show detailed track info |
| `!volume <0-100>` | Change volume |
| `!shuffle` | Randomize the queue |
| `!remove <index>` | Remove a specific song |
| `!leave` | Kick the bot from voice |

---

## ⚠️ Troubleshooting

- **403 Forbidden:** Ensure your `cookies.txt` is fresh and in the bot directory.
- **Unrecognized Option:** Ensure the bot log says `✅ FFmpeg Engine Verified: ffmpeg version 7.x`. If it shows `4.x`, check your path in `bot.py`.
- **Bot doesn't respond:** Double check that **Message Content Intent** is turned ON in the Discord Developer portal.
