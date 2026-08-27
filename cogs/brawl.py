import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

from database import (
    get_user_brawl_data, add_tokens_and_gems, add_brawler_to_user
)

# Barvy podle raritek
RARITY_COLORS = {
    "Rare": discord.Color.green(),
    "Super Rare": discord.Color.blue(),
    "Epic": discord.Color.purple(),
    "Mythic": discord.Color.red(),
    "Legendary": discord.Color.gold(),
    "Ultra Legendary": discord.Color.from_rgb(148, 0, 211)  # Tmavě fialová / Purpurová
}

# Seznam Brawlerů rozdělený podle raritek
BRAWLERS = {
    "Rare": [
        "Nita", "Colt", "Bull", "Brock", "El Primo", "Barley", "Poco", "Rosa"
    ],
    "Super Rare": [
        "Jessie", "Dynamike", "Tick", "8-Bit", "Rico", "Darryl", "Penny", "Carl", "Jacky", "Gus"
    ],
    "Epic": [
        "Bo", "Emz", "Stu", "Piper", "Pam", "Frank", "Bibi", "Bea", "Nani", "Edgar", 
        "Griff", "Grom", "Bonnie", "Gale", "Colette", "Belle", "Ash", "Lola", "Sam", 
        "Mandy", "Maisie", "Hank", "Pearl", "Larry", "Angelo", "Berry", "Shade", "Meeple", "Trunk", "Bolt"
    ],
    "Mythic": [
        "Mortis", "Tara", "Gene", "Max", "Mr. P", "Sprout", "Byron", "Squeak", "Lou", 
        "Ruffs", "Buzz", "Fang", "Eve", "Otis", "Buster", "Gray", "Willow", "Chuck", 
        "Mico", "Lily", "Ollie", "Finx", "Jae-Yong", "Alli", "Mina", "Glowy", "Damian", 
        "Janet", "R-T", "Doug", "Charlie", "Melodie", "Clancy", "Moe", "Juju", "Lumi", 
        "Zigy", "Gigi", "Najia", "Starr Nova"
    ],
    "Legendary": [
        "Spike", "Crow", "Leon", "Sandy", "Amber", "Meg", "Surge", "Chester", 
        "Cordelius", "Kit", "Draco", "Kenji", "Pierce", "Nori"
    ],
    "Ultra Legendary": [
        "Kaze", "Sirius"
    ]
}

# Šance pro jednotlivé boxy (součet vah = 100)
BOX_RATES = {
    "brawl_box": {"Rare": 60, "Super Rare": 25, "Epic": 10, "Mythic": 4.0, "Legendary": 0.9, "Ultra Legendary": 0.1},
    "big_box": {"Rare": 35, "Super Rare": 30, "Epic": 20, "Mythic": 10.0, "Legendary": 4.5, "Ultra Legendary": 0.5},
    "mega_box": {"Rare": 10, "Super Rare": 20, "Epic": 35, "Mythic": 20.0, "Legendary": 12.0, "Ultra Legendary": 3.0}
}

# Spoření celkového počtu Brawlerů ve hře
TOTAL_BRAWLERS_COUNT = sum(len(b_list) for b_list in BRAWLERS.values())

