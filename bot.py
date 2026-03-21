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

# ── YT-DLP options ──────────────────────────────────────────────────────────
_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
_ydl_proxy = os.getenv("YDL_PROXY")  # e.g. http://user:pass@host:port

_cookies_found = os.path.exists(_cookies_path)
print(f"[config] Proxy  : {_ydl_proxy or 'NOT SET'}")
print(f"[config] Cookies: {_cookies_path if _cookies_found else 'NOT FOUND'}")

YDL_OPTS = {
    "format": "bestaudio[ext=webm]/bestaudio/best",
    "quiet": False,
    "no_warnings": False,
    "noplaylist": True,
    "skip_download": True,
    "geo_bypass": True,
    "socket_timeout": 30,
    "extractor_retries": 3,
    "cookiefile": _cookies_path if _cookies_found else None,
    "extractor_args": {"youtube": {"player_client": ["web"]}},
    "proxy": _ydl_proxy,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
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

queues: dict = {}
now_playing: dict = {}

def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]


# ── Audio fetching ───────────────────────────────────────────────────────────
async def fetch_track(query: str):
    loop = asyncio.get_event_loop()

    def _extract():
        search = query if query.startswith("http") else f"ytsearch1:{query}"
        print(f"[yt-dlp] Fetching: {search}")
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            try:
                info = ydl.extract_info(search, download=False)
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        print("[yt-dlp] No entries found")
                        return None
                    info = entries[0]
                url = info.get("url")
                title = info.get("title", "Unknown")
                print(f"[yt-dlp] Got: {title} | URL ok: {bool(url)}")
                return {
                    "title": title,
                    "url": url,
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

# ── Audio fetching (Updated for Playlists) ───────────────────────────────────
async def fetch_tracks(query: str) -> list:
    loop = asyncio.get_event_loop()
    def _extract():
        # Handle search vs URL
        search = query if query.startswith("http") else f"ytsearch1:{query}"
        # We allow playlists here
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

async def ensure_voice(ctx: commands.Context):
    """Return a valid connected VoiceClient, cleaning up any stale connection first."""
    vc = ctx.voice_client
    if vc is None:
        vc = await ctx.author.voice.channel.connect(self_deaf=True)
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    queue = get_queue(ctx.guild.id)
    for t in tracks:
        t["requester"] = ctx.author
        queue.append(t)

    if len(tracks) > 1:
        await msg.edit(content=f"✅ Added **{len(tracks)}** songs from playlist to queue.")
    else:
        await msg.edit(content=f"✅ Queued: **{tracks[0]['title']}**")

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
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    await ctx.send("⏹️ Stopped and cleared queue.")

@bot.command(aliases=["q"])
async def queue(ctx):
    q = get_queue(ctx.guild.id)
    current = now_playing.get(ctx.guild.id)
    if not q and not current:
        return await ctx.send("📭 Queue is empty.")
    
    desc = ""
    if current:
        desc += f"**Now Playing:** {current['title']}\n\n"
    
    if q:
        desc += "**Up Next:**\n"
        for i, t in enumerate(list(q)[:10], 1):
            desc += f"`{i}.` {t['title']}\n"
        if len(q) > 10:
            desc += f"*...and {len(q)-10} more*"

    embed = discord.Embed(title="🎶 Current Queue", description=desc, color=0xFF0000)
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
        else:
            await ctx.send("❌ Volume must be between 0 and 100.")

@bot.command()
async def shuffle(ctx):
    q = get_queue(ctx.guild.id)
    if len(q) < 2: return await ctx.send("❌ Not enough songs to shuffle.")
    shuffled = list(q)
    random.shuffle(shuffled)
    queues[ctx.guild.id] = deque(shuffled)
    await ctx.send("🔀 Queue shuffled!")

@bot.command()
async def remove(ctx, index: int):
    q = get_queue(ctx.guild.id)
    if 1 <= index <= len(q):
        removed = list(q)
        item = removed.pop(index - 1)
        queues[ctx.guild.id] = deque(removed)
        await ctx.send(f"🗑️ Removed: **{item['title']}**")
    else:
        await ctx.send("❌ Invalid index.")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Bye!")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🎵 Music Bot Help", color=0xFF0000)
    cmds = [
        ("!play <song/URL>", "Play song or playlist"),
        ("!skip", "Skip current song"),
        ("!pause/!resume", "Pause or resume"),
        ("!stop", "Stop and clear queue"),
        ("!queue/!q", "Show queue"),
        ("!nowplaying/!np", "Show current song"),
        ("!volume <0-100>", "Adjust volume"),
        ("!shuffle", "Shuffle queue"),
        ("!remove <#>", "Remove song at index"),
        ("!leave", "Disconnect bot")
    ]
    for n, d in cmds: embed.add_field(name=n, value=d, inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(TOKEN)