from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from cogs.roles import RankSelectView
from database import db
from web import keep_alive


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("puvod.main")

COGS_DIRECTORY = Path(__file__).resolve().parent / "cogs"


class MyBot(commands.Bot):
    def __init__(self) -> None:
        # Ponecháváme původní intents kvůli logování, welcome a Revive.
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        # setup_hook proběhne právě jednou při startu této instance.
        self.add_view(RankSelectView())
        logger.info("Persistentní menu Brawl ranků bylo zaregistrováno")

        if not COGS_DIRECTORY.is_dir():
            raise RuntimeError(f"Složka cogů nebyla nalezena: {COGS_DIRECTORY}")

        cog_files = sorted(
            path for path in COGS_DIRECTORY.glob("*.py")
            if not path.name.startswith("_")
        )

        for path in cog_files:
            extension = f"cogs.{path.stem}"
            try:
                await self.load_extension(extension)
                logger.info("Načten cog: %s", extension)
            except Exception:
                # Nezamaskujeme původní chybu dalšími pokusy o spuštění.
                logger.exception("Nepodařilo se načíst cog %s", extension)
                raise

        try:
            synced = await self.tree.sync()
        except Exception:
            logger.exception("Synchronizace slash příkazů selhala")
            raise
        else:
            logger.info("Synchronizováno %d globálních slash příkazů", len(synced))

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logger.info("Bot je ONLINE jako %s (ID: %s)", self.user, self.user.id)
        try:
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="oba servery",
                )
            )
        except discord.HTTPException:
            logger.warning("Nepodařilo se změnit aktivitu bota", exc_info=True)



async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Chybí DISCORD_TOKEN v proměnných prostředí")

    try:
        await db.connect()
        logger.info("Databáze PostgreSQL / Supabase je připojená")

        # Kontextový manažer vždy korektně uzavře HTTP session klienta.
        async with MyBot() as bot:
            @bot.tree.error
            async def on_tree_error(
                interaction: discord.Interaction,
                error: app_commands.AppCommandError,
            ) -> None:
                command_name = (
                    interaction.command.qualified_name
                    if interaction.command is not None
                    else "neznámý"
                )
                original = (
                    error.original
                    if isinstance(error, app_commands.CommandInvokeError)
                    else error
                )
                logger.error(
                    "Chyba slash příkazu /%s (server=%s, uživatel=%s)",
                    command_name,
                    interaction.guild_id,
                    interaction.user.id,
                    exc_info=(type(original), original, original.__traceback__),
                )

                if isinstance(original, discord.NotFound) and original.code in (10062, 10015):
                    # Discord interakce/webhook už vypršel; další odpověď není možná.
                    return

                message = "❌ Příkaz se nepodařilo dokončit. Zkus to znovu později."
                if isinstance(original, app_commands.MissingPermissions):
                    message = "⛔ Nemáš oprávnění k použití tohoto příkazu."
                elif isinstance(original, app_commands.CommandOnCooldown):
                    message = f"⏳ Zkus to za {original.retry_after:.1f} sekundy."

                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(message, ephemeral=True)
                    else:
                        await interaction.response.send_message(message, ephemeral=True)
                except discord.HTTPException:
                    logger.warning("Odeslání chybové zprávy do Discordu se nezdařilo", exc_info=True)

            # discord.py má vlastní automatický reconnect; nový while True není potřeba.
            logger.info("Spouštím Discord bota...")
            await bot.start(token, reconnect=True)
    finally:
        if db.pool is not None:
            await db.pool.close()
            db.pool = None
            logger.info("Připojení k databázi bylo uzavřeno")


if __name__ == "__main__":
    keep_alive()
    logger.info("FastAPI health endpoint byl spuštěn")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot byl ručně zastaven")
    except Exception:
        # Proces skončí s chybou – Render může spustit novou, ČISTOU instanci.
        logger.exception("Kritické selhání při spouštění bota")
        raise
