from __future__ import annotations

import logging
import random
from datetime import datetime, date
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import db

logger = logging.getLogger(__name__)
PRAGUE = ZoneInfo("Europe/Prague")

DISCUSSION_TOPICS = [
    "🎮 **60 FPS na Ultra vs. 240 FPS na Low** – co by sis vybral(a) a proč?",
    "🎵 Kdybys mohl(a) poslouchat jen **3 písničky**, které by to byly?",
    "🖥️ **Klávesnice a myš vs. ovladač** – na čem se ti hraje lépe?",
    "🎧 **Sluchátka vs. reproduktory** – co používáš radši?",
    "🍕 **Havajská pizza** – geniální kombinace, nebo ne?",
    "🎬 Filmy a seriály: **dabing vs. titulky**?",
    "📱 **iOS vs. Android** – proč používáš právě svůj systém?",
    "☕ **Káva vs. energetické nápoje** – jaký nápoj máš nejradši?",
    "🌍 Kdybys mohl(a) žít kdekoliv na světě, **kam by ses přestěhoval(a)**?",
    "🕹️ **Singleplayer vs. kompetitivní multiplayer** – co tě baví víc?",
    "🎮 Jaká hra tě naposledy opravdu překvapila?",
    "🏆 Kterého herního úspěchu si nejvíc vážíš?",
    "💻 Na čem bys nejdřív upgradoval(a) svůj počítač?",
    "📺 Jaký seriál bys doporučil(a) někomu, kdo neví, co sledovat?",
    "🎵 Máš radši hudbu s výrazným textem, nebo beatem?",
    "🌙 Jsi spíš noční sova, nebo ranní ptáče?",
    "🎮 Kterou starou hru bys chtěl(a) vidět jako remake?",
    "🍔 Kdybys mohl(a) jíst jen jedno jídlo týden, co by to bylo?",
    "🐶 **Kočky vs. psi** – které zvíře máš radši?",
    "🎬 Který film má podle tebe nejlepší soundtrack?",
    "📚 Kdybys mohl(a) přes noc ovládnout jednu dovednost, kterou by sis vybral(a)?",
    "💬 Jaká je tvoje nejkontroverznější herní opinie?",
    "🎮 Která hra má podle tebe nejlepší komunitu?",
    "👾 Jakou hru by sis vzal(a) na opuštěný ostrov?",
    "🎨 Preferuješ realistickou, nebo stylizovanou herní grafiku?",
    "🕹️ Jakou první hru si pamatuješ?",
    "🏎️ Radši závodní, nebo survival hry?",
    "🧠 Umělá inteligence ve hrách – dobrá budoucnost, nebo problém?",
    "💸 Za jakou herní kosmetiku bys nikdy neutratil(a) peníze?",
    "🎤 Kterému interpretovi bys chtěl(a) jít na koncert?",
    "🎉 Jaká událost z letoška tě nejvíc potěšila?",
    "🧩 Baví tě víc strategické, nebo akční hry?",
]

GUILD_QUERY = """
    SELECT guild_id, discussion_channel_id,
           COALESCE(discussion_time, '18:00') AS discussion_time,
           discussion_last_post_date
      FROM guild_settings
     WHERE discussion_channel_id IS NOT NULL
"""


def build_topic_embed(topic: str) -> discord.Embed:
    embed = discord.Embed(
        title="💬 TÉMA DNEŠNÍ DISKUZE",
        description=f"{topic}\n\n*Přidej svůj názor a rozjeď diskuzi!*",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Puvod Bot • denní diskuze")
    return embed


class DiscussionCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.discussion_loop.start()

    def cog_unload(self) -> None:
        self.discussion_loop.cancel()

    @tasks.loop(minutes=1)
    async def discussion_loop(self) -> None:
        now = datetime.now(PRAGUE)
        today = now.date()
        try:
            guild_rows = await db.fetch(GUILD_QUERY)
        except Exception:
            logger.exception("Discussion: Supabase není dostupná")
            return
        for row in guild_rows:
            try:
                guild_id = int(row["guild_id"])
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue
                channel = guild.get_channel(int(row["discussion_channel_id"]))
                if not isinstance(channel, discord.TextChannel):
                    continue
                hhmm = row["discussion_time"] or "18:00"
                try:
                    target_h, target_m = map(int, hhmm.split(":"))
                except (ValueError, AttributeError):
                    logger.warning("Discussion: špatný čas %r v guild %s", hhmm, guild_id)
                    continue
                # Odesílej pouze v nastaveném čase, maximálně 1x denně.
                if (now.hour, now.minute) < (target_h, target_m):
                    continue
                if row["discussion_last_post_date"] == today:
                    continue

                # Atomicky si vyhradíme datum, aby dva souběžné workery neposlaly téma dvakrát.
                reserved = await db.fetchrow(
                    "UPDATE guild_settings SET discussion_last_post_date = $2 "
                    "WHERE guild_id = $1 AND discussion_last_post_date IS DISTINCT FROM $2 "
                    "RETURNING guild_id", str(guild_id), today,
                )
                if reserved is None:
                    continue
                try:
                    await channel.send(embed=build_topic_embed(random.choice(DISCUSSION_TOPICS)),
                                       allowed_mentions=discord.AllowedMentions.none())
                except (discord.HTTPException, discord.Forbidden):
                    # Při neúspěšném odeslání uvolníme zámek dne pro další pokus.
                    await db.execute(
                        "UPDATE guild_settings SET discussion_last_post_date = NULL "
                        "WHERE guild_id = $1 AND discussion_last_post_date = $2", str(guild_id), today,
                    )
                    raise
                logger.info("Discussion: téma dne %s odesláno do %s", today, guild_id)
            except Exception:
                logger.exception("Discussion: chyba v serveru %s", row["guild_id"])

    @discussion_loop.before_loop
    async def before_discussion_loop(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="topic", description="[Admin] Pošle ručně diskuzní téma do aktuálního kanálu.")
    async def send_topic(self, interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except discord.NotFound:
            return
        try:
            await interaction.channel.send(embed=build_topic_embed(random.choice(DISCUSSION_TOPICS)),
                                           allowed_mentions=discord.AllowedMentions.none())
            await interaction.followup.send("✅ Téma odesláno.", ephemeral=True)
        except discord.HTTPException:
            logger.exception("Discussion: /topic selhalo")
            await interaction.followup.send("❌ Nemůžu poslat téma, zkontroluj oprávnění.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiscussionCog(bot))
