from __future__ import annotations

import asyncio
import logging
import math
import random
from collections import defaultdict
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    add_brawler_to_user,
    add_tokens_and_gems,
    get_user_brawl_data,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# BRAWLEŘI A RARITY
# ─────────────────────────────────────────────────────────────────────────────

RARITY_COLORS = {
    "Rare": discord.Color.green(),
    "Super Rare": discord.Color.blue(),
    "Epic": discord.Color.purple(),
    "Mythic": discord.Color.red(),
    "Legendary": discord.Color.gold(),
    "Ultra Legendary": discord.Color.from_rgb(148, 0, 211),
}

RARITY_EMOJIS = {
    "Rare": "🟢",
    "Super Rare": "🔵",
    "Epic": "🟣",
    "Mythic": "🔴",
    "Legendary": "🟡",
    "Ultra Legendary": "🔮",
}

# Aktualizovaný katalog, včetně Wendy / Cosmo / Vince (Mythic).
BRAWLERS = {
    "Rare": [
        "Nita", "Colt", "Bull", "Brock", "El Primo", "Barley", "Poco", "Rosa",
    ],
    "Super Rare": [
        "Jessie", "Dynamike", "Tick", "8-Bit", "Rico", "Darryl", "Penny",
        "Carl", "Jacky", "Gus",
    ],
    "Epic": [
        "Bo", "Emz", "Stu", "Piper", "Pam", "Frank", "Bibi", "Bea", "Nani",
        "Edgar", "Griff", "Grom", "Bonnie", "Gale", "Colette", "Belle", "Ash",
        "Lola", "Sam", "Mandy", "Maisie", "Hank", "Pearl", "Larry", "Angelo",
        "Berry", "Shade", "Meeple", "Trunk", "Bolt",
    ],
    "Mythic": [
        "Mortis", "Tara", "Gene", "Max", "Mr. P", "Sprout", "Byron", "Squeak",
        "Lou", "Ruffs", "Buzz", "Fang", "Eve", "Otis", "Buster", "Gray",
        "Willow", "Chuck", "Mico", "Lily", "Ollie", "Finx", "Jae-Yong",
        "Alli", "Mina", "Glowy", "Damian", "Janet", "R-T", "Doug", "Charlie",
        "Melodie", "Clancy", "Moe", "Juju", "Lumi", "Zigy", "Gigi",
        "Najia", "Starr Nova", "Wendy", "Cosmo", "Vince",
    ],
    "Legendary": [
        "Spike", "Crow", "Leon", "Sandy", "Amber", "Meg", "Surge", "Chester",
        "Cordelius", "Kit", "Draco", "Kenji", "Pierce", "Nori",
    ],
    "Ultra Legendary": ["Kaze", "Sirius"],
}

TOTAL_BRAWLERS_COUNT = sum(len(names) for names in BRAWLERS.values())
ALL_BRAWLER_NAMES = frozenset(name for names in BRAWLERS.values() for name in names)

if len(ALL_BRAWLER_NAMES) != TOTAL_BRAWLERS_COUNT:
    raise ValueError("V katalogu BRAWLERS je některý Brawler uveden vícekrát.")


# Původní šance zachované beze změny. Pokud už je rarita plně sesbíraná,
# její váha se vyloučí a ostatní dostupné rarity se přepočítají poměrně.
BOX_RATES = {
    "brawl_box": {
        "Rare": 60, "Super Rare": 25, "Epic": 10,
        "Mythic": 4.0, "Legendary": 0.9, "Ultra Legendary": 0.1,
    },
    "big_box": {
        "Rare": 35, "Super Rare": 30, "Epic": 20,
        "Mythic": 10.0, "Legendary": 4.5, "Ultra Legendary": 0.5,
    },
    "mega_box": {
        "Rare": 10, "Super Rare": 20, "Epic": 35,
        "Mythic": 20.0, "Legendary": 12.0, "Ultra Legendary": 3.0,
    },
}

for _box_key, _rates in BOX_RATES.items():
    if set(_rates) != set(BRAWLERS) or not math.isclose(sum(_rates.values()), 100.0):
        raise ValueError(f"Chybná konfigurace šancí pro {_box_key}.")


@dataclass(frozen=True, slots=True)
class BoxConfig:
    name: str
    icon: str
    currency: str | None = None
    price: int = 0


