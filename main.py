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


@bot.event
async def on_ready():
    """Function that is called on establishing of the connection"""
    await bot.tree.sync(guild=discord.Object(id=settings['guild']))
    print(f'{bot.user} is ready to serve.')


@bot.tree.command(name='hello', description="If you're that lonely to ask a bot to say hello.",
                  guild=discord.Object(id=settings['guild']))
async def _hello(interaction):
    """/hello command"""
    await interaction.response.send_message("Hello, {}!".format(interaction.user))


bot.run(config.settings['token'])
