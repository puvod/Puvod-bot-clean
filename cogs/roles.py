import unicodedata
import discord
from discord import app_commands
from discord.ext import commands

def normalize_text(text: str) -> str:
    text = text.lower().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# -------------------------------------------------------------------
# PERSISTENTNÍ PRVKY PRO ROLOVÉ MENU
# -------------------------------------------------------------------

class CombinedRoleView(discord.ui.View):
    def __init__(self, roles: list[discord.Role] = None):
        super().__init__(timeout=None)  # timeout=None = tlačítka fungují navždy!
        if roles:
            for role in roles[:5]:
                self.add_item(RoleButton(role))
            if len(roles) > 5:
                self.add_item(RoleSelect(roles[5:]))

class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role):
        super().__init__(
            label=role.name, 
            style=discord.ButtonStyle.primary, 
            custom_id=f"btn_role_{role.id}"
        )
        self.role_id = role.id

    async def callback(self, interaction: discord.Interaction):
        role_id = getattr(self, "role_id", int(self.custom_id.replace("btn_role_", "")))
        role = interaction.guild.get_role(role_id)
        
        if not role:
            await interaction.response.send_message("Tato role už na serveru neexistuje!", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Odebral jsem ti roli: **{role.name}**", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Přidal jsem ti roli: **{role.name}**", ephemeral=True)

class RoleSelect(discord.ui.Select):
    def __init__(self, roles: list[discord.Role]):
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles]
        super().__init__(placeholder="Další role...", options=options, custom_id="select_roles_extra")

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("Tato role už na serveru neexistuje!", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Odebral jsem ti roli: **{role.name}**", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Přidal jsem ti roli: **{role.name}**", ephemeral=True)

# -------------------------------------------------------------------
# MODAL PRO TVORBU MENU
# -------------------------------------------------------------------

class RoleModal(discord.ui.Modal, title='Vytvořit menu rolí'):
    title_input = discord.ui.TextInput(
        label='Nadpis Embedu', 
        placeholder='VÝBĚR ROLÍ'
    )
    desc_input = discord.ui.TextInput(
        label='Popis', 
        style=discord.TextStyle.paragraph, 
        placeholder='Vyber si své role...\n(můžeš řádkovat)'
    )
    roles_input = discord.ui.TextInput(
        label='ID rolí (oddělené čárkou)', 
        placeholder='1234567890, 0987654321'
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_ids = [int(i.strip()) for i in self.roles_input.value.split(',') if i.strip()]
            roles = [interaction.guild.get_role(rid) for rid in role_ids if interaction.guild.get_role(rid)]
            
            if not roles:
                await interaction.response.send_message("❌ Žádná z vložených ID rolí nebyla na serveru nalezena!", ephemeral=True)
                return

            embed = discord.Embed(
                title=self.title_input.value, 
                description=self.desc_input.value, 
                color=discord.Color.blue()
            )
            view = CombinedRoleView(roles)
            
            await interaction.channel.send(embed=embed, view=view)
            await interaction.response.send_message("✅ Menu bylo úspěšně vytvořeno a odesláno!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Zadaná ID rolí musí být čísla oddělená čárkami!", ephemeral=True)

# -------------------------------------------------------------------
# SYSTÉM PRO BRAWL STARS RANKY
# -------------------------------------------------------------------

BRAWL_RANKS = {
    1464661112565006459: "Gold",
    1463231879414157446: "Diamond",
    1463232501949399164: "Mythic",
    1463232272164585474: "Legendary",
    1463232392281198776: "Masters",
    1463232574313988168: "PRO"
}

class RankSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="Vyber si svůj Brawl Stars Rank...",
        custom_id="brawl_stars_rank_select",
        options=[
            discord.SelectOption(label="Gold Rank", value="1464661112565006459", emoji="🟡"),
            discord.SelectOption(label="Diamond Rank", value="1463231879414157446", emoji="💎"),
            discord.SelectOption(label="Mythic Rank", value="1463232501949399164", emoji="🔴"),
            discord.SelectOption(label="Legendary Rank", value="1463232272164585474", emoji="🟡"),
            discord.SelectOption(label="Masters Rank", value="1463232392281198776", emoji="🟣"),
            discord.SelectOption(label="PRO Rank", value="1463232574313988168", emoji="⚡")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_role_id = int(select.values[0])
        guild = interaction.guild
        member = interaction.user
        
        selected_role = guild.get_role(selected_role_id)
        if not selected_role:
            await interaction.response.send_message("Tato role nebyla na serveru nalezena!", ephemeral=True)
            return

        roles_to_remove = [
            guild.get_role(rid) for rid in BRAWL_RANKS.keys() 
            if rid != selected_role_id and guild.get_role(rid) in member.roles
        ]
        
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove)

        if selected_role in member.roles:
            await member.remove_roles(selected_role)
            await interaction.response.send_message(f"Odebral jsem ti rank: **{selected_role.name}**", ephemeral=True)
        else:
            await interaction.user.add_roles(selected_role)
            await interaction.response.send_message(f"Nastavil jsem ti rank: **{selected_role.name}** 🏆", ephemeral=True)

# -------------------------------------------------------------------
# ROLES COG TŘÍDA
# -------------------------------------------------------------------

class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Globální zachytávač pro tlačítka rolí po restartu bota."""
        if interaction.response.is_done():
            return

        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")

            # --- 1. ODCHYTÁVÁNÍ TLAČÍTEK Z /create MENU ---
            if custom_id.startswith("btn_role_"):
                try:
                    role_id = int(custom_id.replace("btn_role_", ""))
                    role = interaction.guild.get_role(role_id)

                    if not role:
                        await interaction.response.send_message("Tato role už na serveru neexistuje!", ephemeral=True)
                        return

                    if role in interaction.user.roles:
                        await interaction.user.remove_roles(role)
                        await interaction.response.send_message(f"Odebral jsem ti roli: **{role.name}**", ephemeral=True)
                    else:
                        await interaction.user.add_roles(role)
                        await interaction.response.send_message(f"Přidal jsem ti roli: **{role.name}**", ephemeral=True)
                except Exception as e:
                    print(f"Chyba při zpracování tlačítka role: {e}")

            # --- 2. ODCHYTÁVÁNÍ SELECT MENU Z /create (POKUD JE ROLÍ VÍCE NEŽ 5) ---
            elif custom_id == "select_roles_extra":
                try:
                    selected_role_id = int(interaction.data.get("values", [])[0])
                    role = interaction.guild.get_role(selected_role_id)

                    if not role:
                        await interaction.response.send_message("Tato role už na serveru neexistuje!", ephemeral=True)
                        return

                    if role in interaction.user.roles:
                        await interaction.user.remove_roles(role)
                        await interaction.response.send_message(f"Odebral jsem ti roli: **{role.name}**", ephemeral=True)
                    else:
                        await interaction.user.add_roles(role)
                        await interaction.response.send_message(f"Přidal jsem ti roli: **{role.name}**", ephemeral=True)
                except Exception as e:
                    print(f"Chyba při zpracování select menu: {e}")

    @app_commands.command(name="create", description="Vytvoří vlastní menu pro výběr rolí")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_roles_menu(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RoleModal())

    @app_commands.command(name="brawlrankmenu", description="Pošle menu pro výběr Brawl Stars ranků")
    @app_commands.checks.has_permissions(administrator=True)
    async def brawlrankmenu(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⭐ BRAWL STARS RANKY ⭐",
            description="Vyber si svůj aktuální rank v menu níže:",
            color=discord.Color.gold()
        )
        view = RankSelectView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("Brawl Stars menu bylo vytvořeno!", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))