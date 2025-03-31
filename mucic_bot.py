import os
import re
import asyncio
import logging
import subprocess

import discord
from discord.ext import commands
import yt_dlp

# Import the token from the tokenss module
from tokenss import token as TOKEN



# ---------- Configuration ----------

PREFIX = '!'
CACHE_DIR = 'cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'outtmpl': f'{CACHE_DIR}/%(id)s.%(ext)s',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -loglevel panic -bufsize 64k'
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
song_queue = []
in_play = False
async def ensure_voice(ctx):
    """Ensure the bot is in the same voice channel as the invoker."""
    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to use this command.")
        return None
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)
    return ctx.voice_client

async def download_and_get_info(query: str):
    """
    Download a song or, if query is not a URL, search for the top result.
    Returns the info dictionary with an added 'file_path' key.
    """
    def run_ydl(q):
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            return ydl.extract_info(q, download=False)

    if re.match(r'https?://', query):
        info = await asyncio.to_thread(run_ydl, query)
    else:
        # Search and return the top result.
        info = await asyncio.to_thread(run_ydl, f"ytsearch:{query}")
        if 'entries' in info:
            info = info['entries'][0]
    return info

async def search_youtube(query: str):
    """Search YouTube and return up to 10 results (without downloading)."""
    search_options = YDL_OPTIONS.copy()
    search_options.update({'skip_download': True})
    with yt_dlp.YoutubeDL(search_options) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, f"ytsearch10:{query}")
    return info.get('entries', [])

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")


async def add_to_queue(ctx, query: str):
    """Add a song to the queue."""
    info = await download_and_get_info(query)
    song_queue.append(info)
    await ctx.send(f"Added to queue: {info.get('title')}")

def stream_audio(url):
    """Extract a direct streamable URL using yt-dlp."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url']  # Get direct audio stream URL
async def play_next(ctx):
    """Play the next song in the queue."""
    global in_play
    if song_queue:
        info = song_queue.pop(0)  # Get the first song in the queue
        stream_url = stream_audio(info['webpage_url'])  # Extract streamable URL
        source = discord.FFmpegOpusAudio(stream_url, **FFMPEG_OPTIONS)

        ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f"Now playing: {info.get('title')}")
    else:
        in_play = False
        await ctx.send("Queue is empty.")




@bot.command(name='play')
async def play(ctx, *, query: str):
    global in_play
    voice = await ensure_voice(ctx)
    if voice is None:
        return
    await ctx.send("Processing your request...")

    await add_to_queue(ctx, query)
    
    if not in_play:
        in_play = True
        await play_next(ctx)

@bot.command(name='skip')
async def skip(ctx):
    """Skip the current song."""
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await play_next(ctx)
    else:
        await ctx.send("No song is currently playing.")
@bot.command(name='remove')
async def remove(ctx, index: int):
    """Remove a song from the queue."""
    if 0 < index <= len(song_queue):
        removed_song = song_queue.pop(index - 1)
        await ctx.send(f"Removed from queue: {removed_song['title']}")
    else:
        await ctx.send("Invalid index. Please provide a valid number.")

@bot.command(name='stop')
async def stop(ctx):
    """Stop the current song and clear the queue."""
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    song_queue.clear()
    await ctx.send("Stopped playback and cleared the queue.")

@bot.command(name='pause')
async def pause(ctx):
    """Pause the current song."""
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused the current song.")
    else:
        await ctx.send("No song is currently playing.")

@bot.command(name='resume')
async def resume(ctx):
    """Resume the paused song."""
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed the current song.")
    else:
        await ctx.send("The current song is not paused.")

@bot.command(name='join')
async def join(ctx):
    """Join the voice channel."""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
            await ctx.send(f"Joined {channel.name}.")
        else:
            await ctx.voice_client.move_to(channel)
            await ctx.send(f"Moved to {channel.name}.")
    else:
        await ctx.send("You must be in a voice channel to use this command.")

@bot.command(name='leave')
async def leave(ctx):
    """Leave the voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")
loop = False        
@bot.command(name='loop')
async def loop(ctx):
    global loop
    """Loop the current song."""
    if ctx.voice_client and ctx.voice_client.is_playing() and not loop:
        loop = True
        ctx.voice_client.loop = True
        await ctx.send("Looping the current song.")
    elif ctx.voice_client and ctx.voice_client.is_playing() and loop:
        loop = False
        ctx.voice_client.loop = False
        await ctx.send("Stopped looping the current song.")
    else:
        await ctx.send("No song is currently playing.")

@bot.command(name='clear')
async def clear(ctx):
    """Clear the song queue."""
    global song_queue
    song_queue.clear()
    await ctx.send("Cleared the song queue.")


        

@bot.command(name='search')
async def search(ctx, *, query: str):
    global in_play
    """Search for a song on YouTube."""
    await ctx.send("Searching...")
    results = await search_youtube(query)
    if not results:
        await ctx.send("No results found.")
        return

    embed = discord.Embed(title="Search Results", color=discord.Color.blue())
    for i, entry in enumerate(results):
        embed.add_field(name=f"{i+1}. {entry['title']}", value=f"[Link]({entry['webpage_url']})", inline=False)
        if i >=9:
            break
    
    embed.set_footer(text="Type the number of the song you want to play (1-10).")
    await ctx.send(embed=embed)

    # Wait for user input
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
    # Wait for the user to respond with a number
    try:
        msg = await bot.wait_for('message', check=check, timeout=30)
        choice = int(msg.content) - 1
        if choice < 0 or choice >= len(results):
            return await ctx.send("Invalid selection. Please try again.")

        selected = results[choice]
        info = await download_and_get_info(selected['webpage_url'])
        await add_to_queue(ctx, info['webpage_url'])

        if not in_play:
            in_play = True
            await play_next(ctx)
        else:
            await ctx.send(f"Added to queue: {info.get('title')}")


    except asyncio.TimeoutError:
        await ctx.send("Selection timed out. Please try again.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


@bot.command(name='queue')
async def queue(ctx):
    """Show the current song queue."""
    if not song_queue:
        await ctx.send("The queue is empty.")
        return

    queue_list = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(song_queue)])
    await ctx.send(f"Current queue:\n{queue_list}")

@bot.command(name='play_list')
async def play_playlist(ctx,*,index: int):
    """Play a song from the playlist."""
    if 0 < index <= len(song_queue):
        song = song_queue[index - 1]
        await play(ctx, query=song['webpage_url'])
    else:
        await ctx.send("Invalid index. Please provide a valid number.")
@bot.command(name='current_volume')
async def current_volume(ctx):
    """Check the current volume of the bot."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        volume = ctx.voice_client.source.volume * 100
        await ctx.send(f"Current volume: {volume}%")
    else:
        await ctx.send("No song is currently playing.")


@bot.command(name='volume')
async def volume(ctx, volume: int):
    """Set the volume of the bot."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.source.volume = volume / 100.0
        await ctx.send(f"Volume set to {volume}%")
    else:
        await ctx.send("No song is currently playing.")


bot.run(TOKEN)