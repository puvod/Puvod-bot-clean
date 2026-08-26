import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

from database import (
    get_user_brawl_data, add_tokens_and_gems, add_brawler_to_user
)

# Seznam Brawlerů rozdělený podle raritek
BRAWLERS = {
    "Rare": [
        {"name": "Shelly", "color": discord.Color.green()},
        {"name": "Colt", "color": discord.Color.green()},
        {"name": "Bull", "color": discord.Color.green()},
        {"name": "Brock", "color": discord.Color.green()},
        {"name": "El Primo", "color": discord.Color.green()},
        {"name": "Barley", "color": discord.Color.green()},
        {"name": "Poco", "color": discord.Color.green()},
        {"name": "Rosa", "color": discord.Color.green()}
    ],
    "Super Rare": [
        {"name": "Rico", "color": discord.Color.blue()},
        {"name": "Darryl", "color": discord.Color.blue()},
        {"name": "Penny", "color": discord.Color.blue()},
        {"name": "Carl", "color": discord.Color.blue()},
        {"name": "Jacky", "color": discord.Color.blue()}
    ],
    "Epic": [
        {"name": "Piper", "color": discord.Color.purple()},
        {"name": "Pam", "color": discord.Color.purple()},
        {"name": "Frank", "color": discord.Color.purple()},
        {"name": "Bibi", "color": discord.Color.purple()},
        {"name": "Bea", "color": discord.Color.purple()},
        {"name": "Nani", "color": discord.Color.purple()},
        {"name": "Edgar", "color": discord.Color.purple()},
        {"name": "Griff", "color": discord.Color.purple()},
        {"name": "Grom", "color": discord.Color.purple()},
        {"name": "Bonnie", "color": discord.Color.purple()}
    ],
    "Mythic": [
        {"name": "Mortis", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Tara", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Gene", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Max", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Mr. P", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Sprout", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Byron", "color": discord.Color.from_rgb(186, 85, 211)},
        {"name": "Squeak", "color": discord.Color.from_rgb(186, 85, 211)}
    ],
    "Legendary": [
        {"name": "Spike", "color": discord.Color.gold()},
        {"name": "Crow", "color": discord.Color.gold()},
        {"name": "Leon", "color": discord.Color.gold()},
        {"name": "Sandy", "color": discord.Color.gold()},
        {"name": "Amber", "color": discord.Color.gold()},
        {"name": "Meg", "color": discord.Color.gold()},
        {"name": "Chester", "color": discord.Color.gold()}
    ]
}

# Šance pro jednotlivé boxy (součetvah = 100)
BOX_RATES = {
    "brawl_box": {"Rare": 65, "Super Rare": 25, "Epic": 8, "Mythic": 1.8, "Legendary": 0.2},
    "big_box": {"Rare": 40, "Super Rare": 35, "Epic": 18, "Mythic": 6, "Legendary": 1.0},
    "mega_box": {"Rare": 15, "Super Rare": 30, "Epic": 35, "Mythic": 15, "Legendary": 5.0}
}

