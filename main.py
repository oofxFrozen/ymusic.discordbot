# n.sannikov@innopolis.university
# i.sardanadze@innopolis.university

import os
import urllib.request
from asyncio import run
from hashlib import md5
from queue import Queue

import xmltodict

import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord import app_commands

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

    if ym_client.search(request)['tracks'] is None:
        await interaction.response.send_message("Couldn't find anything.")
        return

    track: yandex_music.Track = ym_client.search(request)['tracks']['results'][0]

    await interaction.response.send_message("Successfully added **{}** by **{}** to the queue."
                                            .format(track.title, track.artists[0]['name']))

    await add_track_to_queue(track)

    # If bot is not in a voice channel, connect.
    if request_author.voice and len(bot.voice_clients) == 0:
        await request_author.voice.channel.connect()

    # If bot does not stream the audio currently, start the process.
    if not bot.voice_clients[0].is_playing():
        await play_the_queue(interaction)


async def add_track_to_queue(track):
    """Function that puts the track to the queue."""
    track_id = f'{track["id"]}:{track["albums"][0]["id"]}'
    link, track_info = await get_track_info(track_id)
    source = FFmpegPCMAudio(link, **ffmpeg_options, executable='ffmpeg/bin/ffmpeg.exe')
    music_queue.put([source, track_info])


async def get_track_info(track_id: str):
    """Function that returns direct link to the track and info by track's id."""
    track_info = ym_client.tracks(track_id)[0]

    # Parse the download information.
    url = track_info.get_download_info()[0]['download_info_url']
    response = urllib.request.urlopen(url).read()
    tree = xmltodict.parse(response)
    link = build_direct_link(tree)
    return link, track_info


async def play_the_queue(interaction: discord.Interaction):
    """Function that starts playing the music queue."""
    global music_queue, current_track

    # In case if bot is not in voice channel / music queue is empty.
    if len(bot.voice_clients) == 0 or music_queue.empty():
        current_track = None
        return

    # Getting the voice client to stream the audio.
    vc = bot.voice_clients[0]

    # Tracks are stored as lists in format [<source of the audio>, <track information>]
    track = music_queue.get()
    track[0].read()
    current_track = track[1]

    # Stream the audio to voice channel and loop the process until the queue is empty.
    vc.play(track[0], after=lambda arg: run(play_the_queue(interaction)))


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
