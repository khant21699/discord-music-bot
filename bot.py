import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import subprocess
from collections import deque

# ── Config ──────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", '')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

PREFIX = "!"

# ── Local FFmpeg Engine Path ────────────────────────────────────────────────
# This points to the high-tech version you downloaded in your bot folder
FFMPEG_EXE = "/home/ubuntu/discord-music-bot/ffmpeg-7.0.2-amd64-static/ffmpeg"

# Verification Check on Startup
if not os.path.isfile(FFMPEG_EXE):
    print(f"❌ ERROR: FFmpeg not found at {FFMPEG_EXE}")
else:
    _v = subprocess.check_output([FFMPEG_EXE, "-version"]).decode().split('\n')[0]
    print(f"✅ FFmpeg Engine Verified: {_v}")

# ── Proxy & Headers ─────────────────────────────────────────────────────────
_ydl_proxy = os.getenv("YDL_PROXY")
_android_ua = "com.google.android.youtube/19.05.36 (Linux; U; Android 14; en_US; Pixel 8 Pro) gzip"

# ── Cookie config ───────────────────────────────────────────────────────────
_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
_cookies_found = os.path.isfile(_cookies_path)

# ── YT-DLP Options ──────────────────────────────────────────────────────────
YDL_OPTS = {
    "format": "139/140/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
    "nocheckcertificate": True,
    "proxy": _ydl_proxy,
    "cookiefile": _cookies_path if _cookies_found else None,
    "http_headers": {
        "User-Agent": _android_ua,
        "Accept": "*/*",
        "Connection": "keep-alive",
    },
    "extractor_args": {
        "youtube": {
            "player_client": ["android"],
            "player_skip": ["webpage", "configs"],
        }
    }
}

# ── FFmpeg Options (Refined for Version 7) ──────────────────────────────────
# We use double quotes inside the header string to prevent parsing errors
_ffmpeg_before = (
    f'-headers "User-Agent: {_android_ua}\r\nAccept: */*\r\nConnection: keep-alive\r\n" '
    f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
)

# If you get "Unrecognized option '4'", remove the '-4 ' below. 
# FFmpeg 7 usually handles IPv4/IPv6 intelligently by default.
_ffmpeg_before = "-4 " + _ffmpeg_before 

if _ydl_proxy:
    _ffmpeg_before += f' -http_proxy "{_ydl_proxy}"'

FFMPEG_OPTS = {
    "before_options": _ffmpeg_before,
    "options": "-vn -loglevel warning",
}

# ── Bot setup ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

queues: dict[int, deque] = {}
now_playing: dict[int, dict] = {}

def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]

# ── Audio fetching ───────────────────────────────────────────────────────────
async def fetch_track(query: str) -> dict | None:
    loop = asyncio.get_event_loop()
    def _extract():
        search = query if query.startswith("http") else f"ytsearch1:{query}"
        print(f"[yt-dlp] Fetching: {search}")
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            try:
                info = ydl.extract_info(search, download=False)
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries: return None
                    info = entries[0]
                return {
                    "title": info.get("title", "Unknown"),
                    "url": info.get("url"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration", 0),
                    "webpage_url": info.get("webpage_url"),
                }
            except Exception as e:
                print(f"[yt-dlp error] {e}")
                return None
    return await loop.run_in_executor(None, _extract)

def format_duration(seconds: int) -> str:
    if not seconds: return "Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

# ── Playback Logic ───────────────────────────────────────────────────────────
def play_next(ctx: commands.Context):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if not queue:
        now_playing.pop(guild_id, None)
        asyncio.run_coroutine_threadsafe(ctx.send("✅ Queue finished."), bot.loop)
        return

    vc = ctx.voice_client
    if vc is None or not vc.is_connected(): return

    track = queue.popleft()
    now_playing[guild_id] = track
    print(f"[playback] Starting: {track['title']}")

    # USING THE NEW ENGINE HERE
    source = discord.FFmpegPCMAudio(
        track["url"],
        executable=FFMPEG_EXE,
        before_options=FFMPEG_OPTS["before_options"],
        options=FFMPEG_OPTS["options"],
    )
    source = discord.PCMVolumeTransformer(source, volume=0.8)

    def after(error):
        if error: print(f"[playback error] {error}")
        play_next(ctx)

    vc.play(source, after=after)

    embed = discord.Embed(title="🎵 Now Playing", description=f"**{track['title']}**", color=0xFF0000)
    asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), bot.loop)

# ── Commands ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first!")

    msg = await ctx.send("🔍 Searching...")
    track = await fetch_track(query)

    if not track:
        return await msg.edit(content="❌ Could not find that song.")

    track["requester"] = ctx.author
    
    # Ensure Voice Connection
    vc = ctx.voice_client
    if vc is None:
        vc = await ctx.author.voice.channel.connect(self_deaf=True)
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    get_queue(ctx.guild.id).append(track)
    await msg.edit(content=f"✅ Queued: **{track['title']}**")

    if not vc.is_playing() and not vc.is_paused():
        play_next(ctx)

@bot.command()
async def stop(ctx):
    queues.pop(ctx.guild.id, None)
    if ctx.voice_client: await ctx.voice_client.disconnect()
    await ctx.send("⏹️ Stopped.")

if __name__ == "__main__":
    bot.run(TOKEN)