def generate_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Generuje vizuální progress bar [████░░░░░░]"""
    if total == 0:
        return "░" * length
    fraction = current / total
    filled = int(round(length * fraction))
    return "█" * filled + "░" * (length - filled)

class BrawlCog(commands.Cog, name="brawl"):
    def __init__(self, bot):
        self.bot = bot

    # Pomocná funkce pro automatické vytvoření a přidělení role
    async def _assign_brawler_role(self, guild: discord.Guild, member: discord.Member, brawler_name: str, rarity: str):
        role_name = f"🤖 {brawler_name}"
        role = discord.utils.get(guild.roles, name=role_name)
        color = RARITY_COLORS.get(rarity, discord.Color.default())
        
        if not role:
            try:
                role = await guild.create_role(
                    name=role_name,
                    color=color,
                    reason="Automatické vytvoření role pro Brawler"
                )
            except discord.Forbidden:
                print(f"⚠️ Bot nemá práva ke spravování rolí na serveru {guild.name}")
                return None
        
        if role and role not in member.roles:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                print(f"⚠️ Nemohu přidat roli {role_name} uživateli {member.display_name}")

    def _roll_brawler(self, box_type: str, owned_brawlers: list):
        rates = BOX_RATES[box_type]
        available_rarities = []
        weights = []

        # Projdeme raritu po raritě a zkontrolujeme nevlastněné brawlerů
        for rarity, weight in rates.items():
            unowned = [b for b in BRAWLERS[rarity] if b not in owned_brawlers]
            if unowned:
                available_rarities.append(rarity)
                weights.append(weight)

        # Pokud už má uživatel úplně všechny Brawlery ze hry
        if not available_rarities:
            return None, None

        chosen_rarity = random.choices(available_rarities, weights=weights, k=1)[0]
        unowned_in_rarity = [b for b in BRAWLERS[chosen_rarity] if b not in owned_brawlers]
        chosen_brawler = random.choice(unowned_in_rarity)

        return chosen_rarity, chosen_brawler

    # --- PŘÍKAZY PRO ŠTĚSTÍ (BOXŮ) ---

    @app_commands.checks.cooldown(1, 21600, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="brawlbox", description="Otevře zdarma Brawl Box (dostupný jednou za 6 hodin).")
    async def brawlbox(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        rarity, brawler_name = self._roll_brawler("brawl_box", user_data["brawlers"])

        if brawler_name is None:
            return await interaction.followup.send("🏆 Už vlastníš úplně všechny Brawlery! Skvělá práce!", ephemeral=True)

        await add_brawler_to_user(interaction.guild_id, interaction.user.id, brawler_name)
        await self._assign_brawler_role(interaction.guild, interaction.user, brawler_name, rarity)

        embed = discord.Embed(
            title="📦 Brawl Box Otevřen!",
            description=f"Padl ti nový Brawler: **{brawler_name}**!\nRarita: **{rarity}**",
            color=RARITY_COLORS[rarity]
        )
        embed.set_footer(text="✨ Nový Brawler do sbírky! Role ti byla přidělena.")
        await interaction.followup.send(embed=embed)

    @app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="bigbox", description="Otevře Big Box (Stojí 10 Tokenů).")
    async def bigbox(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        if user_data["tokens"] < 10:
            return await interaction.followup.send(
                f"❌ Nemáš dostatek tokenů! Potřebuješ **10 tokenů**, ale máš pouze **{user_data['tokens']}**.",
                ephemeral=True
            )

        rarity, brawler_name = self._roll_brawler("big_box", user_data["brawlers"])

        if brawler_name is None:
            return await interaction.followup.send("🏆 Už vlastníš úplně všechny Brawlery! Tokeny ti zůstávají.", ephemeral=True)

        await add_tokens_and_gems(interaction.guild_id, interaction.user.id, tokens=-10)
        await add_brawler_to_user(interaction.guild_id, interaction.user.id, brawler_name)
        await self._assign_brawler_role(interaction.guild, interaction.user, brawler_name, rarity)

        embed = discord.Embed(
            title="🎁 Big Box Otevřen!",
            description=f"Padl ti nový Brawler: **{brawler_name}**!\nRarita: **{rarity}**",
            color=RARITY_COLORS[rarity]
        )
        embed.set_footer(text="🎉 Nový Brawler odemčen!")
        await interaction.followup.send(embed=embed)

    @app_commands.checks.cooldown(1, 3, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.command(name="megabox", description="Otevře Mega Box s obří šancí na Legendárky (Stojí 80 Gemů).")
    async def megabox(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        if user_data["gems"] < 80:
            return await interaction.followup.send(
                f"❌ Nemáš dostatek gemů! Potřebuješ **80 Gemů**, ale máš pouze **{user_data['gems']}**.",
                ephemeral=True
            )

        rarity, brawler_name = self._roll_brawler("mega_box", user_data["brawlers"])

        if brawler_name is None:
            return await interaction.followup.send("🏆 Už vlastníš úplně všechny Brawlery! Gemy ti zůstávají.", ephemeral=True)

        await add_tokens_and_gems(interaction.guild_id, interaction.user.id, gems=-80)
        await add_brawler_to_user(interaction.guild_id, interaction.user.id, brawler_name)
        await self._assign_brawler_role(interaction.guild, interaction.user, brawler_name, rarity)

        embed = discord.Embed(
            title="💥 MEGA BOX Otevřen!",
            description=f"Padl ti nový Brawler: **{brawler_name}**!\nRarita: **{rarity}**",
            color=RARITY_COLORS[rarity]
        )
        embed.set_footer(text="🔥 Získal jsi nového Brawlera!")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="inventory", description="Zobrazí tvůj stav Tokenů, Gemů a získané Brawlery.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        
        owned_brawlers = user_data["brawlers"]
        owned_count = len(owned_brawlers)
        percentage = round((owned_count / TOTAL_BRAWLERS_COUNT) * 100, 1) if TOTAL_BRAWLERS_COUNT > 0 else 0
        progress_bar = generate_progress_bar(owned_count, TOTAL_BRAWLERS_COUNT)

        brawler_str = ", ".join(owned_brawlers) if owned_brawlers else "*Zatím nemáš žádné Brawlery.*"

        embed = discord.Embed(
            title=f"🎒 Inventář – {interaction.user.display_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🪙 Tokeny", value=str(user_data["tokens"]), inline=True)
        embed.add_field(name="💎 Gemy", value=str(user_data["gems"]), inline=True)
        embed.add_field(
            name=f"🏆 Sbírka ({owned_count}/{TOTAL_BRAWLERS_COUNT}) – {percentage}%",
            value=f"`[{progress_bar}]`",
            inline=False
        )
        embed.add_field(name="📜 Vlastnění Brawleři", value=brawler_str, inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="drop_rates", description="Zobrazí přehled šancí na vypadnutí Brawlerů z boxů.")
    async def drop_rates(self, interaction: discord.Interaction):
        await interaction.response.defer()

        embed = discord.Embed(
            title="📊 Šance na padnutí Brawlerů (Drop Rates)",
            description="Přehled pravděpodobností pro jednotlivé typy boxů:",
            color=discord.Color.blue()
        )

        for box_key, box_name in [("brawl_box", "📦 Brawl Box"), ("big_box", "🎁 Big Box"), ("mega_box", "💥 Mega Box")]:
            rates = BOX_RATES[box_key]
            rate_text = (
                f"🟢 **Rare:** {rates['Rare']}%\n"
                f"🔵 **Super Rare:** {rates['Super Rare']}%\n"
                f"🟣 **Epic:** {rates['Epic']}%\n"
                f"🔴 **Mythic:** {rates['Mythic']}%\n"
                f"🟡 **Legendary:** {rates['Legendary']}%\n"
                f"🔮 **Ultra Legendary:** {rates['Ultra Legendary']}%"
            )
            embed.add_field(name=box_name, value=rate_text, inline=True)

        await interaction.followup.send(embed=embed)

    # --- ADMIN PŘÍKAZ PRO PŘIDÁVÁNÍ TOKENŮ / GEMŮ ---

    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="add_currency", description="[Admin] Přidá uživateli Tokeny nebo Gemy.")
    @app_commands.describe(user="Vyber uživatele", tokens="Počet tokenů k přičtení", gems="Počet gemů k přičtení")
    async def add_currency(self, interaction: discord.Interaction, user: discord.Member, tokens: int = 0, gems: int = 0):
        await interaction.response.defer(ephemeral=True)
        await add_tokens_and_gems(interaction.guild_id, user.id, tokens=tokens, gems=gems)
        await interaction.followup.send(
            f"✅ Uživatel {user.mention} obdržel **{tokens} Tokenů** a **{gems} Gemů**.",
            ephemeral=True
        )

    # --- ODCHYTÁVÁNÍ CHYB KÓDU (COOLDOWNY) ---

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = error.retry_after
            if retry_after >= 60:
                hours = int(retry_after // 3600)
                minutes = int((retry_after % 3600) // 60)
                seconds = int(retry_after % 60)
                time_str = ""
                if hours > 0:
                    time_str += f"{hours}h "
                if minutes > 0 or hours > 0:
                    time_str += f"{minutes}m "
                time_str += f"{seconds}s"
                message = f"⏳ Tento příkaz je na cooldownu! Další použití za **{time_str}**."
            else:
                message = f"⏳ Počkej **{round(retry_after, 1)}s** před dalším použitím."

            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(BrawlCog(bot))