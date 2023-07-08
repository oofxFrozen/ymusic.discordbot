# n.sannikov@innopolis.university
# i.sardanadze@innopolis.university

import urllib.request
from asyncio import run
from hashlib import md5
from queue import Queue

import xmltodict

import discord
from discord.ext import commands
from discord import FFmpegPCMAudio

import yandex_music
from yandex_music import Client

import config
from config import settings

# Initialize bot connection instance with intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='~', intents=intents)

# Initialize YMusic connection instance
ym_client = Client(config.YM_TOKEN).init()

# Data structures to store the music queue and currently played track.
music_queue = Queue(maxsize=0)
current_track: yandex_music.Track = None

# ffmpeg options to correctly stream the audio.
ffmpeg_options = {
    'options': '-vn -loglevel panic',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}


@bot.event
async def on_ready():
    """Function that is called on establishing the connection"""
    await bot.tree.sync(guild=discord.Object(id=settings['guild']))
    print(f'{bot.user} is ready to serve.')


@bot.tree.command(name='hello', description="If you're that lonely to ask a bot to say hello.",
                  guild=discord.Object(id=settings['guild']))
async def _hello(interaction):
    """/hello command"""
    await interaction.response.send_message("Hello, {}!".format(interaction.user))


@bot.tree.command(name='vc_connect', description="Joins the voice chat you're in.",
                  guild=discord.Object(id=settings['guild']))
async def _vc_connect(interaction: discord.Interaction):
    """Command that makes the bot join your voice chat."""
    vc = interaction.user.voice
    if vc:
        await vc.channel.connect()
        await interaction.response.send_message("Joined the vc.")

    else:
        await interaction.response.send_message("Cannot join your vc.")


@bot.tree.command(name='search', description="Gives a list of tracks as a result of search using the input string.",
                  guild=discord.Object(id=settings['guild']))
async def _search(interaction, search_string: str):
    """Command that gives a list of tracks as a result of search using the input string."""

    # In case of invalid request for track that does not exist on YM.
    if ym_client.search(search_string)['tracks'] is None:
        await interaction.response.send_message("Could not find anything.")
        return

    # Parsing a result string and building a response.
    track_list = ym_client.search(search_string)['tracks']['results']
    msg = ''
    n = min(5, len(track_list))
    for i in range(n):
        track = track_list[i]
        title = track['title']
        artist = track['artists'][0]['name']
        msg += str(i + 1) + f'. **{artist}** - **{title}** \n'

    await interaction.response.send_message(msg)


@bot.tree.command(name='play', description="Adds the track to the music queue.",
                  guild=discord.Object(id=settings['guild']))
async def _play(interaction, request: str):
    """Command that adds the track to the queue."""

    request_author = interaction.user

    # If bot is not in a voice channel, connect.
    if request_author.voice and len(bot.voice_clients) == 0:
        await request_author.voice.channel.connect()

    await parse_play_command(interaction, request)

    # If bot does not stream the audio currently, start the process.
    if not bot.voice_clients[0].is_playing():
        await play_the_queue()


@bot.tree.command(name='pause', description="Pauses the currently playing track.",
                  guild=discord.Object(id=settings['guild']))
async def _pause(interaction):
    """/pause command"""

    if len(bot.voice_clients) == 0:
        await interaction.response.send_message("Not connected to the voice channel at the moment.")
        return

    vc = bot.voice_clients[0]
    if not vc or not vc.is_playing():
        await interaction.response.send_message("Not playing anything at the moment.")
        return

    await interaction.response.send_message("Paused.")
    vc.pause()


@bot.tree.command(name='resume', description="Resumes the currently paused track.",
                  guild=discord.Object(id=settings['guild']))
async def _resume(interaction):
    """/resume command"""

    if len(bot.voice_clients) == 0:
        await interaction.response.send_message("Not connected to the voice channel at the moment.")
        return

    vc = bot.voice_clients[0]
    if not vc or vc.is_playing():
        await interaction.response.send_message("Already playing a track.")
        return

    await interaction.response.send_message("Resumed.")
    vc.resume()


@bot.tree.command(name='queue', description="Shows the track queue.",
                  guild=discord.Object(id=settings['guild']))
async def _queue(interaction):
    """/queue command"""
    if len(bot.voice_clients) == 0:
        await interaction.response.send_message("Not connected to the voice channel.")
        return

    global music_queue
    global current_track
    mqueue = music_queue.queue
    msg = ''

    if current_track is None:
        await interaction.response.send_message("Queue is empty.")
        return

    # Forming a string with all the tracks in the queue.
    msg += f'1. **{current_track.artists[0].name}** - **{current_track.title}** [Playing now] \n'
    n = min(4, len(mqueue))
    if len(mqueue) > 4:
        for i in range(n):
            track_info = mqueue[i][1]
            msg += str(i + 2) + f'. **{track_info.artists[0].name}** - **{track_info.title}** \n'
    msg += f'... and {len(mqueue) - 4} more tracks' if len(mqueue) > 4 else ""

    await interaction.response.send_message(msg)


@bot.tree.command(name='skip', description="Skips the currently playing track.",
                  guild=discord.Object(id=settings['guild']))
async def _skip(interaction):
    """/skip command"""
    if len(bot.voice_clients) == 0:
        await interaction.response.send_message("Not connected to the voice channel.")
        return

    global current_track
    global music_queue

    if current_track is None:
        await interaction.response.send_message("Not playing anything at the moment.")
        return

    await interaction.response.send_message("Successfully skipped the current track.")
    bot.voice_clients[0].stop()


