"""Puvod Brawl: daily shop, blings, real named skins, inventory and equip."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from cogs.brawl import BRAWLERS
from database import db

logger = logging.getLogger(__name__)
PRAGUE = ZoneInfo("Europe/Prague")

# Our Discord-game prices and earning rates, NOT Supercell in-game prices.
RARITY_SKIN_PRICE = {
    "Rare": 140, "Super Rare": 175, "Epic": 220,
    "Mythic": 275, "Legendary": 340, "Ultra Legendary": 420,
}
BRAWLER_RARITY = {name: rarity for rarity, members in BRAWLERS.items() for name in members}

# Named skins selected from community Brawl Stars skin catalogs.
# Newer Brawlers may have no publicly verified skin yet; they are not invented.
SKINS = {
    "Nita": ["Panda Nita","Shiba Nita"],
    "Colt": ["Rockstar Colt","Outlaw Colt"],
    "Bull": ["Viking Bull","Touchdown Bull"],
    "Brock": ["Beach Brock","Boom Box Brock"],
    "El Primo": ["El Rudo Primo","El Rey Primo"],
    "Barley": ["Wizard Barley","Maple Barley"],
    "Poco": ["Pirate Poco","Serenade Poco"],
    "Rosa": ["Coco Rosa","Mantis Rosa"],
    "Jessie": ["Summer Jessie","Tanuki Jessie"],
    "Dynamike": ["Classic Dynamike","Robo Mike"],
    "Tick": ["Snowman Tick","King Crab Tick"],
    "8-Bit": ["8-Bit Classic","V8-Bit"],
    "Rico": ["Popcorn Rico","Chicken Rico"],
    "Darryl": ["Dumpling Darryl","Cupcake Darryl"],
    "Penny": ["Bunny Penny","Smuggler Penny"],
    "Carl": ["Goblin Carl","Dark Tide Carl"],
    "Jacky": ["Constructor Jacky","Jet Ski Jacky"],
    "Gus": ["Boy Scout Gus","Balloon Sally Gus"],
    "Bo": ["Horus Bo","Wasp Bo"],
    "Emz": ["Harajuku Emz","DJ 3.M.Z"],
    "Stu": ["Superstar Stu","Headless Rider Stu"],
    "Piper": ["Pink Piper","Lunar Piper"],
    "Pam": ["Holiday Pam","Stonks Pam"],
    "Frank": ["Caveman Frank","DJ Frank"],
    "Bibi": ["ZomBibi","Heroine Bibi"],
    "Bea": ["Ladybug Bea","Neko Bea"],
    "Nani": ["Retro Nani","Ares Nani"],
    "Edgar": ["Blackbird Edgar","Orochi Edgar"],
    "Griff": ["High Score Griff","Sleigher Griff"],
    "Grom": ["Bunny Grom","FrankenGrom"],
    "Bonnie": ["Unicorn Bonnie","FootBonnie"],
    "Gale": ["Nutcracker Gale","Squeakbuster Gale"],
    "Colette": ["Inspector Colette","Trixie Colette"],
    "Belle": ["Ivy Belle","Coral Belle"],
    "Ash": ["Krampus Ash","Pizza Oven Ash"],
    "Lola": ["Galaxy Storm Lola","Kitsune Lola"],
    "Sam": ["Yeti Sam","Caesar Sam"],
    "Mandy": ["Witch Mandy","Hanbok Mandy"],
    "Maisie": ["Tech Maisie","Marauder Maisie"],
    "Hank": ["Shark Tank Hank","Rodeo Hank"],
    "Pearl": ["Vintage Pearl","Porcelain Pearl"],
    "Larry": ["Larry & Lawrie Controllers","Glitch Larry & Lawrie"],
    "Angelo": ["Elf Angelo","Dionysus Angelo"],
    "Berry": ["Dark Horse Berry","Pegasus Berry"],
    "Shade": ["Cinema Shade","Street Shade"],
    "Meeple": ["Strike Meeple","Mystic Meeple"],
    "Trunk": ["Swimming Trunk","Royale Trunk"],
    "Bolt": ["King Crab Bolt"],
    "Mortis": ["Rogue Mortis","Mecha Mortis"],
    "Tara": ["Stara","Street Ninja Tara"],
    "Gene": ["Evil Gene","Pirate Gene"],
    "Max": ["GT Max","Streetwear Max"],
    "Mr. P": ["Agent P","Count Pengula"],
    "Sprout": ["Tropical Sprout","Lunar Sprout"],
    "Byron": ["Wizard Byron","Overlord Byron"],
    "Squeak": ["Ghost Squeak","Potato Squeak"],
    "Lou": ["Smooth Lou","Burger Lou"],
    "Ruffs": ["Marshal Ruffs","Sous Chef Ruffs"],
    "Buzz": ["Kaiju Buzz","Director Buzz"],
    "Fang": ["Octo Fang","Kabocha Fang"],
    "Eve": ["Baiku Eve","Mothra Eve"],
    "Otis": ["Pharaotis","Oni Otis"],
    "Buster": ["Crocodile Buster","Chainsaw Buster"],
    "Gray": ["Detective Gray","Runaway Gray"],
    "Willow": ["Axl Willow","Scorpion Willow"],
    "Chuck": ["Inferno Chuck","Electroid Chuck"],
    "Mico": ["Wukong Mico","Macaron Mico"],
    "Lily": ["Strawberry Lily","Knight Lily"],
    "Ollie": ["Ollie-G","Pharaollie"],
    "Finx": ["Jurassic Finx","Mecha Chief Finx"],
    "Jae-Yong": ["True Silver Jae-Yong"],
    "Alli": ["Graffiti Alli","Baddie Alli"],
    "Mina": ["Graffiti Mina","Ollie-G Mina"],
    "Glowy": ["Ladybug Glowy","Strawberry Glowy"],
    "Damian": ["Unicorn Knight Damian","Pegasus Damian"],
    "Janet": ["Popstar Janet","Dark Fairy Janet"],
    "R-T": ["Patrol R-T","Poseidon R-T"],
    "Doug": ["Draco Doug","Man-o-war Doug"],
    "Charlie": ["Amazing Charlie","Virus Charlie"],
    "Melodie": ["Sif Melodie","Harpy Melodie"],
    "Clancy": ["High Stakes Clancy","Kaiju Clancy"],
    "Moe": ["Monterey Moe","Moon Driller Moe"],
    "Juju": ["Unlucky Juju","Queen Juju"],
    "Lumi": ["Dark Knight Lumi","Persephone Lumi"],
    "Zigy": ["Wicked Ziggy","Dark Wizard Ziggy"],
    "Gigi": ["Axl Gigi","Unlucky Gigi"],
    "Najia": ["Stara Najia","Jurassic Najia"],
    "Starr Nova": ["Tabby Starr Nova","Popstar Starr Nova"],
    "Wendy": ["True Silver Wendy"],
    "Spike": ["Sakura Spike","Dark Lord Spike"],
    "Crow": ["Crowbone","Phoenix Crow"],
    "Leon": ["Shark Leon","Dino Leon"],
    "Sandy": ["Sleepy Sandy","Nightmare Sandy"],
    "Amber": ["Frost Queen Amber","Bubble Trouble Amber"],
    "Meg": ["Beetle Meg","Jaguar Spirit Meg"],
    "Surge": ["DIY Surge","Surge Kong"],
    "Chester": ["Loki Chester","Moon Guardian Chester"],
    "Cordelius": ["Odin Cordelius","Paper Cordelius"],
    "Kit": ["Siamese Kit","Calico Kit"],
    "Draco": ["Dark Knight Draco","Eddie Draco"],
    "Kenji": ["Oni Kenji","Fruit Samurai Kenji"],
    "Pierce": ["High Stakes Pierce","Knight Pierce"],
    "Nori": ["Nano Nori","True Silver Nori"],
    "Kaze": ["Fruity Kaze","Clockwork Kaze"],
    "Sirius": ["True Silver Sirius"],
}

CATALOG = {}
for brawler, skins in SKINS.items():
    if brawler not in BRAWLER_RARITY:
        continue
    for index, name in enumerate(skins):
        skin_id = f"{brawler}|{name}"
        if len(skin_id) > 100:
            raise RuntimeError("Skin ID is too long.")
        price = RARITY_SKIN_PRICE[BRAWLER_RARITY[brawler]] + index * 85
        CATALOG[skin_id] = (brawler, name, price)


def today_prague() -> date:
    return datetime.now(PRAGUE).date()


def daily_rewards(guild_id: int, user_id: int, day: date) -> tuple[int, int, int]:
    # Stable preview on multiple commands or across instances.
    digest = hashlib.sha256(f"puvod-daily-v1:{guild_id}:{user_id}:{day.isoformat()}".encode()).digest()
    return (1 + digest[0] % 2, 2 + digest[1] % 4, 40 + digest[2] % 31)


def has_brawler(owned_string: str | None, brawler: str) -> bool:
    return brawler in {x.strip() for x in (owned_string or "").split(",") if x.strip()}


def nice_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class DailyClaimView(discord.ui.View):
    def __init__(self, cog: "BrawlShopCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Vyzvednout FREE odměnu", style=discord.ButtonStyle.success,
                       emoji="🎁", custom_id="puvod:brawl:daily:v1")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.claim_daily(interaction)


class BrawlShopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        # All player data stays under existing user_brawl table RLS.
        # No new public Supabase tables or access policies are created.
        for statement in (
            "ALTER TABLE public.user_brawl ADD COLUMN IF NOT EXISTS blings INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE public.user_brawl ADD COLUMN IF NOT EXISTS last_daily_claim_date DATE",
            "ALTER TABLE public.user_brawl ADD COLUMN IF NOT EXISTS skin_inventory TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
            "ALTER TABLE public.user_brawl ADD COLUMN IF NOT EXISTS equipped_skins JSONB NOT NULL DEFAULT '{}'::jsonb",
        ):
            await db.execute(statement)
        self.bot.add_view(DailyClaimView(self))
        logger.info("Brawl shop: Blingy, daily shop a skin inventory pripraveny.")

    @staticmethod
    async def defer(interaction: discord.Interaction) -> bool:
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            return True
        except discord.NotFound:
            return False

    @staticmethod
    async def get_account(guild_id: int, user_id: int):
        row = await db.fetchrow(
            "SELECT tokens, gems, blings, last_daily_claim_date, brawlers, "
            "skin_inventory, equipped_skins FROM public.user_brawl "
            "WHERE guild_id=$1 AND user_id=$2", str(guild_id), str(user_id),
        )
        if row is None:
            return {
                "tokens": 0, "gems": 0, "blings": 0,
                "last_daily_claim_date": None, "brawlers": "",
                "skin_inventory": [], "equipped_skins": {},
            }
        account = dict(row)
        equipped_raw = account.get("equipped_skins")
        equipped = json.loads(equipped_raw) if isinstance(equipped_raw, str) else equipped_raw
        account["equipped_skins"] = equipped if isinstance(equipped, dict) else {}
        return account

    async def claim_daily(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("❌ Pouze na serveru.", ephemeral=True)
            return
        if not await self.defer(interaction):
            return
        guild_id, user_id = str(interaction.guild_id), str(interaction.user.id)
        day = today_prague()
        tokens, gems, blings = daily_rewards(interaction.guild_id, interaction.user.id, day)
        try:
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO public.user_brawl (guild_id, user_id) VALUES ($1,$2) "
                        "ON CONFLICT (guild_id,user_id) DO NOTHING", guild_id, user_id,
                    )
                    row = await conn.fetchrow(
                        "SELECT last_daily_claim_date FROM public.user_brawl "
                        "WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", guild_id, user_id,
                    )
                    if row is None:
                        raise RuntimeError("Chybi profil hrace")
                    already_claimed = row["last_daily_claim_date"] == day
                    if not already_claimed:
                        result = await conn.fetchrow(
                            "UPDATE public.user_brawl SET "
                            "tokens=COALESCE(tokens,0)+$3, gems=COALESCE(gems,0)+$4, "
                            "blings=COALESCE(blings,0)+$5, last_daily_claim_date=$6 "
                            "WHERE guild_id=$1 AND user_id=$2 "
                            "RETURNING tokens, gems, blings",
                            guild_id, user_id, tokens, gems, blings, day,
                        )
            if already_claimed:
                await interaction.followup.send(
                    "✅ Dnešní FREE odměnu už máš. Další bude o půlnoci (Praha).",
                    ephemeral=True,
                )
                return
            embed = discord.Embed(
                title="🎁 DAILY FREE • VYZVEDNUTO",
                description=(
                    f"🪙 **+{tokens} tokenů**\n"
                    f"💎 **+{gems} gemů**\n"
                    f"🔷 **+{blings} Blingů**\n\n"
                    "Další odměna je dostupná **po půlnoci českého času**."
                ),
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Tvoje peněženka",
                value=f"🪙 {nice_int(result['tokens'])}  •  💎 {nice_int(result['gems'])}  •  🔷 {nice_int(result['blings'])}",
                inline=False,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Daily claim failed: server=%s user=%s", guild_id, user_id)
            await interaction.followup.send(
                "❌ Odměnu se nepodařilo potvrdit v Supabase. Zkus znovu.",
                ephemeral=True,
            )

    @app_commands.guild_only()
    @app_commands.command(name="dailyshop", description="Zobraz dnešní FREE odměny a vyzvedni je.")
    async def dailyshop(self, interaction: discord.Interaction):
        if not await self.defer(interaction):
            return
        try:
            day = today_prague()
            data = await self.get_account(interaction.guild_id, interaction.user.id)
            tokens, gems, blings = daily_rewards(interaction.guild_id, interaction.user.id, day)
            claimed = data["last_daily_claim_date"] == day
            embed = discord.Embed(
                title="🛍️ PUVOD • DAILY SHOP",
                description=(
                    "## 🎁 DNEŠNÍ FREE BALÍČEK\n"
                    f"🪙 **{tokens} tokenů**\n"
                    f"💎 **{gems} gemů**\n"
                    f"🔷 **{blings} Blingů**\n\n"
                    f"**Stav:** {'✅ Už vyzvednuto' if claimed else '🟢 Připraveno k vyzvednutí'}\n"
                    "📅 Reset každý den o **00:00 (Europe/Prague)**"
                ),
                color=discord.Color.from_rgb(126, 87, 194),
            )
            embed.add_field(
                name="💰 Tvoje peněženka",
                value=f"🪙 {nice_int(data['tokens'])}  •  💎 {nice_int(data['gems'])}  •  🔷 {nice_int(data['blings'])}",
                inline=False,
            )
            embed.set_footer(text="Skins: /skinshop • vlastní skiny: /myskins")
            if claimed:
                # discord.py rejects view=None; omit the parameter entirely.
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    embed=embed, view=DailyClaimView(self), ephemeral=True
                )
        except Exception:
            logger.exception("Daily shop display failed")
            await interaction.followup.send("❌ Obchod se nepodařilo načíst.", ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="claimdaily", description="Vyzvedni si denní tokeny, gemy a Blingy.")
    async def claimdaily(self, interaction: discord.Interaction):
        await self.claim_daily(interaction)

    @app_commands.guild_only()
    @app_commands.command(name="blings", description="Zjisti, kolik máš Blingů.")
    async def blings(self, interaction: discord.Interaction):
        if not await self.defer(interaction):
            return
        data = await self.get_account(interaction.guild_id, interaction.user.id)
        await interaction.followup.send(
            f"🔷 **{nice_int(data['blings'])} Blingů**\n"
            "Získej další v /dailyshop nebo otevíráním boxů. Skins: /skinshop",
            ephemeral=True,
        )

    @staticmethod
    def autocomplete_brawler_list(current: str):
        names = sorted({item[0] for item in CATALOG.values()})
        hits = [name for name in names if current.casefold() in name.casefold()]
        return [app_commands.Choice(name=name, value=name) for name in hits[:25]]

    @app_commands.guild_only()
    @app_commands.command(name="skinshop", description="Prohlédni si skiny pro vybraného Brawlera.")
    @app_commands.describe(brawler="Jméno Brawlera; můžeš použít našeptávač.")
    async def skinshop(self, interaction: discord.Interaction, brawler: str | None = None):
        if not await self.defer(interaction):
            return
        account = await self.get_account(interaction.guild_id, interaction.user.id)
        owned = set(account["skin_inventory"] or [])
        embed = discord.Embed(
            title="🎨 PUVOD • SKIN SHOP",
            description=(
                f"🔷 Tvoje Blingy: **{nice_int(account['blings'])}**\n"
                "Skin lze koupit **jen pro Brawlera, kterého vlastníš**.\n"
                "Nákup: /buyskin • Výbava: /equipskin\n\n"
            ),
            color=discord.Color.from_rgb(126, 87, 194),
        )
        if not brawler:
            possible = [name for name in sorted(SKINS) if name in BRAWLER_RARITY]
            own = [name for name in possible if has_brawler(account["brawlers"], name)]
            embed.description += (
                f"V katalogu je **{len(CATALOG)} skinů pro {len(possible)} Brawlerů**.\n"
                "Pro nabídku použij /skinshop brawler:<jméno>.\n\n"
                "🎮 Tvoji Brawleři se skiny: "
                + (", ".join(own[:22]) + ("…" if len(own) > 22 else "") if own else "Zatím žádní.")
            )
        else:
            match = next((name for name in SKINS if name.casefold() == brawler.casefold()), None)
            if match is None or match not in BRAWLER_RARITY:
                await interaction.followup.send("❌ Tohohle Brawlera v katalogu nemáme.", ephemeral=True)
                return
            has = has_brawler(account["brawlers"], match)
            embed.description += f"## {match}\n" + ("✅ Vlastníš Brawlera\n" if has else "🔒 Nejdřív potřebuješ Brawlera\n")
            for skin_id, (item_brawler, name, price) in CATALOG.items():
                if item_brawler != match:
                    continue
                symbol = "✅ Zakoupeno" if skin_id in owned else f"🔷 {price} Blingů"
                embed.add_field(name=f"✨ {name}", value=symbol, inline=False)
        embed.set_footer(text="Ceny Blingů jsou vlastní pravidla Puvod Discord bota.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @skinshop.autocomplete("brawler")
    async def suggest_brawler(self, interaction: discord.Interaction, current: str):
        return self.autocomplete_brawler_list(current)

    @app_commands.guild_only()
    @app_commands.command(name="buyskin", description="Kup si skin za Blingy (musíš vlastnit Brawlera).")
    @app_commands.describe(skin="Název skinu; vyber z našeptávače.")
    async def buyskin(self, interaction: discord.Interaction, skin: str):
        if not await self.defer(interaction):
            return
        if skin not in CATALOG:
            await interaction.followup.send("❌ Neznámý skin. Vyber skin z /skinshop.", ephemeral=True)
            return
        brawler, name, price = CATALOG[skin]
        gid, uid = str(interaction.guild_id), str(interaction.user.id)
        try:
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO public.user_brawl (guild_id,user_id) VALUES ($1,$2) "
                        "ON CONFLICT (guild_id,user_id) DO NOTHING", gid, uid,
                    )
                    account = await conn.fetchrow(
                        "SELECT blings, brawlers, skin_inventory FROM public.user_brawl "
                        "WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", gid, uid,
                    )
                    if not has_brawler(account["brawlers"], brawler):
                        status = f"🔒 Nejdřív musíš získat Brawlera **{brawler}**."
                    elif skin in (account["skin_inventory"] or []):
                        status = f"✅ **{name}** už vlastníš."
                    elif account["blings"] < price:
                        status = f"🔷 Chybí ti **{price - account['blings']} Blingů** na **{name}**."
                    else:
                        result = await conn.fetchrow(
                            "UPDATE public.user_brawl SET blings=blings-$3, "
                            "skin_inventory=array_append(skin_inventory,$4::text) "
                            "WHERE guild_id=$1 AND user_id=$2 RETURNING blings",
                            gid, uid, price, skin,
                        )
                        status = (f"🎉 **Zakoupen skin: {name}!**\n"
                                  f"🔷 Zaplaceno: {price} • Zbývá: {result['blings']}\n"
                                  "Nyní můžeš použít /equipskin.")
            await interaction.followup.send(status, ephemeral=True)
        except Exception:
            logger.exception("Skin purchase failed: %s", skin)
            await interaction.followup.send("❌ Nákup se nepodařilo potvrdit v Supabase.", ephemeral=True)

    @buyskin.autocomplete("skin")
    async def suggest_skin(self, interaction: discord.Interaction, current: str):
        needle = current.casefold()
        hits = [
            app_commands.Choice(name=f"{name} • {price} Blingů"[:100], value=skin_id)
            for skin_id, (brawler, name, price) in CATALOG.items()
            if needle in name.casefold() or needle in brawler.casefold()
        ]
        return hits[:25]

    @app_commands.guild_only()
    @app_commands.command(name="myskins", description="Prohlédni si svoje zakoupené skiny.")
    async def myskins(self, interaction: discord.Interaction):
        if not await self.defer(interaction):
            return
        data = await self.get_account(interaction.guild_id, interaction.user.id)
        skins = data["skin_inventory"] or []
        equipped = data["equipped_skins"] or {}
        lines = []
        for skin_id in skins:
            if skin_id not in CATALOG:
                continue
            brawler, name, _ = CATALOG[skin_id]
            icon = "✅" if equipped.get(brawler) == skin_id else "🎨"
            lines.append(f"{icon} **{name}** • {brawler}")
        embed = discord.Embed(
            title="🎒 Moje skiny",
            description=(
                f"🔷 Blingy: **{nice_int(data['blings'])}** • Zakoupeno: **{len(skins)}**\n\n"
                + ("\n".join(lines)[:3600] if lines else
                   "Zatím nevlastníš žádné skiny. Začni v /skinshop.")
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="✅ právě vybavené skiny • vybavení změň přes /equipskin")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.guild_only()
    @app_commands.command(name="equipskin", description="Vybav si zakoupený skin pro svého Brawlera.")
    @app_commands.describe(skin="Zakoupený skin; vyber z našeptávače.")
    async def equipskin(self, interaction: discord.Interaction, skin: str):
        if not await self.defer(interaction):
            return
        if skin not in CATALOG:
            await interaction.followup.send("❌ Neznámý skin.", ephemeral=True)
            return
        brawler, name, _ = CATALOG[skin]
        try:
            gid, uid = str(interaction.guild_id), str(interaction.user.id)
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    account = await conn.fetchrow(
                        "SELECT brawlers, skin_inventory FROM public.user_brawl "
                        "WHERE guild_id=$1 AND user_id=$2 FOR UPDATE", gid, uid,
                    )
                    if account is None or not has_brawler(account["brawlers"], brawler):
                        message = f"🔒 Nejdřív musíš vlastnit Brawlera **{brawler}**."
                    elif skin not in (account["skin_inventory"] or []):
                        message = "🔒 Tento skin ještě nevlastníš. Kup ho přes /buyskin."
                    else:
                        await conn.execute(
                            "UPDATE public.user_brawl SET equipped_skins = "
                            "jsonb_set(COALESCE(equipped_skins,'{}'::jsonb), ARRAY[$3::text], to_jsonb($4::text), true) "
                            "WHERE guild_id=$1 AND user_id=$2",
                            gid, uid, brawler, skin,
                        )
                        message = f"✨ **{name}** je nyní vybavený skin pro **{brawler}**!"
            await interaction.followup.send(message, ephemeral=True)
        except Exception:
            logger.exception("Skin equip failed: %s", skin)
            await interaction.followup.send("❌ Nepodařilo se uložit vybavený skin.", ephemeral=True)

    @equipskin.autocomplete("skin")
    async def suggest_equip_skin(self, interaction: discord.Interaction, current: str):
        try:
            data = await self.get_account(interaction.guild_id, interaction.user.id)
        except Exception:
            return []
        needle = current.casefold()
        return [
            app_commands.Choice(name=CATALOG[skin_id][1][:100], value=skin_id)
            for skin_id in (data["skin_inventory"] or [])
            if skin_id in CATALOG and needle in CATALOG[skin_id][1].casefold()
        ][:25]


async def setup(bot: commands.Bot):
    await bot.add_cog(BrawlShopCog(bot))
