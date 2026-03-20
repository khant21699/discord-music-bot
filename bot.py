import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
from collections import deque

# ── Config ──────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN", '')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

PREFIX = "!"

# ── YT-DLP options ──────────────────────────────────────────────────────────
_cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

YDL_OPTS = {
    "format": "bestaudio[ext=webm]/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
    "geo_bypass": True,
    "socket_timeout": 30,
    "extractor_retries": 3,
    "cookiefile": _cookies_path if os.path.exists(_cookies_path) else None,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin",
    "options": "-vn",
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
    if not seconds:
        return "Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ── Playback ─────────────────────────────────────────────────────────────────
def play_next(ctx: commands.Context):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if not queue:
        now_playing.pop(guild_id, None)
        asyncio.run_coroutine_threadsafe(
            ctx.send("✅ Queue finished. Use `!play` to add more songs!"),
            bot.loop,
        )
        return

    vc = ctx.voice_client
    if vc is None or not vc.is_connected():
        now_playing.pop(guild_id, None)
        print("[playback] Voice client disconnected — cannot play next track.")
        asyncio.run_coroutine_threadsafe(
            ctx.send("❌ Lost voice connection. Rejoin a voice channel and use `!play` to start again."),
            bot.loop,
        )
        return

    track = queue.popleft()
    now_playing[guild_id] = track

    print(f"[playback] Playing: {track['title']} | URL: {track['url'][:80]}...")

    source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS)
    source = discord.PCMVolumeTransformer(source, volume=0.8)

    def after(error):
        if error:
            print(f"[playback error] {error}")
        play_next(ctx)

    vc.play(source, after=after)

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{track['title']}]({track.get('webpage_url', '')})**",
        color=0xFF0000,
    )
    embed.add_field(name="Duration", value=format_duration(track.get("duration", 0)), inline=True)
    embed.add_field(name="Requested by", value=track["requester"].mention, inline=True)
    if track.get("thumbnail"):
        embed.set_thumbnail(url=track["thumbnail"])

    asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), bot.loop)


# ── Commands ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    # Clear any stale voice sessions left over from a previous deployment
    for guild in bot.guilds:
        try:
            await guild.change_voice_state(channel=None)
        except Exception:
            pass
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play <song>"
    ))


async def ensure_voice(ctx: commands.Context):
    """Return a valid connected VoiceClient, cleaning up any stale connection first."""
    vc = ctx.voice_client

    # Force-disconnect any broken/disconnected voice client so connect() won't throw
    if vc is not None and not vc.is_connected():
        try:
            await vc.disconnect(force=True)
        except Exception:
            pass
        await asyncio.sleep(0.5)
        vc = ctx.voice_client  # re-read after disconnect

    if vc is None:
        vc = await ctx.author.voice.channel.connect(self_deaf=True)
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    return vc


@bot.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    if not ctx.author.voice:
        return await ctx.send("❌ You must be in a voice channel first!")

    # Show feedback immediately — before the slow operations
    msg = await ctx.send("🔍 Searching...")

    track = await fetch_track(query)

    if track is None or not track.get("url"):
        return await msg.edit(content="❌ Could not find or stream that song. Try a YouTube URL directly.")

    track["requester"] = ctx.author

    # Connect (or reconnect) to voice after the fetch so we hold the connection as briefly as possible
    if not ctx.author.voice:
        return await msg.edit(content="❌ You left the voice channel before the song was ready.")

    try:
        vc = await ensure_voice(ctx)
    except Exception as e:
        return await msg.edit(content=f"❌ Could not connect to voice: {e}")

    queue = get_queue(ctx.guild.id)
    queue.append(track)
    await msg.edit(content=f"✅ Queued: **{track['title']}**")

    if not vc.is_playing() and not vc.is_paused():
        play_next(ctx)


