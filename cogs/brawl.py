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

from database import add_tokens_and_gems, db, get_user_brawl_data

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# BRAWLEŘI A DROP RATES
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
    "Rare": "🟢", "Super Rare": "🔵", "Epic": "🟣", "Mythic": "🔴",
    "Legendary": "🟡", "Ultra Legendary": "🔮",
}

BRAWLERS = {
    "Rare": ["Nita", "Colt", "Bull", "Brock", "El Primo", "Barley", "Poco", "Rosa"],
    "Super Rare": ["Jessie", "Dynamike", "Tick", "8-Bit", "Rico", "Darryl", "Penny", "Carl", "Jacky", "Gus"],
    "Epic": [
        "Bo", "Emz", "Stu", "Piper", "Pam", "Frank", "Bibi", "Bea", "Nani", "Edgar",
        "Griff", "Grom", "Bonnie", "Gale", "Colette", "Belle", "Ash", "Lola", "Sam",
        "Mandy", "Maisie", "Hank", "Pearl", "Larry", "Angelo", "Berry", "Shade",
        "Meeple", "Trunk", "Bolt",
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

ALL_BRAWLERS = frozenset(name for group in BRAWLERS.values() for name in group)
TOTAL_BRAWLERS_COUNT = sum(map(len, BRAWLERS.values()))
if len(ALL_BRAWLERS) != TOTAL_BRAWLERS_COUNT:
    raise ValueError("V seznamu Brawlerů je duplicitní postava.")

BOX_RATES = {
    "brawl_box": {"Rare": 60, "Super Rare": 25, "Epic": 10, "Mythic": 4.0, "Legendary": 0.9, "Ultra Legendary": 0.1},
    "big_box": {"Rare": 35, "Super Rare": 30, "Epic": 20, "Mythic": 10.0, "Legendary": 4.5, "Ultra Legendary": 0.5},
    "mega_box": {"Rare": 10, "Super Rare": 20, "Epic": 35, "Mythic": 20.0, "Legendary": 12.0, "Ultra Legendary": 3.0},
}
for box_id, rates in BOX_RATES.items():
    if set(rates) != set(BRAWLERS) or not math.isclose(sum(rates.values()), 100):
        raise ValueError(f"Neplatné šance pro {box_id}.")


@dataclass(frozen=True, slots=True)
class BoxConfig:
    name: str
    icon: str
    currency: str | None = None
    price: int = 0


BOXES = {
    "brawl_box": BoxConfig("Brawl Box", "📦"),
    "big_box": BoxConfig("Big Box", "🎁", "tokens", 10),
    "mega_box": BoxConfig("Mega Box", "💥", "gems", 80),
}
CURRENCY = {"tokens": ("🪙", "tokenů"), "gems": ("💎", "gemů")}

# Tři krátké vizuální fáze: Discord neumí skutečnou animaci embedu,
# proto postupně editujeme jednu zprávu. Jen 3 edity, šetrné k API.
ANIMATION_FRAMES = (
    ("🔒", "Připravujeme tvůj box...", "▰▱▱▱▱", 0.85),
    ("✨", "Box se třese... něco je uvnitř!", "▰▰▱▱▱", 0.95),
    ("💫", "Otevíráme...", "▰▰▰▰▱", 1.00),
)


def bar(current: int, total: int, length: int = 12) -> str:
    ratio = min(1.0, max(0.0, current / total)) if total > 0 else 0.0
    filled = round(ratio * length)
    return "█" * filled + "░" * (length - filled)


def readable_number(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def cooldown_text(seconds: float) -> str:
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


def purchase_status(owned_currency: int, box: BoxConfig) -> str:
    """Výsledek zobrazený v inventáři, shopu i drop rates."""
    if box.currency is None:
        return "🆓 Zdarma každých 6 hodin"
    icon, name = CURRENCY[box.currency]
    amount = max(0, int(owned_currency))
    if amount >= box.price:
        return f"✅ **Můžeš otevřít!** • {readable_number(amount)} {icon} • cena {box.price} {name}"
    return (
        f"🔒 Chybí **{readable_number(box.price - amount)}** {icon} "
        f"• máš {readable_number(amount)}/{box.price} {name}"
    )


@dataclass(frozen=True, slots=True)
class BoxResult:
    status: str  # 'ok' | 'insufficient' | 'completed'
    rarity: str | None = None
    brawler: str | None = None
    owned_count: int = 0
    tokens: int = 0
    gems: int = 0


class BrawlCog(commands.Cog, name="brawl"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Transakce chrání i napříč instancemi, lokální lock navíc uspořádá
        # požadavky daného hráče na této instanci.
        self._player_locks: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)

    @staticmethod
    async def _defer(interaction: discord.Interaction, *, ephemeral: bool = False) -> bool:
        try:
            await interaction.response.defer(thinking=True, ephemeral=ephemeral)
            return True
        except discord.NotFound as exc:
            if exc.code == 10062:
                logger.warning("Discord interakce %s vypršela před potvrzením", interaction.id)
                return False
            raise

    @staticmethod
    def _roll(box_id: str, owned: set[str]) -> tuple[str | None, str | None]:
        available = {rarity: [name for name in names if name not in owned]
                     for rarity, names in BRAWLERS.items()}
        rarities = [rarity for rarity in BOX_RATES[box_id] if available[rarity]]
        if not rarities:
            return None, None
        rarity = random.choices(rarities, weights=[BOX_RATES[box_id][r] for r in rarities], k=1)[0]
        return rarity, random.choice(available[rarity])

    async def _purchase_and_draw(self, guild_id: int, user_id: int, box_id: str) -> BoxResult:
        """Jedna transakce: načti zůstatek, vylosuj, odečti cenu a ulož Brawlera.

        SELECT ... FOR UPDATE chrání před souběžným otevřením i pokud by běželo
        více procesů bota. Změny se buď uloží všechny, nebo žádná.
        """
        box = BOXES[box_id]
        key = (guild_id, user_id)
        async with self._player_locks[key]:
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO user_brawl (guild_id, user_id, tokens, gems, brawlers) "
                        "VALUES ($1, $2, 0, 0, '') ON CONFLICT (guild_id, user_id) DO NOTHING",
                        str(guild_id), str(user_id),
                    )
                    row = await conn.fetchrow(
                        "SELECT tokens, gems, brawlers FROM user_brawl "
                        "WHERE guild_id = $1 AND user_id = $2 FOR UPDATE",
                        str(guild_id), str(user_id),
                    )
                    if row is None:
                        raise RuntimeError("Hráče se nepodařilo načíst ze Supabase.")

                    tokens = int(row["tokens"] or 0)
                    gems = int(row["gems"] or 0)
                    current = [name.strip() for name in (row["brawlers"] or "").split(",") if name.strip()]
                    owned = set(current)
                    balance = tokens if box.currency == "tokens" else gems
                    if box.currency and balance < box.price:
                        return BoxResult("insufficient", tokens=tokens, gems=gems)
                    rarity, brawler = self._roll(box_id, owned)
                    if rarity is None or brawler is None:
                        return BoxResult("completed", owned_count=len(owned & ALL_BRAWLERS), tokens=tokens, gems=gems)

                    token_price = box.price if box.currency == "tokens" else 0
                    gem_price = box.price if box.currency == "gems" else 0
                    # Zachováme i případné starší záznamy, které v katalogu nejsou.
                    updated = await conn.fetchrow(
                        "UPDATE user_brawl SET "
                        "brawlers=$1, tokens=tokens-$2, gems=gems-$3 "
                        "WHERE guild_id=$4 AND user_id=$5 RETURNING tokens, gems",
                        ",".join([*current, brawler]), token_price, gem_price,
                        str(guild_id), str(user_id),
                    )
                    if updated is None:
                        raise RuntimeError("Nepodařilo se uložit nového Brawlera.")
                    return BoxResult(
                        status="ok", rarity=rarity, brawler=brawler,
                        owned_count=len((owned | {brawler}) & ALL_BRAWLERS),
                        tokens=int(updated["tokens"]), gems=int(updated["gems"]),
                    )

    @staticmethod
    def _opening_embed(box: BoxConfig, frame_index: int, author: str) -> discord.Embed:
        emoji, caption, progress, _ = ANIMATION_FRAMES[frame_index]
        embed = discord.Embed(
            title=f"{box.icon} {box.name}  •  OTEVÍRÁNÍ",
            description=(
                f"# {emoji} {caption}\n\n"
                f"`{progress}`\n\n"
                "*Co se asi skrývá uvnitř?*"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Brawl System • otevírá {author}")
        return embed

    @staticmethod
    def _result_embed(box_id: str, result: BoxResult, author: str) -> discord.Embed:
        box = BOXES[box_id]
        percent = result.owned_count * 100 / TOTAL_BRAWLERS_COUNT
        emoji = RARITY_EMOJIS[result.rarity]
        embed = discord.Embed(
            title=f"{box.icon} {box.name}  •  OTEVŘENO!",
            description=(
                "## ✨ NOVÝ BRAWLER!\n"
                f"# {result.brawler}\n"
                f"{emoji} **{result.rarity}**"
            ),
            color=RARITY_COLORS[result.rarity],
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="🏆 Tvoje sbírka",
            value=(
                f"**{result.owned_count}/{TOTAL_BRAWLERS_COUNT}** • **{percent:.1f} %**\n"
                f"`{bar(result.owned_count, TOTAL_BRAWLERS_COUNT, 14)}`"
            ),
            inline=False,
        )
        embed.add_field(
            name="💰 Zůstatek po otevření",
            value=f"🪙 **{readable_number(result.tokens)}** tokenů\n💎 **{readable_number(result.gems)}** gemů",
            inline=True,
        )
        embed.add_field(
            name="🎁 Další boxy",
            value=(
                f"Big Box: {'✅' if result.tokens >= BOXES['big_box'].price else '🔒'}"
                f"  •  Mega Box: {'✅' if result.gems >= BOXES['mega_box'].price else '🔒'}\n"
                "`/boxshop` • Podrobný přehled"
            ),
            inline=True,
        )
        embed.set_footer(text=f"Brawl System • {author} • Brawler je uložený v Supabase")
        return embed

    async def _reveal(self, interaction: discord.Interaction, box_id: str, result: BoxResult) -> None:
        """Animuje jedinou Discord zprávu; výsledek už je bezpečně v databázi.

        Když selže editace (HTTP API), alespoň se pokusíme doručit výsledek
        novým followupem. Nikdy nespouštíme druhý nákup.
        """
        author = discord.utils.escape_markdown(interaction.user.display_name)
        final_embed = self._result_embed(box_id, result, author)
        message = None
        try:
            message = await interaction.followup.send(
                embed=self._opening_embed(BOXES[box_id], 0, author),
                wait=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            for index, (_, _, _, delay) in enumerate(ANIMATION_FRAMES):
                await asyncio.sleep(delay)
                if index + 1 < len(ANIMATION_FRAMES):
                    await message.edit(embed=self._opening_embed(BOXES[box_id], index + 1, author))
            await message.edit(embed=final_embed)
        except discord.HTTPException:
            logger.exception("Animace boxu selhala; výsledek už je v DB (interaction=%s)", interaction.id)
            if message is not None:
                try:
                    await message.edit(embed=final_embed)
                    return
                except discord.HTTPException:
                    logger.warning("Nelze opravit zprávu s animací (interaction=%s)", interaction.id)
            try:
                await interaction.followup.send(embed=final_embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logger.exception("Nedokážu zobrazit výsledek boxu (interaction=%s)", interaction.id)

    async def _open_box(self, interaction: discord.Interaction, box_id: str) -> None:
        if interaction.guild_id is None:
            await interaction.followup.send("❌ Tento příkaz funguje pouze na serveru.", ephemeral=True)
            return

        result = await self._purchase_and_draw(interaction.guild_id, interaction.user.id, box_id)
        box = BOXES[box_id]

        if result.status == "insufficient":
            icon, currency_name = CURRENCY[box.currency]
            amount = result.tokens if box.currency == "tokens" else result.gems
            await interaction.followup.send(
                f"🔒 **Na {box.icon} {box.name} zatím nemáš dost!**\n"
                f"Cena: **{box.price} {currency_name}** {icon}\n"
                f"Máš: **{readable_number(amount)}** {icon}\n"
                f"Chybí ti: **{readable_number(box.price - amount)}** {icon}\n"
                "Použij `/boxshop` pro přehled všech boxů.",
            )
            return
        if result.status == "completed":
            await interaction.followup.send(
                "🏆 **Máš kompletní sbírku!** Všechny Brawlery už vlastníš. "
                "Nic se ti neodečetlo.",
            )
            return
        await self._reveal(interaction, box_id, result)

    # ─────────────────────────────────────────────────────────────────────────
    # OTEVÍRÁNÍ BOXŮ
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 21600, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="brawlbox", description="Otevři zdarma Brawl Box (jednou za 6 hodin).")
    async def brawlbox(self, interaction: discord.Interaction):
        if await self._defer(interaction):
            await self._open_box(interaction, "brawl_box")

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="bigbox", description="Otevři animovaný Big Box za 10 tokenů.")
    async def bigbox(self, interaction: discord.Interaction):
        if await self._defer(interaction):
            await self._open_box(interaction, "big_box")

    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="megabox", description="Otevři animovaný Mega Box za 80 gemů.")
    async def megabox(self, interaction: discord.Interaction):
        if await self._defer(interaction):
            await self._open_box(interaction, "mega_box")

    # ─────────────────────────────────────────────────────────────────────────
    # INVENTÁŘ, OBCHOD, PRAVDĚPODOBNOSTI
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.command(name="inventory", description="Zobraz sbírku, peněženku a postup k dalšímu boxu.")
    async def inventory(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        owned = set(data.get("brawlers") or []) & ALL_BRAWLERS
        tokens = int(data.get("tokens") or 0)
        gems = int(data.get("gems") or 0)
        total = len(owned)
        percent = total / TOTAL_BRAWLERS_COUNT * 100

        embed = discord.Embed(
            title=f"🎒 Brawl inventář • {discord.utils.escape_markdown(interaction.user.display_name)}",
            description=(
                f"🏆 **{total}/{TOTAL_BRAWLERS_COUNT} Brawlerů**  •  **{percent:.1f} %**\n"
                f"`{bar(total, TOTAL_BRAWLERS_COUNT, 18)}`\n\n"
                f"🪙 **{readable_number(tokens)} tokenů**  •  💎 **{readable_number(gems)} gemů**"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="🎁 Big Box • 10 tokenů",
            value=f"`{bar(tokens, 10, 12)}`\n{purchase_status(tokens, BOXES['big_box'])}",
            inline=False,
        )
        embed.add_field(
            name="💥 Mega Box • 80 gemů",
            value=f"`{bar(gems, 80, 12)}`\n{purchase_status(gems, BOXES['mega_box'])}",
            inline=False,
        )
        for rarity, names in BRAWLERS.items():
            matching = [name for name in names if name in owned]
            detail = ", ".join(f"`{name}`" for name in matching) if matching else "*Zatím žádný.*"
            # Discord má limit 1024 znaků na jedno pole embedu.
            if len(detail) > 1024:
                detail = detail[:1018] + "…"
            embed.add_field(
                name=f"{RARITY_EMOJIS[rarity]} {rarity} • {len(matching)}/{len(names)}",
                value=detail,
                inline=False,
            )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Boxy: /brawlbox • /bigbox • /megabox | Obchod: /boxshop")
        await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.guild_only()
    @app_commands.command(name="boxshop", description="Prohlédni si boxy, ceny a kolik ti chybí tokenů či gemů.")
    async def boxshop(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        tokens = int(data.get("tokens") or 0)
        gems = int(data.get("gems") or 0)
        embed = discord.Embed(
            title="🛒 Brawl Box Shop",
            description=(
                "Vyber box podle ceny a šancí na vzácné postavy.\n\n"
                f"**Tvoje peněženka**\n🪙 {readable_number(tokens)} tokenů  •  "
                f"💎 {readable_number(gems)} gemů"
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="📦 Brawl Box • /brawlbox",
            value="🆓 **Zdarma** jednou za 6 hodin\nNový Brawler z dostupných rarit.",
            inline=False,
        )
        embed.add_field(
            name="🎁 Big Box • /bigbox",
            value=(
                f"`{bar(tokens, 10, 12)}`\n{purchase_status(tokens, BOXES['big_box'])}\n"
                f"Za aktuální zůstatek: **{tokens // 10}×**"
            ),
            inline=False,
        )
        embed.add_field(
            name="💥 Mega Box • /megabox",
            value=(
                f"`{bar(gems, 80, 12)}`\n{purchase_status(gems, BOXES['mega_box'])}\n"
                f"Za aktuální zůstatek: **{gems // 80}×**"
            ),
            inline=False,
        )
        embed.set_footer(text="Šance: /drop_rates • Každý box dává 1 nového Brawlera • Zakoupení má cooldown 3 s")
        await interaction.followup.send(embed=embed)

    @app_commands.guild_only()
    @app_commands.command(name="drop_rates", description="Zobraz šance boxů, ceny i vlastní dostupnost.")
    async def drop_rates(self, interaction: discord.Interaction):
        if not await self._defer(interaction):
            return
        data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        embed = discord.Embed(
            title="🎲 Brawl Box • Drop Rates",
            description=(
                "**Šance na raritu nového Brawlera** pro každý box.\n"
                "*Jakmile vlastníš všechny postavy některé rarity, její šance se "
                "přerozdělí mezi zbývající rarity.*"
            ),
            color=discord.Color.blurple(),
        )
        for box_id, box in BOXES.items():
            amount = int(data.get(box.currency) or 0) if box.currency else 0
            state = purchase_status(amount, box)
            lines = [
                f"{RARITY_EMOJIS[rarity]} **{rarity}:** {chance:g} %"
                for rarity, chance in BOX_RATES[box_id].items()
            ]
            embed.add_field(
                name=f"{box.icon} {box.name}",
                value=f"{state}\n" + "\n".join(lines),
                inline=False,
            )
        embed.set_footer(text="Každý box = 1 nový Brawler. Detailní nákupy: /boxshop")
        await interaction.followup.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # ADMIN
    # ─────────────────────────────────────────────────────────────────────────

    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="add_currency", description="[Admin] Přidej hráči tokeny nebo gemy.")
    @app_commands.describe(
        user="Uživatel", tokens="Počet tokenů (0–1 000 000)", gems="Počet gemů (0–1 000 000)",
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
            await interaction.followup.send("⚠️ Musíš zadat alespoň jednu kladnou částku.", ephemeral=True)
            return
        key = (interaction.guild_id, user.id)
        async with self._player_locks[key]:
            await add_tokens_and_gems(*key, tokens=tokens, gems=gems)
        embed = discord.Embed(
            title="✅ Měna připsána",
            description=f"Hráč: **{discord.utils.escape_markdown(user.display_name)}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="🪙 Tokeny", value=f"+{readable_number(tokens)}")
        embed.add_field(name="💎 Gemy", value=f"+{readable_number(gems)}")
        embed.set_footer(text="Změny jsou uložené do Supabase")
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info("Admin %s připsal %s tokenů a %s gemů hráči %s", interaction.user.id, tokens, gems, user.id)

    # ─────────────────────────────────────────────────────────────────────────
    # OŠETŘENÍ CHYB
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _send_error(interaction: discord.Interaction, message: str) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException as exc:
            logger.warning("Chybovou zprávu pro interaction %s nelze doručit: %s", interaction.id, exc)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await self._send_error(interaction, f"⏳ Příkaz je na cooldownu: **{cooldown_text(error.retry_after)}**.")
            return
        if isinstance(error, app_commands.MissingPermissions):
            await self._send_error(interaction, "⛔ Tento příkaz může použít pouze administrátor.")
            return
        if isinstance(error, app_commands.NoPrivateMessage):
            await self._send_error(interaction, "❌ Tento příkaz funguje jen na serveru.")
            return
        root = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if isinstance(root, discord.NotFound) and root.code in (10062, 10015):
            logger.warning("Discord interakce/webhook vypršela (interaction=%s, code=%s)", interaction.id, root.code)
            return
        logger.error(
            "Chyba příkazu %s na serveru %s (uživatel %s)",
            getattr(interaction.command, "name", "?"), interaction.guild_id, interaction.user.id,
            exc_info=(type(root), root, root.__traceback__),
        )
        await self._send_error(interaction, "❌ Příkaz se nepodařilo dokončit. Zkus to později.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BrawlCog(bot))
