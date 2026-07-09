import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv("a.env")
discord_token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=None, intents=intents)


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


async def load_cogs():
    await bot.load_extension("cogs.banking")
    await bot.load_extension("cogs.others")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(discord_token)


if __name__ == "__main__":
    asyncio.run(main())