BOXES = {
    "brawl_box": BoxConfig(name="Brawl Box", icon="📦"),
    "big_box": BoxConfig(name="Big Box", icon="🎁", currency="tokens", price=10),
    "mega_box": BoxConfig(name="Mega Box", icon="💥", currency="gems", price=80),
}

CURRENCY_DETAILS = {
    "tokens": ("🪙", "tokenů"),
    "gems": ("💎", "gemů"),
}


def generate_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Zobrazí průběh sbírky a bezpečně omezí hodnoty do rozsahu 0–100 %."""
    if total <= 0:
        return "░" * length
    filled = round(length * min(max(current / total, 0.0), 1.0))
    return "█" * filled + "░" * (length - filled)


def format_cooldown(seconds: float) -> str:
    remaining = max(1, math.ceil(seconds))
    hours, rest = divmod(remaining, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if secs or not parts:
        parts.append(f"{secs} s")
    return " ".join(parts)


class BrawlCog(commands.Cog, name="brawl"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Zámek na hráče: omezuje dvojitý nákup/roll v jedné instanci bota.
        self._player_locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
        # Zámek na server: současné vytvoření stejné role.
        self._role_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    @staticmethod
    async def _defer(interaction: discord.Interaction, *, ephemeral: bool = False) -> bool:
        """Potvrdí slash příkaz před prací s DB. Vypršený interaction jen zaloguje."""
        try:
            await interaction.response.defer(thinking=True, ephemeral=ephemeral)
            return True
        except discord.NotFound as exc:
            if exc.code == 10062:
                logger.warning(
                    "Discord interaction vypršela ještě před potvrzením "
                    "(id=%s, command=%s). Prověř event loop/Render latenci.",
                    interaction.id,
                    getattr(interaction.command, "name", "?"),
                )
                return False
            raise

    @staticmethod
    def _roll_brawler(box_key: str, owned_brawlers: set[str]) -> tuple[str | None, str | None]:
        """Vybere nevlastněného Brawlera; vzácnosti mají zadané váhy."""
        available = {
            rarity: [name for name in names if name not in owned_brawlers]
            for rarity, names in BRAWLERS.items()
        }
        rarities = [rarity for rarity in BOX_RATES[box_key] if available[rarity]]
        if not rarities:
            return None, None

        weights = [BOX_RATES[box_key][rarity] for rarity in rarities]
        rarity = random.choices(rarities, weights=weights, k=1)[0]
        return rarity, random.choice(available[rarity])

    async def _assign_brawler_role(
        self,
        guild: discord.Guild,
        member: discord.Member,
        brawler_name: str,
        rarity: str,
    ) -> str:
        """Role jsou pouze bonus: chyba Discord oprávnění nikdy neruší DB odměnu."""
        role_name = f"🤖 {brawler_name}"
        try:
            async with self._role_locks[guild.id]:
                role = discord.utils.get(guild.roles, name=role_name)
                if role is None:
                    role = await guild.create_role(
                        name=role_name,
                        color=RARITY_COLORS[rarity],
                        reason=f"Brawl Box • odemčen {brawler_name}",
                    )

            if role in member.roles:
                return "✅ Roli už máš"
            await member.add_roles(role, reason=f"Brawl Box • {brawler_name}")
            return "✅ Role přidělena"
        except discord.Forbidden:
            logger.warning("Chybí oprávnění k roli %s na serveru %s", role_name, guild.id)
            return "⚠️ Bot nemá oprávnění přidat roli"
        except discord.HTTPException:
            logger.exception("Chyba Discord API při přidání role %s", role_name)
            return "⚠️ Roli se nepodařilo přidat"

    @staticmethod
    def _create_unlock_embed(
        interaction: discord.Interaction,
        box_key: str,
        rarity: str,
        brawler_name: str,
        owned_after: int,
        role_result: str,
    ) -> discord.Embed:
        box = BOXES[box_key]
        emoji = RARITY_EMOJIS[rarity]
        progress = 100 * owned_after / TOTAL_BRAWLERS_COUNT

        embed = discord.Embed(
            title=f"{box.icon} {box.name}  •  OTEVŘENO!",
            description=(
                "## ✨ Nový Brawler odemčen!\n"
                f"# {brawler_name}\n"
                f"{emoji} **{rarity}**"
            ),
            color=RARITY_COLORS[rarity],
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="🏆 Sbírka", value=f"**{owned_after}/{TOTAL_BRAWLERS_COUNT}** ({progress:.1f} %)", inline=True)
        embed.add_field(name="🤖 Discord role", value=role_result, inline=True)
        embed.add_field(
            name="📈 Postup sbírky",
            value=f"`{generate_progress_bar(owned_after, TOTAL_BRAWLERS_COUNT)}`",
            inline=False,
        )
        embed.set_footer(text=f"Brawl System • {interaction.user.display_name}")
        return embed

    async def _open_box(self, interaction: discord.Interaction, box_key: str) -> None:
        """Jedna implementace pro všechny boxy – kontrola, roll, odečet, uložení."""
        guild = interaction.guild
        if guild is None or interaction.guild_id is None or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("❌ Boxy lze otevírat jen na Discord serveru.", ephemeral=True)
            return

        box = BOXES[box_key]
        key = (guild.id, interaction.user.id)

        async with self._player_locks[key]:
            user_data = await get_user_brawl_data(*key)
            owned = set(user_data.get("brawlers") or [])
            amount = int(user_data.get(box.currency, 0) or 0) if box.currency else 0

            if box.currency and amount < box.price:
                icon, noun = CURRENCY_DETAILS[box.currency]
                await interaction.followup.send(
                    f"{icon} **Nedostatek měny!** {box.name} stojí **{box.price} {noun}**. "
                    f"Máš **{amount}** (chybí {box.price - amount}).",
                    ephemeral=True,
                )
                return

            rarity, brawler_name = self._roll_brawler(box_key, owned)
            if rarity is None or brawler_name is None:
                await interaction.followup.send(
                    "🏆 **Máš kompletní sbírku!** Všechny dostupné Brawlery už vlastníš. "
                    "Žádná měna se neodečetla.",
                    ephemeral=True,
                )
                return

            # Zápisy jsou oddělené, protože stávající database.py nemá transakční API.
            # Při selhání přidání Brawlera se pokusíme měnu vrátit.
            charged = False
            try:
                if box.currency == "tokens":
                    await add_tokens_and_gems(*key, tokens=-box.price)
                    charged = True
                elif box.currency == "gems":
                    await add_tokens_and_gems(*key, gems=-box.price)
                    charged = True

                await add_brawler_to_user(*key, brawler_name)
            except Exception:
                if charged:
                    try:
                        if box.currency == "tokens":
                            await add_tokens_and_gems(*key, tokens=box.price)
                        elif box.currency == "gems":
                            await add_tokens_and_gems(*key, gems=box.price)
                    except Exception:
                        logger.exception(
                            "KRITICKÉ: nepodařilo se vrátit %s za %s hráči %s na serveru %s",
                            box.currency, box_key, interaction.user.id, guild.id,
                        )
                raise

            owned_after = len((owned | {brawler_name}) & ALL_BRAWLER_NAMES)

        role_result = await self._assign_brawler_role(guild, interaction.user, brawler_name, rarity)
        embed = self._create_unlock_embed(
            interaction, box_key, rarity, brawler_name, owned_after, role_result,
        )
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    # ─────────────────────────────────────────────────────────────────────────
    # BOX PŘÍKAZY
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 21600, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="brawlbox", description="Otevři zdarma Brawl Box (1× za 6 hodin).")
    async def brawlbox(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        await self._open_box(interaction, "brawl_box")

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="bigbox", description="Otevři Big Box za 10 tokenů.")
    async def bigbox(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        await self._open_box(interaction, "big_box")

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="megabox", description="Otevři Mega Box za 80 gemů.")
    async def megabox(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        await self._open_box(interaction, "mega_box")

    # ─────────────────────────────────────────────────────────────────────────
    # INVENTÁŘ A DROP RATES
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.command(name="inventory", description="Prohlédni si měnu, Brawlery a postup sbírky.")
    async def inventory(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return

        data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        owned = set(data.get("brawlers") or []) & ALL_BRAWLER_NAMES
        total = len(owned)
        percent = 100 * total / TOTAL_BRAWLERS_COUNT

        embed = discord.Embed(
            title=f"🎒 Brawl inventář • {discord.utils.escape_markdown(interaction.user.display_name)}",
            description=(
                f"**🏆 {total} / {TOTAL_BRAWLERS_COUNT} Brawlerů**  •  **{percent:.1f} %**\n"
                f"`{generate_progress_bar(total, TOTAL_BRAWLERS_COUNT, 18)}`\n\n"
                f"🪙 **Tokeny:** {int(data.get('tokens') or 0):,}\n"
                f"💎 **Gemy:** {int(data.get('gems') or 0):,}"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )

        for rarity, names in BRAWLERS.items():
            matching = [name for name in names if name in owned]
            value = ", ".join(f"`{name}`" for name in matching) if matching else "*Zatím žádný.*"
            embed.add_field(
                name=f"{RARITY_EMOJIS[rarity]} {rarity}  •  {len(matching)}/{len(names)}",
                value=value,
                inline=False,
            )

        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Sbírej Brawlery pomocí /brawlbox, /bigbox a /megabox")
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.guild_only()
    @app_commands.command(name="drop_rates", description="Zobraz šance a ceny všech boxů.")
    async def drop_rates(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return

        embed = discord.Embed(
            title="🎲 Brawl Box • Drop Rates",
            description=(
                "Šance na **jednoho nového Brawlera** podle jeho rarity.\n"
                "*Když už máš celou raritu, její šance se poměrně rozdělí mezi zbývající rarity.*"
            ),
            color=discord.Color.blurple(),
        )
        for box_key, box in BOXES.items():
            if box.currency:
                icon, noun = CURRENCY_DETAILS[box.currency]
                cost = f"{icon} {box.price} {noun}"
            else:
                cost = "🆓 Zdarma • každých 6 hodin"
            lines = [
                f"{RARITY_EMOJIS[rarity]} **{rarity}** — {chance:g} %"
                for rarity, chance in BOX_RATES[box_key].items()
            ]
            embed.add_field(
                name=f"{box.icon} {box.name}  •  {cost}",
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text="Šance se neodvíjí od počtu postav v dané raritě.")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ADMIN
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="add_currency", description="[Admin] Přidej uživateli tokeny nebo gemy.")
    @app_commands.describe(
        user="Uživatel, kterému chceš připsat měnu",
        tokens="Počet tokenů (0 až 1 000 000)",
        gems="Počet gemů (0 až 1 000 000)",
    )
    async def add_currency(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        tokens: app_commands.Range[int, 0, 1_000_000] = 0,
        gems: app_commands.Range[int, 0, 1_000_000] = 0,
    ):
        if not await self._defer(interaction, ephemeral=True):
            return
        if tokens == 0 and gems == 0:
            await interaction.followup.send("⚠️ Zadej alespoň jednu kladnou částku.", ephemeral=True)
            return

        key = (interaction.guild_id, user.id)
        async with self._player_locks[key]:
            await add_tokens_and_gems(*key, tokens=tokens, gems=gems)

        embed = discord.Embed(
            title="✅ Měna připsána",
            description=f"Účet: **{discord.utils.escape_markdown(user.display_name)}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="🪙 Tokeny", value=f"+{tokens:,}")
        embed.add_field(name="💎 Gemy", value=f"+{gems:,}")
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info("Admin %s připsal %s tokenů a %s gemů hráči %s", interaction.user.id, tokens, gems, user.id)

    # ─────────────────────────────────────────────────────────────────────────
    # CHYBOVÁ HLÁŠENÍ
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _send_error(interaction: discord.Interaction, message: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException as exc:
            # Interakce může mezitím vypršet. Nesmíme kvůli tomu vyhazovat další chybu.
            logger.warning("Nelze odeslat chybové hlášení pro interaction %s: %s", interaction.id, exc)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.CommandOnCooldown):
            await self._send_error(
                interaction,
                f"⏳ Příkaz je na cooldownu. Zkus to za **{format_cooldown(error.retry_after)}**.",
            )
            return

        if isinstance(error, app_commands.MissingPermissions):
            await self._send_error(interaction, "⛔ Tento příkaz může použít pouze administrátor.")
            return

        if isinstance(error, app_commands.NoPrivateMessage):
            await self._send_error(interaction, "❌ Tento příkaz funguje jen na serveru.")
            return

        root_error = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if isinstance(root_error, discord.NotFound) and root_error.code in (10062, 10015):
            logger.warning("Discord interakce/webhook vypršela (id=%s, code=%s)", interaction.id, root_error.code)
            return

        logger.error(
            "Chyba příkazu %s na serveru %s (uživatel %s)",
            getattr(interaction.command, "name", "?"),
            interaction.guild_id,
            interaction.user.id,
            exc_info=(type(root_error), root_error, root_error.__traceback__),
        )
        await self._send_error(
            interaction,
            "❌ Příkaz se nepodařilo dokončit. Zkus to znovu později. "
            "Pokud problém přetrvá, kontaktuj administrátora.",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BrawlCog(bot))