@bot.tree.command(name='skip_number', description="Skips a number of tracks.",
                  guild=discord.Object(id=settings['guild']))
async def _skip_number(interaction, number_of_tracks: int):
    """/skip_number command"""
    if len(bot.voice_clients) == 0:
        await interaction.response.send_message("Not connected to the voice channel.")
        return

    global current_track
    global music_queue

    if current_track is None:
        await interaction.response.send_message("Not playing anything at the moment.")
        return

    n = len(music_queue.queue) + 1 if number_of_tracks >= len(music_queue.queue) else number_of_tracks

    for _ in range(n - 1):
        music_queue.get()

    await interaction.response.send_message(f"Successfully skipped {n} tracks.")
    bot.voice_clients[0].stop()


@bot.tree.command(name='skip_all', description="Skips all the tracks in the queue.",
                  guild=discord.Object(id=settings['guild']))
async def _skip_all(interaction):
    """/skip_all command"""
    if len(bot.voice_clients) == 0:
        await interaction.response.send_message("Not connected to the voice channel.")
        return

    global current_track
    global music_queue

    if current_track is None:
        interaction.response.send_message("Not playing anything at the moment.")
        return

    music_queue = Queue(maxsize=0)
    interaction.response.send_message("Successfully skipped all the tracks.")
    bot.voice_clients[0].stop()


async def parse_play_command(interaction, request: str):
    """Function that parses the play request and performs an action depending on the type of the content provided"""
    # If it is not a link, try to search for the track and add it to the queue.
    if 'music.yandex.ru' not in request:
        if ym_client.search(request)['tracks'] is None:
            await interaction.response.send_message("Couldn't find anything.")
            return
        track: yandex_music.Track = ym_client.search(request)['tracks']['results'][0]
        await interaction.response.send_message("Successfully added **{}** by **{}** to the queue."
                                                .format(track.title, track.artists[0]['name']))
        await add_track_to_queue(track)

    elif 'playlist' in request:
        ymlink = request
        user_id = ymlink.split('users/')[1].split('/playlists')[0]
        playlist_id = ymlink.split('playlists/')[1]
        playlist_info = ym_client.users_playlists(playlist_id, user_id=user_id)
        track_list = playlist_info['tracks']
        await interaction.response.send_message(
            'Successfully added *{}* tracks from **{}** *playlist* by **{}** to the queue.'
            .format(playlist_info.track_count, playlist_info.title, playlist_info.owner.name))
        await add_playlist_to_queue(track_list)

    elif 'track' in request:
        ymlink = request
        album_id = ymlink.split('album/')[1].split('/track')[0]
        track_id = ymlink.split('track/')[1]
        track_id = f'{track_id}:{album_id}'
        await add_track_to_queue(ym_client.tracks(track_id)[0])

    else:
        ymlink = request
        album_id = ymlink.split('album/')[1]
        track_list = ym_client.albums_with_tracks(album_id).volumes[0]
        album_info = ym_client.albums(album_id)[0]

        await interaction.response.send_message(
            'Successfully added *{}* tracks from **{}** *album* by **{}** to the queue.'
            .format(album_info.track_count, album_info.title, album_info.artists[0].name))
        await add_playlist_to_queue(track_list)


async def add_track_to_queue(track):
    """Puts the track to the queue."""

    track_id = f'{track["id"]}:{track["albums"][0]["id"]}'
    music_queue.put([track_id, track])

    # If bot does not stream the audio currently, start the process.
    if not bot.voice_clients[0].is_playing():
        await play_the_queue()


async def add_playlist_to_queue(track_list: list):
    """Adds the whole playlist to the queue."""

    for track in track_list:
        await add_track_to_queue(track['track'])


async def get_track_info(track_id: str):
    """Function that returns direct link to the track and info by track's id."""
    track_info = ym_client.tracks(track_id)[0]

    # Parse the download information.
    url = track_info.get_download_info()[0]['download_info_url']
    response = urllib.request.urlopen(url).read()
    tree = xmltodict.parse(response)
    link = build_direct_link(tree)
    return link, track_info


async def play_the_queue():
    """Function that starts playing the music queue."""
    global music_queue, current_track

    # In case if bot is not in voice channel / music queue is empty.
    if len(bot.voice_clients) == 0 or music_queue.empty():
        current_track = None
        return

    # Getting the voice client to stream the audio.
    vc = bot.voice_clients[0]

    # Tracks are stored as lists in format [track_id, track_info]
    track_id = music_queue.get()[0]
    link, current_track = await get_track_info(track_id)
    source = FFmpegPCMAudio(link, **ffmpeg_options, executable='ffmpeg/bin/ffmpeg.exe')
    source.read()

    # Stream the audio to voice channel and loop the process until the queue is empty.
    vc.play(source, after=lambda arg: run(play_the_queue()))


def build_direct_link(tree: dict) -> str:
    """Algorithm that builds a direct link to a track."""
    dwinfo = tree['download-info']
    host = dwinfo['host']
    path = dwinfo['path']
    ts = dwinfo['ts']
    s = dwinfo['s']
    sign = md5(('XGRlBW9FXlekgbPrRHuSiA' + path[1::] + s).encode('utf-8')).hexdigest()
    return f'https://{host}/get-mp3/{sign}/{ts}{path}'


# After adding all the commands, run the bot.
bot.run(config.settings['token'])
