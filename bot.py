import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import subprocess
import random
from collections import deque

# ── Config ──────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", '')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

PREFIX = "!"

# ── Local FFmpeg Engine Path ────────────────────────────────────────────────
FFMPEG_EXE = "/home/ubuntu/discord-music-bot/ffmpeg-7.0.2-amd64-static/ffmpeg"

# Verification Check on Startup
if os.path.isfile(FFMPEG_EXE):
    try:
        _v = subprocess.check_output([FFMPEG_EXE, "-version"]).decode().split('\n')[0]
        print(f"✅ FFmpeg Engine Verified: {_v}")
    except: pass

# ── Proxy & Headers ─────────────────────────────────────────────────────────
_ydl_proxy = os.getenv("YDL_PROXY")
_android_ua = "com.google.android.youtube/19.05.36 (Linux; U; Android 14; en_US; Pixel 8 Pro) gzip"
_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

# ── YT-DLP Options (Optimized for Playlists & Extraction Fixes) ─────────────
# ── Updated YT-DLP Options ──────────────────────────────────────────────────
YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "proxy": _ydl_proxy,
    "cookiefile": _cookies_path if os.path.isfile(_cookies_path) else None,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    "extractor_args": {
        "youtube": {
            # Use 'ios' specifically, as it is currently the most successful at bypassing bot detection
            "player_client": ["ios"], 
            "player_skip": ["webpage", "configs"],
        }
    }
}

# ── FFmpeg Options ──────────────────────────────────────────────────────────
_ffmpeg_before = (
    f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
    f'-headers "User-Agent: {_android_ua}\r\n"'
)
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

def format_duration(seconds: int) -> str:
    if not seconds: return "Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

# ── Audio fetching ───────────────────────────────────────────────────────────
async def fetch_tracks(query: str) -> list:
    loop = asyncio.get_event_loop()
    def _extract():
        search = query if query.startswith("http") else f"ytsearch1:{query}"
        opts = YDL_OPTS.copy()
        opts["noplaylist"] = False 
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(search, download=False)
                tracks = []
                if "entries" in info:
                    for entry in info["entries"]:
                        if entry:
                            tracks.append({
                                "title": entry.get("title", "Unknown"),
                                "url": entry.get("url"),
                                "thumbnail": entry.get("thumbnail"),
                                "duration": entry.get("duration", 0),
                                "webpage_url": entry.get("webpage_url"),
                            })
                    return tracks
                return [{
                    "title": info.get("title", "Unknown"),
                    "url": info.get("url"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration", 0),
                    "webpage_url": info.get("webpage_url"),
                }]
            except Exception as e:
                print(f"[yt-dlp error] {e}")
                return []
    return await loop.run_in_executor(None, _extract)

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

# ── Commands ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ Join a voice channel first!")

    msg = await ctx.send("🔍 Processing...")
    tracks = await fetch_tracks(query)

    if not tracks:
        return await msg.edit(content="❌ YouTube error. Run `pip install -U --pre yt-dlp` on your server.")

    vc = ctx.voice_client
    if vc is None:
        vc = await ctx.author.voice.channel.connect(self_deaf=True)
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    queue = get_queue(ctx.guild.id)
    for t in tracks:
        t["requester"] = ctx.author
        queue.append(t)

    await msg.edit(content=f"✅ Queued **{len(tracks)}** song(s): **{tracks[0]['title']}**")
    if not vc.is_playing() and not vc.is_paused():
        play_next(ctx)

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped!")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed.")

@bot.command()
async def stop(ctx):
    get_queue(ctx.guild.id).clear()
    now_playing.pop(ctx.guild.id, None)
    if ctx.voice_client: await ctx.voice_client.disconnect()
    await ctx.send("⏹️ Stopped.")

@bot.command(aliases=["q"])
async def queue(ctx):
    q = get_queue(ctx.guild.id)
    current = now_playing.get(ctx.guild.id)
    if not q and not current: return await ctx.send("📭 Queue is empty.")
    
    desc = f"**Now Playing:** {current['title']}\n\n**Up Next:**\n" if current else ""
    for i, t in enumerate(list(q)[:10], 1):
        desc += f"`{i}.` {t['title']}\n"
    
    embed = discord.Embed(title="🎶 Current Queue", description=desc or "Queue is empty.", color=0xFF0000)
    await ctx.send(embed=embed)

@bot.command(aliases=["np"])
async def nowplaying(ctx):
    current = now_playing.get(ctx.guild.id)
    if not current: return await ctx.send("❌ Nothing is playing.")
    embed = discord.Embed(title="🎵 Now Playing", description=f"**{current['title']}**", color=0xFF0000)
    if current['thumbnail']: embed.set_thumbnail(url=current['thumbnail'])
    embed.add_field(name="Duration", value=format_duration(current['duration']))
    embed.add_field(name="Requested By", value=current['requester'].mention)
    await ctx.send(embed=embed)

@bot.command()
async def volume(ctx, vol: int):
    if ctx.voice_client and ctx.voice_client.source:
        if 0 <= vol <= 100:
            ctx.voice_client.source.volume = vol / 100
            await ctx.send(f"🔊 Volume set to **{vol}%**")

@bot.command()
async def shuffle(ctx):
    q = get_queue(ctx.guild.id)
    if len(q) < 2: return await ctx.send("❌ Need more songs.")
    shuffled = list(q)
    random.shuffle(shuffled)
    queues[ctx.guild.id] = deque(shuffled)
    await ctx.send("🔀 Shuffled!")

@bot.command()
async def remove(ctx, index: int):
    q = get_queue(ctx.guild.id)
    if 1 <= index <= len(q):
        removed = list(q)
        item = removed.pop(index - 1)
        queues[ctx.guild.id] = deque(removed)
        await ctx.send(f"🗑️ Removed: **{item['title']}**")

@bot.command()
async def leave(ctx):
    if ctx.voice_client: await ctx.voice_client.disconnect()
    await ctx.send("👋 Bye!")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎵 Music Help", description="`!play`, `!skip`, `!pause`, `!resume`, `!stop`, `!queue`, `!nowplaying`, `!volume`, `!shuffle`, `!remove`, `!leave`", color=0xFF0000)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(TOKEN)