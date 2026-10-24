from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, date
from time import monotonic
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import db, get_setting, get_top_users_daily, get_top_users_lifetime, get_all_guilds_with_counting, update_setting


logger = logging.getLogger(__name__)
PRAGUE = ZoneInfo("Europe/Prague")
CACHE_TTL_SECONDS = 120.0
POSTGRES_INT_MAX = 2_147_483_647
NUMBER_PATTERN = re.compile(r"[0-9]{1,10}\Z")
MEDALS = ("🥇", "🥈", "🥉")


@dataclass(slots=True, frozen=True)
class CountResult:
    status: str
    expected: int = 0
    number: int = 0
    tokens: int = 0
    gems: int = 0
    reset: bool = False


def number_display(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def leaderboard_lines(rows: list | tuple, *, max_players: int = 10) -> str:
    """Podporuje asyncpg.Record i běžné dvojice (user_id, count)."""
    lines = []
    for index, row in enumerate(rows[:max_players]):
        user_id, count = row[0], int(row[1])
        prefix = MEDALS[index] if index < len(MEDALS) else f"**{index + 1}.**"
        lines.append(f"{prefix} <@{user_id}>  ·  **{number_display(count)}**")
    return "\n".join(lines) if lines else "*Zatím žádné záznamy. První místo čeká! ✨*"


class Counting(commands.GroupCog, name="counting", description="Počítání, statistiky a žebříčky"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # První vrstva proti pořadovým závodům v jedné instanci.
        self._guild_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Kanál se z DB čte jen při prvním numerickém příspěvku / po vypršení TTL.
        self._channel_cache: dict[int, tuple[int | None, float]] = {}
        # Druhá vrstva: řádkové zámky PostgreSQL uvnitř transakcí.
        # V paměti sledujeme nedávné message ID pro ochranu před duplicitní událostí.
        self._recent_message_ids: deque[int] = deque()
        self._recent_message_set: set[int] = set()
        self._daily_finished: set[tuple[int, date]] = set()
        self._daily_announced: set[tuple[int, date]] = set()

    async def cog_load(self) -> None:
        # db.connect() probíhá v main.py před bot.start(). Přidáme 1 sloupec,
        # na který se nevztahuje whitelist get_setting/update_setting.
        # Čteme a zapisujeme jej přes parametrizované SQL, nikoli f-stringy.
        await db.execute(
            "ALTER TABLE guild_settings "
            "ADD COLUMN IF NOT EXISTS counting_last_report_date DATE"
        )
        self.check_topka_time.start()
        logger.info("Counting cog je připravený; denní topka používá Europe/Prague")

    def cog_unload(self) -> None:
        self.check_topka_time.cancel()

    @staticmethod
    async def _defer(interaction: discord.Interaction, *, ephemeral: bool = False) -> bool:
        try:
            await interaction.response.defer(thinking=True, ephemeral=ephemeral)
            return True
        except discord.NotFound as exc:
            if exc.code == 10062:
                logger.warning("Interakce %s vypršela před potvrzením", interaction.id)
                return False
            raise

    @staticmethod
    async def _send_error(interaction: discord.Interaction, message: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException as exc:
            logger.warning("Nelze odeslat chybovou odpověď interakce %s: %s", interaction.id, exc)

    def _cache_channel(self, guild_id: int, channel_id: int | None) -> None:
        self._channel_cache[guild_id] = (channel_id, monotonic() + CACHE_TTL_SECONDS)

    async def _get_counting_channel(self, guild_id: int) -> int | None:
        cached = self._channel_cache.get(guild_id)
        if cached is not None and monotonic() < cached[1]:
            return cached[0]
        value = await get_setting(guild_id, "counting_channel_id")
        channel_id = int(value) if value else None
        self._cache_channel(guild_id, channel_id)
        return channel_id

    @staticmethod
    def _base_embed(title: str, *, description: str = "", color: discord.Color | None = None) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=color or discord.Color.blurple(),
            timestamp=datetime.now(PRAGUE),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ADMINISTRACE
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_channel", description="Nastaví Counting kanál, počáteční číslo a reset po chybě.")
    @app_commands.describe(
        channel="Textový kanál, ve kterém se bude počítat",
        výchozí_číslo="Již dosažené číslo; další bude o 1 vyšší",
        reset_po_chybe="Při špatném čísle resetovat počítání na nulu?",
    )
    async def setup_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        výchozí_číslo: app_commands.Range[int, 0, 2_147_483_646] = 0,
        reset_po_chybe: bool = True,
    ):
        if not await self._defer(interaction, ephemeral=True):
            return
        guild_id = interaction.guild_id
        try:
            async with self._guild_locks[guild_id]:
                async with db.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            "INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
                            str(guild_id),
                        )
                        await conn.execute(
                            """UPDATE guild_settings
                               SET counting_channel_id=$2, reset_on_fail=$3,
                                   current_number=$4, current_streak=0, last_user_id=NULL
                               WHERE guild_id=$1""",
                            str(guild_id), channel.id, int(reset_po_chybe), výchozí_číslo,
                        )
                self._cache_channel(guild_id, channel.id)
        except Exception:
            logger.exception("Chyba při konfiguraci Countingu pro guild %s", guild_id)
            await self._send_error(interaction, "❌ Nepodařilo se uložit Counting nastavení do Supabase.")
            return

        embed = self._base_embed("✅ Counting byl nastaven", color=discord.Color.green())
        embed.add_field(name="📍 Kanál", value=channel.mention, inline=True)
        embed.add_field(name="🔢 Aktuální číslo", value=f"`{number_display(výchozí_číslo)}`", inline=True)
        embed.add_field(name="➡️ Další číslo", value=f"`{number_display(výchozí_číslo + 1)}`", inline=True)
        embed.add_field(name="💥 Reset po chybě", value="Zapnutý" if reset_po_chybe else "Vypnutý", inline=True)
        embed.add_field(name="🪙 Tokeny", value="1 za každé 100. číslo", inline=True)
        embed.add_field(name="💎 Gemy", value="80 za každé 1 000. číslo", inline=True)
        embed.set_footer(text="Více čísel po sobě může přidat i stejný hráč.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="set_number", description="Ručně nastaví poslední správné číslo.")
    @app_commands.describe(číslo="Poslední správné číslo")
    async def set_number(
        self, interaction: discord.Interaction,
        číslo: app_commands.Range[int, 0, 2_147_483_646],
    ):
        if not await self._defer(interaction, ephemeral=True):
            return
        try:
            async with self._guild_locks[interaction.guild_id]:
                async with db.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            "INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
                            str(interaction.guild_id),
                        )
                        await conn.execute(
                            """UPDATE guild_settings SET current_number=$2,
                               current_streak=0, last_user_id=NULL WHERE guild_id=$1""",
                            str(interaction.guild_id), číslo,
                        )
        except Exception:
            logger.exception("Ruční nastavení čísla selhalo (guild=%s)", interaction.guild_id)
            await self._send_error(interaction, "❌ Nepodařilo se uložit číslo do databáze.")
            return
        await interaction.followup.send(
            f"✅ Číslo nastaveno na **{number_display(číslo)}**. "
            f"Další je **{number_display(číslo + 1)}**. Série byla resetována.",
            ephemeral=True,
        )

    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="setup_time", description="Nastaví denní topku v českém čase (Europe/Prague).")
    @app_commands.describe(time="HH:MM, například 20:00")
    async def setup_time(self, interaction: discord.Interaction, time: str):
        try:
            parsed = datetime.strptime(time, "%H:%M")
            if parsed.strftime("%H:%M") != time:
                raise ValueError("Neplatný tvar času")
        except ValueError:
            await self._send_error(interaction, "❌ Čas musí mít přesný formát **HH:MM** (např. `20:00`).")
            return
        if not await self._defer(interaction, ephemeral=True):
            return
        try:
            await update_setting(interaction.guild_id, "counting_time", time)
        except Exception:
            logger.exception("Uložení counting_time selhalo (guild=%s)", interaction.guild_id)
            await self._send_error(interaction, "❌ Čas se nepodařilo uložit do databáze.")
            return
        await interaction.followup.send(
            f"✅ Denní žebříček bude zveřejněn každý den v **{time}** "
            "(časové pásmo **Europe/Prague**, automaticky letní/zimní čas).",
            ephemeral=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # STATISTIKY
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.command(name="leaderboard", description="Zobrazí denní nebo historický žebříček Countingu.")
    @app_commands.choices(typ=[
        app_commands.Choice(name="Dnes", value="daily"),
        app_commands.Choice(name="Celkově", value="lifetime"),
    ])
    async def leaderboard(self, interaction: discord.Interaction, typ: str = "daily"):
        if not await self._defer(interaction):
            return
        try:
            guild_id = interaction.guild_id
            if typ == "daily":
                rows = await get_top_users_daily(guild_id, limit=10)
                title = "📊 Denní žebříček Countingu"
                color = discord.Color.blurple()
            else:
                rows = await get_top_users_lifetime(guild_id, limit=10)
                title = "🏆 Historický žebříček Countingu"
                color = discord.Color.gold()
            async with db.pool.acquire() as conn:
                info = await conn.fetchrow(
                    "SELECT current_number, current_streak FROM guild_settings WHERE guild_id=$1",
                    str(guild_id),
                )
            current = int(info["current_number"] or 0) if info else 0
            streak = int(info["current_streak"] or 0) if info else 0
        except Exception:
            logger.exception("Načtení leaderboardu selhalo (guild=%s)", interaction.guild_id)
            await self._send_error(interaction, "❌ Žebříček se nepodařilo načíst ze Supabase.")
            return

        embed = self._base_embed(title, color=color)
        embed.add_field(name="🔢 Aktuální číslo", value=f"**{number_display(current)}**", inline=True)
        embed.add_field(name="🔥 Současná série", value=f"**{number_display(streak)}**", inline=True)
        embed.add_field(name="👑 Nejlepší počtáři", value=leaderboard_lines(rows), inline=False)
        embed.set_footer(text="Denní výsledky se resetují po zveřejnění denní topky.")
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.guild_only()
    @app_commands.command(name="status", description="Zobrazí nastavení a aktuální stav Countingu.")
    async def status(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        try:
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT counting_channel_id, current_number, current_streak,
                              reset_on_fail, counting_time, last_user_id
                       FROM guild_settings WHERE guild_id=$1""",
                    str(interaction.guild_id),
                )
        except Exception:
            logger.exception("Načtení Counting statusu selhalo")
            await self._send_error(interaction, "❌ Stav Countingu se nepodařilo načíst.")
            return

        if not row or row["counting_channel_id"] is None:
            await interaction.followup.send(
                "ℹ️ Counting ještě není nastavený. Administrátor může použít `/counting setup_channel`. ",
                ephemeral=True,
            )
            return
        current = int(row["current_number"] or 0)
        streak = int(row["current_streak"] or 0)
        last_user = row["last_user_id"]
        embed = self._base_embed("🔢 Counting · stav serveru")
        embed.add_field(name="📍 Kanál", value=f"<#{row['counting_channel_id']}>", inline=True)
        embed.add_field(name="➡️ Další číslo", value=f"**{number_display(current + 1)}**", inline=True)
        embed.add_field(name="🔥 Aktuální série", value=f"**{number_display(streak)}**", inline=True)
        embed.add_field(name="💥 Reset po chybě", value="Zapnutý" if row["reset_on_fail"] is None or int(row["reset_on_fail"]) == 1 else "Vypnutý", inline=True)
        embed.add_field(name="⏰ Denní topka", value=f"{row['counting_time']} (Praha)" if row["counting_time"] else "Nenastavena", inline=True)
        embed.add_field(name="👤 Poslední počtář", value=f"<@{last_user}>" if last_user else "Nikdo", inline=True)
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    # ─────────────────────────────────────────────────────────────────────────
    # ATOMICKÉ POČÍTÁNÍ A ODMĚNY
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _store_count(guild_id: int, channel_id: int, user_id: int, number: int) -> CountResult:
        """Jeden DB commit pro číslo + leaderboard + Brawl měnu.

        PostgreSQL FOR UPDATE serializuje počítání napříč procesy/instancemi.
        Při jakékoli DB chybě transakce vrátí vše do původního stavu.
        """
        gid, uid = str(guild_id), str(user_id)
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                setting = await conn.fetchrow(
                    """SELECT counting_channel_id, current_number, current_streak,
                              reset_on_fail FROM guild_settings
                       WHERE guild_id=$1 FOR UPDATE""",
                    gid,
                )
                if not setting or setting["counting_channel_id"] != channel_id:
                    return CountResult("wrong_channel")

                expected = int(setting["current_number"] or 0) + 1
                if expected > POSTGRES_INT_MAX:
                    return CountResult("limit", expected=expected)

                if number != expected:
                    reset = setting["reset_on_fail"] is None or int(setting["reset_on_fail"]) == 1
                    if reset:
                        await conn.execute(
                            """UPDATE guild_settings
                               SET current_number=0, current_streak=0, last_user_id=NULL
                               WHERE guild_id=$1""",
                            gid,
                        )
                    return CountResult("incorrect", expected=expected, number=number, reset=reset)

                await conn.execute(
                    """UPDATE guild_settings
                       SET current_number=$2,
                           current_streak=COALESCE(current_streak,0)+1,
                           last_user_id=$3
                       WHERE guild_id=$1""",
                    gid, number, uid,
                )
                await conn.execute(
                    """INSERT INTO counting_leaderboard
                           (guild_id, user_id, daily_counts, lifetime_counts)
                       VALUES ($1, $2, 1, 1)
                       ON CONFLICT (guild_id, user_id) DO UPDATE SET
                           daily_counts=counting_leaderboard.daily_counts+1,
                           lifetime_counts=counting_leaderboard.lifetime_counts+1""",
                    gid, uid,
                )

                # Původní ekonomika zůstává: tisícovka má 80 gemů,
                # nikoli zároveň další token.
                tokens = 0
                gems = 0
                if number % 1_000 == 0:
                    gems = 80
                elif number % 100 == 0:
                    tokens = 1
                if tokens or gems:
                    await conn.execute(
                        """INSERT INTO user_brawl (guild_id, user_id, tokens, gems)
                           VALUES ($1, $2, $3, $4)
                           ON CONFLICT (guild_id, user_id) DO UPDATE SET
                               tokens=user_brawl.tokens+EXCLUDED.tokens,
                               gems=user_brawl.gems+EXCLUDED.gems""",
                        gid, uid, tokens, gems,
                    )
                return CountResult("correct", number=number, tokens=tokens, gems=gems)

    @staticmethod
    async def _react(message: discord.Message, emoji: discord.Emoji | str) -> None:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException as exc:
            logger.debug("Nelze přidat reakci ke zprávě %s: %s", message.id, exc)

    @staticmethod
    async def _announce(message: discord.Message, text: str) -> None:
        try:
            await message.channel.send(text, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        except discord.HTTPException as exc:
            logger.warning("Counting oznámení selhalo (guild=%s): %s", message.guild.id, exc)

    def _remember_message(self, message_id: int) -> None:
        if message_id in self._recent_message_set:
            return
        if len(self._recent_message_ids) >= 4_000:
            expired = self._recent_message_ids.popleft()
            self._recent_message_set.discard(expired)
        self._recent_message_ids.append(message_id)
        self._recent_message_set.add(message_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        text = message.content.strip()
        # '123 aha' není platné číslo; zprávy bez čísla nechodí vůbec do DB.
        if not NUMBER_PATTERN.fullmatch(text):
            return
        if message.id in self._recent_message_set:
            return

        gid = message.guild.id
        try:
            async with self._guild_locks[gid]:
                # Kontrola po získání zámku chrání i před duplicitou během DB await.
                if message.id in self._recent_message_set:
                    return
                channel_id = await self._get_counting_channel(gid)
                if channel_id != message.channel.id:
                    return
                result = await self._store_count(gid, message.channel.id, message.author.id, int(text))
                if result.status == "wrong_channel":
                    self._channel_cache.pop(gid, None)
                    return
                if result.status in ("correct", "incorrect", "limit"):
                    self._remember_message(message.id)
        except Exception:
            logger.exception("Counting DB chyba (guild=%s, message=%s)", gid, message.id)
            # Nepotvrzovat ✅ ani ❌, pokud nebylo jisté, že zápis do DB prošel.
            return

        if result.status == "limit":
            await self._announce(message, "⚠️ Bylo dosaženo maximální hodnoty počítadla. Kontaktuj administrátora.")
            return
        if result.status == "incorrect":
            await self._react(message, "❌")
            if result.reset:
                await self._announce(
                    message,
                    f"💥 {message.author.mention} napsal **{number_display(result.number)}**, "
                    f"ale očekávalo se **{number_display(result.expected)}**. "
                    "Série skončila — začínáme zase od **1**!",
                )
            return
        if result.status != "correct":
            return

        verify = discord.utils.get(message.guild.emojis, name="verify")
        await self._react(message, verify or "✅")
        if result.gems:
            await self._announce(
                message,
                f"💎 **MILNÍK {number_display(result.number)}!** "
                f"{message.author.mention} získává **{result.gems} gemů** do Brawl systému!",
            )
        elif result.tokens:
            await self._announce(
                message,
                f"🪙 **MILNÍK {number_display(result.number)}!** "
                f"{message.author.mention} získává **{result.tokens} token** do Brawl systému!",
            )

    # ─────────────────────────────────────────────────────────────────────────
    # DENNÍ ŽEBŘÍČEK – PRAGUE + TRVALÁ DEDUPLIKACE
    # ─────────────────────────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_topka_time(self):
        now = datetime.now(PRAGUE)
        today = now.date()
        clock = now.strftime("%H:%M")
        try:
            guild_rows = await get_all_guilds_with_counting()
        except Exception:
            logger.exception("Nezdařilo se načtení naplánovaných Counting reportů")
            return

        for guild_id, channel_id, report_time in guild_rows:
            if not report_time or report_time != clock:
                continue
            gid = int(guild_id)
            key = (gid, today)
            if key in self._daily_finished:
                continue
            guild = self.bot.get_guild(gid)
            if guild is None:
                continue
            channel = guild.get_channel(int(channel_id))
            if channel is None or not hasattr(channel, "send"):
                logger.warning("Denní topka: kanál %s na guild %s není v cache", channel_id, gid)
                continue
            try:
                await self._daily_report(gid, channel, today)
            except Exception:
                logger.exception("Denní Counting report selhal pro server %s", gid)

        # Držíme jen dnešní datum, aby sada nerostla bez omezení.
        self._daily_finished = {k for k in self._daily_finished if k[1] == today}
        self._daily_announced = {k for k in self._daily_announced if k[1] == today}

    async def _daily_report(self, guild_id: int, channel, today: date) -> None:
        key = (guild_id, today)
        gid = str(guild_id)
        async with self._guild_locks[guild_id]:
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """SELECT counting_last_report_date FROM guild_settings
                           WHERE guild_id=$1 FOR UPDATE""",
                        gid,
                    )
                    if not row:
                        return
                    if row["counting_last_report_date"] == today:
                        self._daily_finished.add(key)
                        return

                    top_users = await conn.fetch(
                        """SELECT user_id, daily_counts FROM counting_leaderboard
                           WHERE guild_id=$1 AND daily_counts>0
                           ORDER BY daily_counts DESC, user_id ASC LIMIT 5""",
                        gid,
                    )
                    embed = self._base_embed(
                        "🏆 Denní TOP 5 · Counting",
                        description="Další den počítání za námi! Tohle jsou dnešní nejaktivnější hráči.",
                        color=discord.Color.gold(),
                    )
                    embed.add_field(name="👑 Pořadí", value=leaderboard_lines(top_users, max_players=5), inline=False)
                    embed.set_footer(text=f"Výsledky za {today:%d.%m.%Y} • Čas: Praha")

                    # Nejprve odešleme report, až poté resetujeme hodnoty.
                    # Síťový požadavek je omezen timeoutem, aby dlouho nedržel DB lock.
                    if key not in self._daily_announced:
                        async with asyncio.timeout(15):
                            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                        self._daily_announced.add(key)
                    await conn.execute(
                        "UPDATE counting_leaderboard SET daily_counts=0 WHERE guild_id=$1",
                        gid,
                    )
                    await conn.execute(
                        "UPDATE guild_settings SET counting_last_report_date=$2 WHERE guild_id=$1",
                        gid, today,
                    )
            self._daily_finished.add(key)
            logger.info("Denní Counting report a reset dokončen: guild=%s, date=%s", gid, today)

    @check_topka_time.before_loop
    async def before_check_topka_time(self):
        await self.bot.wait_until_ready()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await self._send_error(interaction, "⛔ Tento příkaz je jen pro administrátory.")
            return
        if isinstance(error, app_commands.NoPrivateMessage):
            await self._send_error(interaction, "❌ Counting funguje pouze na serveru.")
            return
        root = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if isinstance(root, discord.NotFound) and root.code in (10062, 10015):
            logger.warning("Vypršela Counting interaction %s (code=%s)", interaction.id, root.code)
            return
        logger.error("Counting příkaz selhal", exc_info=(type(root), root, root.__traceback__))
        await self._send_error(interaction, "❌ Příkaz se nepodařilo dokončit. Podrobnosti jsou v logu Renderu.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Counting(bot))
