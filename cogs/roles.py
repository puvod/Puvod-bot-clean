import discord
from discord import app_commands
from discord.ext import commands
from database import add_selectable_role, get_selectable_roles

class RoleSelect(discord.ui.Select):
    def __init__(self, roles):
        options = [discord.SelectOption(label=r.name, value=str(r.id), description=f"ID: {r.id}") for r in roles]
        super().__init__(placeholder="Vyber si svoji roli...", options=options)

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        
        if not role:
            return await interaction.response.send_message("Role už neexistuje.", ephemeral=True)
            
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Odebral jsem ti roli: **{role.name}**", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Přidal jsem ti roli: **{role.name}**", ephemeral=True)

class RoleView(discord.ui.View):
    def __init__(self, roles):
        super().__init__(timeout=None)
        self.add_item(RoleSelect(roles))

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="role-add", description="[Admin] Přidá roli do výběrového menu")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_role(self, interaction: discord.Interaction, role: discord.Role):
        add_selectable_role(interaction.guild_id, role.id)
        await interaction.response.send_message(f"✅ Role {role.mention} byla přidána do menu.", ephemeral=True)

    @app_commands.command(name="role", description="Otevře menu pro výběr rolí")
    async def get_roles(self, interaction: discord.Interaction):
        role_ids = get_selectable_roles(interaction.guild_id)
        roles = [interaction.guild.get_role(int(r_id)) for r_id in role_ids if interaction.guild.get_role(int(r_id))]
        
        if not roles:
            return await interaction.response.send_message("❌ Zatím nejsou nastaveny žádné role.", ephemeral=True)
        
        embed = discord.Embed(title="Výběr rolí", description="Kliknutím na menu pod zprávou si můžeš roli přidat nebo odebrat.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=RoleView(roles), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Roles(bot))