@bot.command(name="skip", aliases=["s"])
async def skip(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send("❌ Nothing is playing.")
    vc.stop()
    await ctx.send("⏭️ Skipped!")


@bot.command(name="pause")
async def pause(ctx: commands.Context):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸️ Paused.")
    else:
        await ctx.send("❌ Nothing is playing.")


@bot.command(name="resume", aliases=["r"])
async def resume(ctx: commands.Context):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("❌ Nothing is paused.")


@bot.command(name="stop")
async def stop(ctx: commands.Context):
    guild_id = ctx.guild.id
    queues.pop(guild_id, None)
    now_playing.pop(guild_id, None)
    vc = ctx.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
    await ctx.send("⏹️ Stopped and disconnected.")


@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx: commands.Context):
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)
    current = now_playing.get(guild_id)

    if not current and not queue:
        return await ctx.send("📭 Queue is empty.")

    embed = discord.Embed(title="🎶 Music Queue", color=0xFF0000)

    if current:
        embed.add_field(
            name="▶️ Now Playing",
            value=f"**{current['title']}** — {format_duration(current.get('duration', 0))}",
            inline=False,
        )

    if queue:
        lines = []
        for i, t in enumerate(list(queue)[:10], 1):
            lines.append(f"`{i}.` {t['title']} — {format_duration(t.get('duration', 0))}")
        if len(queue) > 10:
            lines.append(f"*...and {len(queue) - 10} more*")
        embed.add_field(name=f"📋 Up Next ({len(queue)} tracks)", value="\n".join(lines), inline=False)

    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np"])
async def nowplaying(ctx: commands.Context):
    current = now_playing.get(ctx.guild.id)
    if not current:
        return await ctx.send("❌ Nothing is playing.")
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{current['title']}]({current.get('webpage_url', '')})**",
        color=0xFF0000,
    )
    embed.add_field(name="Duration", value=format_duration(current.get("duration", 0)), inline=True)
    embed.add_field(name="Requested by", value=current["requester"].mention, inline=True)
    if current.get("thumbnail"):
        embed.set_thumbnail(url=current["thumbnail"])
    await ctx.send(embed=embed)


@bot.command(name="volume", aliases=["vol"])
async def volume(ctx: commands.Context, vol: int):
    vc = ctx.voice_client
    if not vc or not vc.source:
        return await ctx.send("❌ Nothing is playing.")
    if not 0 <= vol <= 100:
        return await ctx.send("❌ Volume must be between 0 and 100.")
    vc.source.volume = vol / 100
    await ctx.send(f"🔊 Volume set to **{vol}%**")


@bot.command(name="shuffle")
async def shuffle(ctx: commands.Context):
    import random
    queue = get_queue(ctx.guild.id)
    if len(queue) < 2:
        return await ctx.send("❌ Need at least 2 songs to shuffle.")
    items = list(queue)
    random.shuffle(items)
    queues[ctx.guild.id] = deque(items)
    await ctx.send("🔀 Queue shuffled!")


@bot.command(name="remove")
async def remove(ctx: commands.Context, index: int):
    queue = get_queue(ctx.guild.id)
    if not queue:
        return await ctx.send("❌ Queue is empty.")
    if not 1 <= index <= len(queue):
        return await ctx.send(f"❌ Index must be between 1 and {len(queue)}.")
    items = list(queue)
    removed = items.pop(index - 1)
    queues[ctx.guild.id] = deque(items)
    await ctx.send(f"🗑️ Removed **{removed['title']}** from the queue.")


@bot.command(name="leave", aliases=["disconnect", "dc"])
async def leave(ctx: commands.Context):
    vc = ctx.voice_client
    if vc:
        queues.pop(ctx.guild.id, None)
        now_playing.pop(ctx.guild.id, None)
        await vc.disconnect()
        await ctx.send("👋 Disconnected.")
    else:
        await ctx.send("❌ Not in a voice channel.")


@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = discord.Embed(title="🎵 Music Bot Commands", description="Prefix: `!`", color=0xFF0000)
    commands_list = [
        ("!play <song/URL>", "Play a song by name or YouTube URL"),
        ("!skip / !s", "Skip the current song"),
        ("!pause", "Pause playback"),
        ("!resume / !r", "Resume playback"),
        ("!stop", "Stop and disconnect"),
        ("!queue / !q", "Show the queue"),
        ("!nowplaying / !np", "Show current song"),
        ("!volume <0-100>", "Set volume"),
        ("!shuffle", "Shuffle the queue"),
        ("!remove <#>", "Remove song from queue"),
        ("!leave", "Disconnect bot"),
    ]
    for cmd, desc in commands_list:
        embed.add_field(name=f"`{cmd}`", value=desc, inline=False)
    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing argument. Use `!help` for usage.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"⚠️ Error: {error}")
        print(f"[Error] {error}")


if __name__ == "__main__":
    bot.run(TOKEN)