class BrawlCog(commands.Cog, name="brawl"):
    def __init__(self, bot):
        self.bot = bot

    # Pomocná funkce pro automatické vytvoření a přidělení role
    async def _assign_brawler_role(self, guild: discord.Guild, member: discord.Member, brawler_info: dict):
        role_name = f"🤖 {brawler_info['name']}"
        role = discord.utils.get(guild.roles, name=role_name)
        
        # Pokud role neexistuje, bot ji automaticky vytvoří
        if not role:
            try:
                role = await guild.create_role(
                    name=role_name,
                    color=brawler_info["color"],
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

    def _roll_brawler(self, box_type: str):
        rates = BOX_RATES[box_type]
        rarities = list(rates.keys())
        weights = list(rates.values())
        
        chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
        chosen_brawler = random.choice(BRAWLERS[chosen_rarity])
        return chosen_rarity, chosen_brawler

    # --- PŘÍKAZY PRO ŠTĚSTÍ (BOXŮ) ---

    @app_commands.command(name="brawlbox", description="Otevře klasický Brawl Box (Zdarma bez omezení).")
    async def brawlbox(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        rarity, brawler = self._roll_brawler("brawl_box")
        is_new = await add_brawler_to_user(interaction.guild_id, interaction.user.id, brawler["name"])
        await self._assign_brawler_role(interaction.guild, interaction.user, brawler)

        embed = discord.Embed(
            title="📦 Brawl Box Otevřen!",
            description=f"Padl ti Brawler: **{brawler['name']}**!\nRarita: **{rarity}**",
            color=brawler["color"]
        )
        if not is_new:
            embed.set_footer(text="Tohoto Brawlera už vlastníš! (Získal jsi duplikát)")
        else:
            embed.set_footer(text="✨ Nový Brawler do sbírky! Role ti byla přidělena.")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="bigbox", description="Otevře Big Box (Stojí 10 Tokenů).")
    async def bigbox(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        if user_data["tokens"] < 10:
            return await interaction.followup.send(
                f"❌ Nemáš dostatek tokenů! Potřebuješ **10 tokenů**, ale máš pouze **{user_data['tokens']}**.",
                ephemeral=True
            )

        await add_tokens_and_gems(interaction.guild_id, interaction.user.id, tokens=-10)
        
        rarity, brawler = self._roll_brawler("big_box")
        is_new = await add_brawler_to_user(interaction.guild_id, interaction.user.id, brawler["name"])
        await self._assign_brawler_role(interaction.guild, interaction.user, brawler)

        embed = discord.Embed(
            title="🎁 Big Box Otevřen!",
            description=f"Padl ti Brawler: **{brawler['name']}**!\nRarita: **{rarity}**",
            color=brawler["color"]
        )
        if not is_new:
            embed.set_footer(text="Tohoto Brawlera už máš ve sbírce.")
        else:
            embed.set_footer(text="🎉 Nový Brawler odemčen!")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="megabox", description="Otevře Mega Box s obří šancí na Legendárky (Stojí 80 Gemů).")
    async def megabox(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        if user_data["gems"] < 80:
            return await interaction.followup.send(
                f"❌ Nemáš dostatek gemů! Potřebuješ **80 Gemů**, ale máš pouze **{user_data['gems']}**.",
                ephemeral=True
            )

        await add_tokens_and_gems(interaction.guild_id, interaction.user.id, gems=-80)
        
        rarity, brawler = self._roll_brawler("mega_box")
        is_new = await add_brawler_to_user(interaction.guild_id, interaction.user.id, brawler["name"])
        await self._assign_brawler_role(interaction.guild, interaction.user, brawler)

        embed = discord.Embed(
            title="💥 MEGA BOX Otevřen!",
            description=f"Padl ti Brawler: **{brawler['name']}**!\nRarita: **{rarity}**",
            color=brawler["color"]
        )
        if not is_new:
            embed.set_footer(text="Tohoto Brawlera už máš ve sbírce.")
        else:
            embed.set_footer(text="🔥 Získal jsi nového Brawlera!")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="inventory", description="Zobrazí tvůj stav Tokenů, Gemů a získané Brawlery.")
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_data = await get_user_brawl_data(interaction.guild_id, interaction.user.id)
        
        brawlers = user_data["brawlers"]
        brawler_str = ", ".join(brawlers) if brawlers else "*Zatím nemáš žádné Brawlery.*"

        embed = discord.Embed(
            title=f"🎒 Inventář – {interaction.user.display_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🪙 Tokeny", value=str(user_data["tokens"]), inline=True)
        embed.add_field(name="💎 Gemy", value=str(user_data["gems"]), inline=True)
        embed.add_field(name="🏆 Vlastnění Brawleři", value=brawler_str, inline=False)

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

async def setup(bot):
    await bot.add_cog(BrawlCog(bot))