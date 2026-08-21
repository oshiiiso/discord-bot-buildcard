"""BuildCard-Bot 本体。"""

import discord
from discord.ext import commands

from config import GUILD_ID
from logging_config import get_logger

logger = get_logger(__name__)

intents = discord.Intents.default()


class BuildCardBot(commands.Bot):
    """UID からビルドカードを出す Bot。"""

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.build")
        logger.info("Build Cog をロードしました")

        if GUILD_ID is not None:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("スラッシュコマンドをサーバー(ID: %s)に%d件同期しました", GUILD_ID, len(synced))
        else:
            synced = await self.tree.sync()
            logger.info("スラッシュコマンドをグローバルに%d件同期しました", len(synced))


bot = BuildCardBot(command_prefix=commands.when_mentioned, intents=intents)


@bot.event
async def on_ready() -> None:
    logger.info("%s としてログインしました", bot.user)
